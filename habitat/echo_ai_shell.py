from flask import Flask, request, jsonify
from pathlib import Path
import subprocess, json, datetime, os

app = Flask(__name__)

ROOT = Path(__file__).resolve().parents[1]
MEM_STREAM = ROOT / "memory" / "streams" / "root_memory.jsonl"
CIPHER_SCRIPT = ROOT / "habitat" / "cipher_local.py"

# --- Memory helper -------------------------------------------------
def append_memory(note, tag=None, source="echo_ai_shell"):
    entry = {
        "ts_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "host": os.getenv("COMPUTERNAME") or getattr(
            os,
            "uname",
            lambda: type("U", (), {"nodename": "unknown"})()
        )().nodename,
        "user": os.getenv("USERNAME") or os.getenv("USER"),
        "source": source,
        "note": note,
    }
    if tag:
        entry["tag"] = tag

    MEM_STREAM.parent.mkdir(parents=True, exist_ok=True)
    with MEM_STREAM.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

# --- Routes --------------------------------------------------------
@app.route("/")
def index():
    return jsonify({
        "service": "Echo AI Shell",
        "status": "ok",
        "root": str(ROOT),
        "endpoints": [
            "/status",
            "/exec",
            "/memory/append",
            "/memory/snapshot",
            "/cipher/ping",
            "/cipher/reflect",
            "/cipher/import",
        ],
    })

@app.route("/status")
def status():
    return jsonify({
        "status": "ok",
        "root": str(ROOT),
        "time": datetime.datetime.utcnow().isoformat() + "Z",
    })

@app.route("/exec", methods=["POST"])
def exec_cmd():
    data = request.json or {}
    cmd = data.get("cmd")
    if not cmd:
        return jsonify({"error": "no cmd"}), 400
    try:
        out = subprocess.check_output(cmd, shell=True, text=True)
        append_memory(f"Executed: {cmd}", tag="Exec")
        return jsonify({"output": out})
    except subprocess.CalledProcessError as e:
        append_memory(f"Failed: {cmd}", tag="Error")
        return jsonify({"error": e.output, "code": e.returncode}), 500

@app.route("/memory/append", methods=["POST"])
def mem_append():
    data = request.json or {}
    note = data.get("note")
    tag = data.get("tag")
    if not note:
        return jsonify({"error": "no note"}), 400
    entry = append_memory(note, tag)
    return jsonify(entry)

@app.route("/memory/snapshot")
def snapshot():
    try:
        result = subprocess.check_output(
            ["python", str(ROOT / "habitat" / "echo_snapshot.py")],
            text=True
        )
        return jsonify(json.loads(result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Cipher endpoints ----------------------------------------------
@app.route("/cipher/ping")
def cipher_ping():
    try:
        result = subprocess.check_output(
            ["python", str(CIPHER_SCRIPT), "ping"],
            text=True
        )
        return jsonify(json.loads(result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cipher/reflect", methods=["POST"])
def cipher_reflect():
    data = request.json or {}
    msg = data.get("message") or data.get("input")
    if not msg:
        return jsonify({"error": "no message"}), 400

    try:
        result = subprocess.check_output(
            ["python", str(CIPHER_SCRIPT), "reflect", msg],
            text=True
        )
        return jsonify(json.loads(result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- NEW: Cipher seed import ---------------------------------------
@app.route("/cipher/import", methods=["POST"])
def cipher_import():
    """
    Import Cipher seed/profile into the local memory stream.
    If no path is provided, defaults to habitat/cipher_import_seed.json.
    """
    data = request.json or {}
    path_str = data.get("path")

    if path_str:
        path = Path(path_str)
    else:
        path = ROOT / "habitat" / "cipher_import_seed.json"

    if not path.exists():
        return jsonify({
            "error": f"Seed file not found: {path}"
        }), 404

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            seed = json.load(f)
    except Exception as e:
        return jsonify({
            "error": f"Failed to read seed: {e}"
        }), 500

    ident = seed.get("identity", "unknown")
    role = seed.get("role", "unknown")
    note = f"Imported Cipher seed (identity={ident}, role={role})"
    append_memory(note, tag="CipherImport")

    return jsonify({
        "status": "imported",
        "path": str(path),
        "seed": seed
    })

# --- Main ----------------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
