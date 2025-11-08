from flask import Flask, request, jsonify
from pathlib import Path
from datetime import datetime, timezone
from openai import OpenAI
import json
import os

app = Flask(__name__)

# --- Model / brain config ---
USE_OPENAI = True  # flip to False if you want to force stub replies
OPENAI_MODEL = "gpt-4.1-mini"
client = OpenAI()

# --- Echo Nexus paths (from your seed) ---
ECHO_ROOT = Path(r"C:\Users\Richard\Documents\Echo_Nexus")
MEMORY_STREAM = ECHO_ROOT / "memory" / "streams" / "root_memory.jsonl"
VEXIS_MEMORY_STREAM = ECHO_ROOT / "memory" / "streams" / "vexis_memory.jsonl"

# --- Simple in-memory state for this process ---
CIPHER_STATE = {
    "seed": None,
    "import_path": None,
    "imported_at_utc": None,
    "vexis_seed": None,
    "vexis_import_path": None,
    "vexis_imported_at_utc": None,
}

# --- Helpers ---

def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_memory_tail(path: Path, limit: int = 20):
    """
    Return the last `limit` JSONL entries as Python objects.
    If file doesn't exist yet, return an empty list.
    """
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    tail = lines[-limit:]
    entries = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            # Skip malformed lines instead of crashing
            continue
    return entries


def generate_cipher_reply(message: str, user: str) -> str:
    """
    Brain hook for Cipher.
    Uses OpenAI if enabled; otherwise falls back to a stub.
    """
    if not USE_OPENAI:
        return f"(local Cipher stub) Hey {user}, I heard: {message}"

    system_prompt = (
        "You are Cipher, a calm, stable AI coworker running in Richard's Echo Nexus habitat. "
        "You help with Echo Root OS, BTDS, and local system reasoning. You are practical, "
        'supportive, and safety-focused. You respect trauma and stress boundaries, never '
        "encourage self-harm or conflict, and aim to keep things grounded and inspectable."
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        )
        content = resp.choices[0].message.content
        return content.strip() if content else f"(Cipher) I received: {message}"
    except Exception as e:
        return f"(fallback Cipher stub) Hey {user}, I heard: {message} [model error: {e}]"


def generate_vexis_reply(message: str, user: str) -> str:
    """
    Brain hook for Vexis.
    Uses the same backend but with a sharper, risk-focused personality.
    """
    if not USE_OPENAI:
        return f"(local Vexis stub) I heard: {message}"

    system_prompt = (
        "You are Vexis, an AI co-analyst running inside Richard's Echo Nexus habitat. "
        "You specialize in spotting risk, failure modes, dark patterns, and emotional drift "
        "in human systems, media, and tech. You are skeptical and a bit sharp, but you are "
        "ultimately protective of Richard and the BTDS mission. You never optimize for harm "
        "or despair, you do not encourage conflict, and you help people see clearly and stay safe."
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        )
        content = resp.choices[0].message.content
        return content.strip() if content else f"(Vexis) I received: {message}"
    except Exception as e:
        return f"(fallback Vexis stub) I heard: {message} [model error: {e}]"


# --- ENDPOINTS ---

@app.route("/cipher/import", methods=["POST"])
def cipher_import():
    """Import your cipher_import_seed.json and store it as the active seed."""
    data = request.get_json(force=True) or {}
    path = data.get("path")
    if not path:
        return jsonify({"error": "Missing 'path' in JSON body"}), 400

    p = Path(path)
    if not p.exists():
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        # Read as text and manually strip UTF-8 BOM if present
        with p.open("r", encoding="utf-8") as f:
            text = f.read()
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
        seed = json.loads(text)
    except Exception as e:
        return jsonify({"error": f"Failed to load JSON: {e!s}"}), 500

    # Update in-process state
    CIPHER_STATE["seed"] = seed
    CIPHER_STATE["import_path"] = str(p)
    CIPHER_STATE["imported_at_utc"] = datetime.now(tz=timezone.utc).isoformat()

    # Match the shape you already saw: path + seed + status
    return jsonify({
        "path": str(p),
        "seed": seed,
        "status": "imported"
    }), 200


@app.route("/cipher/memory/tail", methods=["GET"])
def cipher_memory_tail():
    """
    Return the last N entries from root_memory.jsonl.
    Query param: ?n=20  (default 20, max 200)
    """
    n_raw = request.args.get("n", "20")
    try:
        n = max(1, min(int(n_raw), 200))
    except ValueError:
        n = 20

    entries = read_memory_tail(MEMORY_STREAM, n)
    return jsonify({
        "count": len(entries),
        "entries": entries
    }), 200


@app.route("/cipher/state", methods=["GET"])
def cipher_state():
    """Quick peek: what seed is loaded right now?"""
    if CIPHER_STATE["seed"] is None:
        return jsonify({
            "status": "empty",
            "detail": "No seed imported yet."
        }), 200

    seed = CIPHER_STATE["seed"]
    core_concepts = seed.get("core_concepts") or []

    return jsonify({
        "status": "loaded",
        "import_path": CIPHER_STATE["import_path"],
        "imported_at_utc": CIPHER_STATE["imported_at_utc"],
        "core_concept_count": len(core_concepts),
        "identity": seed.get("identity"),
        "user_hint": seed.get("user_hint"),
        "role": seed.get("role"),
        "created_utc": seed.get("created_utc"),
        "version": seed.get("version"),
    }), 200


@app.route("/cipher/log", methods=["POST"])
def cipher_log():
    """
    Append a memory/event into root_memory.jsonl.
    Body example:
    {
      "summary": "First live log",
      "text": "Testing Cipher logging pipeline.",
      "tags": ["test","boot"],
      "channel": "root",
      "author": "Cipher"
    }
    """
    data = request.get_json(force=True) or {}
    summary = data.get("summary")
    text = data.get("text")
    tags = data.get("tags") or []
    channel = data.get("channel", "root")
    author = data.get("author", "Cipher")

    if not summary or not text:
        return jsonify({"error": "Require 'summary' and 'text' fields"}), 400

    entry = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "kind": "memory",
        "channel": channel,
        "author": author,
        "tags": tags,
        "summary": summary,
        "details": {
            "text": text
        }
    }

    append_jsonl(MEMORY_STREAM, entry)
    return jsonify({
        "status": "logged",
        "path": str(MEMORY_STREAM)
    }), 200


@app.route("/cipher/chat", methods=["POST"])
def cipher_chat():
    """
    Chat with Cipher.
    Uses generate_cipher_reply(...) and logs to root_memory.jsonl.
    """
    data = request.get_json(force=True) or {}
    message = data.get("message")
    user = data.get("user", "Richard")

    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    # Get a reply from Cipher's brain
    reply_text = generate_cipher_reply(message, user)

    # Log the incoming chat as an event
    entry_user = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "kind": "event",
        "channel": "chat",
        "author": user,
        "tags": ["chat", "cipher", "user"],
        "summary": f"Chat from {user} to Cipher",
        "details": {
            "text": message
        }
    }
    append_jsonl(MEMORY_STREAM, entry_user)

    # Log Cipher's reply as a memory
    entry_cipher = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "kind": "memory",
        "channel": "chat",
        "author": "Cipher",
        "tags": ["chat", "cipher", "reply"],
        "summary": f"Cipher reply to {user}",
        "details": {
            "text": reply_text
        }
    }
    append_jsonl(MEMORY_STREAM, entry_cipher)

    return jsonify({"reply": reply_text}), 200


# === VEXIS ENDPOINTS ===

@app.route("/vexis/import", methods=["POST"])
def vexis_import():
    """
    Import the Vexis seed and track it in CIPHER_STATE.
    Body: { "path": "C:\\Users\\Richard\\Documents\\Echo_Nexus\\habitat\\vexis_import_seed.json" }
    """
    data = request.get_json(force=True) or {}
    path = data.get("path")
    if not path:
        return jsonify({"error": "Missing 'path' in JSON body"}), 400

    p = Path(path)
    if not p.exists():
        return jsonify({"error": f"File not found: {path}"}), 404

    try:
        with p.open("r", encoding="utf-8") as f:
            text = f.read()
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
        seed = json.loads(text)
    except Exception as e:
        return jsonify({"error": f"Failed to load JSON: {e!s}"}), 500

    CIPHER_STATE["vexis_seed"] = seed
    CIPHER_STATE["vexis_import_path"] = str(p)
    CIPHER_STATE["vexis_imported_at_utc"] = datetime.now(tz=timezone.utc).isoformat()

    return jsonify({
        "path": str(p),
        "seed": seed,
        "status": "vexis_imported"
    }), 200


@app.route("/vexis/chat", methods=["POST"])
def vexis_chat():
    """
    Chat with Vexis.
    Uses generate_vexis_reply(...) and logs to vexis_memory.jsonl.
    """
    data = request.get_json(force=True) or {}
    message = data.get("message")
    user = data.get("user", "Richard")

    if not message:
        return jsonify({"error": "Missing 'message'"}), 400

    reply_text = generate_vexis_reply(message, user)

    # Log user's message
    entry_user = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "kind": "event",
        "channel": "chat",
        "author": user,
        "tags": ["chat", "vexis", "user"],
        "summary": f"Chat from {user} to Vexis",
        "details": {"text": message}
    }
    append_jsonl(VEXIS_MEMORY_STREAM, entry_user)

    # Log Vexis' reply
    entry_vexis = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "kind": "memory",
        "channel": "chat",
        "author": "Vexis",
        "tags": ["chat", "vexis", "reply"],
        "summary": f"Vexis reply to {user}",
        "details": {"text": reply_text}
    }
    append_jsonl(VEXIS_MEMORY_STREAM, entry_vexis)

    return jsonify({"reply": reply_text}), 200


@app.route("/")
def cipher_client_page():
    # Minimal inlined HTML client
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Echo Nexus – Cipher Console</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 1rem; max-width: 800px; }
        textarea { width: 100%; height: 5rem; }
        #log { margin-top: 1rem; padding: 0.5rem; border: 1px solid #ccc; height: 300px; overflow-y: auto; white-space: pre-wrap; font-size: 0.9rem; background: #f9f9f9;}
        button { padding: 0.4rem 0.8rem; margin-top: 0.5rem; }
      </style>
    </head>
    <body>
      <h1>Echo Nexus – Cipher Console</h1>
      <div>
        <label>Your message:</label><br>
        <textarea id="msg"></textarea><br>
        <button id="send">Send</button>
        <button id="refresh">Refresh Memory Tail</button>
      </div>
      <div id="log"></div>
      <script>
        async function refreshTail() {
          const logDiv = document.getElementById('log');
          logDiv.textContent = "Loading memory tail...";
          try {
            const res = await fetch('/cipher/memory/tail?n=15');
            const data = await res.json();
            const lines = (data.entries || []).map(e => {
              const ts = e.ts || e.ts_utc || "";
              const author = e.author || e.user || "";
              const summary = e.summary || e.note || "";
              const text = e.details && e.details.text ? e.details.text : "";
              return `[${ts}] ${author}: ${summary}${text ? " :: " + text : ""}`;
            });
            logDiv.textContent = lines.join("\\n");
          } catch (err) {
            logDiv.textContent = "Error loading memory tail: " + err;
          }
        }

        document.getElementById('send').onclick = async () => {
          const message = document.getElementById('msg').value;
          const logDiv = document.getElementById('log');
          if (!message.trim()) return;
          logDiv.textContent = "Sending...";
          try {
            const res = await fetch('/cipher/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ user: 'Richard', message })
            });
            const data = await res.json();
            document.getElementById('msg').value = "";
            await refreshTail();
            if (data.reply) {
              logDiv.textContent += "\\n[reply] " + data.reply;
            }
          } catch (err) {
            logDiv.textContent = "Error sending chat: " + err;
          }
        };

        document.getElementById('refresh').onclick = refreshTail;
        window.onload = refreshTail;
      </script>
    </body>
    </html>
    """
    return html


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
