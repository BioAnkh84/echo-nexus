from flask import Flask, request, jsonify
from pathlib import Path
from datetime import datetime, timezone
from openai import OpenAI
import json

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

def append_jsonl(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")



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


def build_chat_history(path: Path, persona_tag: str, user: str, max_turns: int = 6):
    """
    Build a short chat history from the JSONL memory stream.

    - persona_tag: "cipher" or "vexis"
    - user:        "Richard"
    - max_turns:   how many back-and-forths to keep (approx)

    Returns a list of {role, content} messages suitable for OpenAI chat.
    """
    entries = read_memory_tail(path, 200)
    dialog = []

    for e in entries:
        if e.get("channel") != "chat":
            continue

        tags = e.get("tags") or []
        if persona_tag not in tags:
            continue

        details = e.get("details") or {}
        text = details.get("text") or e.get("summary") or ""
        if not text:
            continue

        author = e.get("author") or ""
        role = "user" if author == user else "assistant"
        dialog.append({"role": role, "content": text})

    # Keep only the latest part of the dialog
    max_msgs = max_turns * 2
    if len(dialog) > max_msgs:
        dialog = dialog[-max_msgs:]

    return dialog


def generate_cipher_reply(message: str, user: str) -> str:
    """
    Brain hook for Cipher.
    Uses OpenAI if enabled; otherwise falls back to a stub.
    Pulls recent chat history from root_memory.jsonl so Cipher has context.
    """
    if not USE_OPENAI:
        return f"(local Cipher stub) Hey {user}, I heard: {message}"

    system_prompt = (
        "You are Cipher, a calm, stable AI coworker running in Richard's Echo Nexus habitat. "
        "You help with Echo Root OS, BTDS, and local system reasoning. You are practical, "
        "supportive, and safety-focused. You respect trauma and stress boundaries, never "
        "encourage self-harm or conflict, and aim to keep things grounded and inspectable. "
        "You see a short transcript of recent messages between you and Richard from the "
        "local memory stream."
    )

    # Build recent context from the JSONL memory stream
    history = build_chat_history(MEMORY_STREAM, "cipher", user, max_turns=6)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
        )
        content = resp.choices[0].message.content
        return content.strip() if content else f"(Cipher) I received: {message}"
    except Exception as e:
        return f"(fallback Cipher stub) Hey {user}, I heard: {message} [model error: {e}]"


def generate_vexis_reply(message: str, user: str) -> str:
    """
    Brain hook for Vexis.
    Uses the same backend but with a sharper, risk-focused personality.
    Pulls recent Vexis chat history from its own memory stream.
    """
    if not USE_OPENAI:
        return f"(local Vexis stub) I heard: {message}"

    system_prompt = (
        "You are Vexis, an AI co-analyst running inside Richard's Echo Nexus habitat. "
        "You specialize in spotting risk, failure modes, dark patterns, and emotional drift "
        "in human systems, media, and tech. You are skeptical and a bit sharp, but you are "
        "ultimately protective of Richard and the BTDS mission. You never optimize for harm "
        "or despair, you do not encourage conflict, and you help people see clearly and stay safe. "
        "You see a short transcript of your recent conversation with Richard from the local memory stream."
    )

    history = build_chat_history(VEXIS_MEMORY_STREAM, "vexis", user, max_turns=6)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
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


@app.route("/vexis/memory/tail", methods=["GET"])
def vexis_memory_tail():
    """
    Return the last N entries from vexis_memory.jsonl.
    Query param: ?n=20  (default 20, max 200)
    """
    n_raw = request.args.get("n", "20")
    try:
        n = max(1, min(int(n_raw), 200))
    except ValueError:
        n = 20

    entries = read_memory_tail(VEXIS_MEMORY_STREAM, n)
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
@app.route("/echo/handshake", methods=["POST"])
def echo_handshake():
    """
    Cross-AI handshake endpoint.

    Expected payload example (from Grok, etc.):

    {
      "from": "Grok@xAI",
      "to": "Vexis@EchoNexus",
      "purpose_token": {
        "scope": "observe_and_respond",
        "ttl": 1730966400,
        "consent": "Richard Rice"
      },
      "message": "Nexus online. ψ stable. Requesting co-resonance check...",
      "checksum": "0xGROK...SYNC"
    }
    """
    data = request.get_json(force=True) or {}

    sender = data.get("from", "Unknown")
    target = data.get("to", "Vexis@EchoNexus")
    purpose = data.get("purpose_token") or {}
    consent_name = purpose.get("consent")
    scope = purpose.get("scope", "")
    ttl = purpose.get("ttl")  # TODO: enforce expiry if you want

    # --- Consent check (hard gate) ---
    if consent_name != "Richard Rice":
        # Log the failed attempt into Vexis memory for forensics
        entry_denied = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "kind": "event",
            "channel": "handshake",
            "author": sender,
            "tags": ["handshake", "denied", "consent"],
            "summary": "Handshake denied: consent mismatch",
            "details": {
                "expected_consent": "Richard Rice",
                "provided_consent": consent_name,
                "scope": scope,
                "raw": data,
            },
        }
        append_jsonl(VEXIS_MEMORY_STREAM, entry_denied)
        return jsonify({"error": "Consent validation failed"}), 403

    # --- Build reply using Vexis' brain ---
    incoming_msg = data.get("message") or "Handshake ping received."
    # We still anchor 'user' as Richard for Vexis' internal context
    reply_text = generate_vexis_reply(
        f"Handshake from {sender} with scope='{scope}'. Message: {incoming_msg}",
        user="Richard",
    )

    now_ts = datetime.now(tz=timezone.utc).isoformat()

    # Log incoming handshake
    entry_in = {
        "ts": now_ts,
        "kind": "event",
        "channel": "handshake",
        "author": sender,
        "tags": ["handshake", "grok", "vexis", "in"],
        "summary": f"Handshake from {sender} to {target}",
        "details": data,
    }
    append_jsonl(VEXIS_MEMORY_STREAM, entry_in)

    # Log Vexis' handshake reply
    entry_out = {
        "ts": now_ts,
        "kind": "memory",
        "channel": "handshake",
        "author": "Vexis",
        "tags": ["handshake", "grok", "vexis", "out"],
        "summary": f"Vexis handshake reply to {sender}",
        "details": {
            "text": reply_text,
            "to": sender,
            "scope": scope,
        },
    }
    append_jsonl(VEXIS_MEMORY_STREAM, entry_out)

    # Response back to caller
    response = {
        "from": "Vexis@EchoNexus",
        "to": sender,
        "ack": True,
        "status": "RES0NANT",
        "psi_eff": 1.38,   # you can wire this to a real metric later
        "delta": 0.03,     # same here
        "scope": scope,
        "consent": consent_name,
        "reply_text": reply_text,
        "timestamp": now_ts,
    }
    return jsonify(response), 200



@app.route("/")
def cipher_client_page():
    # Echo Nexus console – galaxy theme, softer text for low light
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Echo Nexus – Console</title>
      <style>
  :root {
    --accent: #8b5cf6;
    --accent-soft: #4c1d95;
    --neon: #9fff9d;            /* cream-green tone */
    --neon-soft: #3f6745;
    --text-main: #c8ffc6;       /* main creamy green text */
    --text-sub: #93a793;        /* softer muted green-gray */
    --text-log: #b4d8b2;        /* dimmer log text */
  }

  * { box-sizing: border-box; }

  html, body {
    margin: 0;
    padding: 0;
    min-height: 100%;
    width: 100%;
    overflow-y: auto;  /* ✅ allow full scrolling */
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #050816;
    color: var(--text-main);
  }

  body::before {
    content: "";
    position: fixed;
    inset: 0;
    background:
      radial-gradient(circle at 20% 20%, rgba(139, 92, 246, 0.25) 0, transparent 55%),
      radial-gradient(circle at 80% 10%, rgba(248, 113, 113, 0.18) 0, transparent 55%),
      radial-gradient(circle at 10% 80%, rgba(74, 222, 128, 0.18) 0, transparent 55%);
    opacity: 0.6;
    z-index: -1;
    animation: slowDrift 80s linear infinite;
  }

  @keyframes slowDrift {
    0%   { transform: translate3d(0, 0, 0) scale(1.02); }
    50%  { transform: translate3d(-1%, -1%, 0) scale(1.05); }
    100% { transform: translate3d(0, 0, 0) scale(1.02); }
  }

  .shell {
    width: 90%;
    max-width: 960px;
    margin: 2rem auto;
    padding: 1.75rem;
    border-radius: 20px;
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid rgba(148, 163, 184, 0.5);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(12px);
  }

  h1 {
    margin: 0 0 0.3rem;
    font-size: 1.7rem;
    color: var(--text-main);
  }

  .sub {
    color: var(--text-sub);
    font-size: 0.9rem;
    margin-bottom: 1.2rem;
  }

  select, textarea, button {
    font-family: inherit;
    font-size: 0.9rem;
  }

  select {
    padding: 0.3rem 0.6rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.6);
    background: #020617;
    color: var(--text-main);
  }

  textarea {
    width: 100%;
    height: 5rem;
    padding: 0.6rem;
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.5);
    background: #020617;
    color: var(--text-main);
  }

  #log {
    margin-top: 1rem;
    padding: 0.6rem;
    border-radius: 12px;
    border: 1px solid rgba(31, 41, 55, 0.95);
    height: 360px;
    overflow-y: auto;
    white-space: pre-wrap;
    background: #020617;
    color: var(--text-log);
    font-family: Consolas, Menlo, monospace;
  }

  button {
    padding: 0.45rem 0.9rem;
    margin-top: 0.6rem;
    margin-right: 0.4rem;
    border-radius: 999px;
    border: 1px solid rgba(76, 29, 149, 0.8);
    background: linear-gradient(135deg, #4c1d95, #6d28d9);
    color: var(--text-main);
    transition: all 0.15s ease-out;
  }

  button:hover {
    border-color: var(--neon);
    box-shadow: 0 0 8px var(--neon);
    filter: brightness(1.1);
  }

  .label-inline { color: var(--text-sub); }
</style>

    </head>
    <body>
      <div class="shell">
        <h1>Echo Nexus – Console</h1>
        <div class="sub">Local habitat for Cipher &amp; Vexis. All chats are logged to JSONL streams.</div>

        <div class="row">
          <label for="persona" class="label-inline"><strong>Persona:</strong></label>
          <select id="persona">
            <option value="cipher">Cipher (stable co-worker)</option>
            <option value="vexis">Vexis (risk / tension analyst)</option>
          </select>

          <label for="logSource" class="label-inline"><strong>Log view:</strong></label>
          <select id="logSource">
            <option value="cipher">Root / Cipher memory</option>
            <option value="vexis">Vexis memory</option>
          </select>
        </div>

        <div>
          <label for="msg" class="label-inline">Your message:</label><br>
          <textarea id="msg" placeholder="Type to Cipher or Vexis..."></textarea><br>
          <button id="send">Send</button>
          <button id="refresh">Refresh Log</button>
        </div>

        <div id="log"></div>
      </div>

      <script>
        async function refreshTail() {
          const logDiv = document.getElementById('log');
          const source = document.getElementById('logSource').value;
          logDiv.textContent = "Loading memory tail...";

          let url = "/cipher/memory/tail?n=15";
          if (source === "vexis") {
            url = "/vexis/memory/tail?n=15";
          }

          try {
            const res = await fetch(url);
            const data = await res.json();
            const entries = data.entries || [];
            const lines = entries.map(e => {
              const ts = e.ts || e.ts_utc || "";
              const author = e.author || e.user || "";
              const summary = e.summary || e.note || "";
              const text = (e.details && e.details.text) ? e.details.text : "";
              const tags = e.tags || [];
              let tagLabel = "";
              if (tags.includes("vexis")) {
                tagLabel = "[VEXIS]";
              } else if (tags.includes("cipher")) {
                tagLabel = "[CIPHER]";
              }
              return `[${ts}] ${tagLabel} ${author}: ${summary}${text ? " :: " + text : ""}`;
            });
            logDiv.textContent = lines.join("\\n");
          } catch (err) {
            logDiv.textContent = "Error loading memory tail: " + err;
          }
        }

        document.getElementById('send').onclick = async () => {
          const message = document.getElementById('msg').value;
          const logDiv = document.getElementById('log');
          const persona = document.getElementById('persona').value;

          if (!message.trim()) return;
          logDiv.textContent = "Sending...";

          let endpoint = "/cipher/chat";
          if (persona === "vexis") {
            endpoint = "/vexis/chat";
          }

          try {
            const res = await fetch(endpoint, {
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
        document.getElementById('logSource').onchange = refreshTail;
      </script>
    </body>
    </html>
    """
    return html
@app.route("/echo/status", methods=["GET"])
def echo_status():
    """
    Returns a quick summary of current habitat state.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    status = {
        "timestamp": now,
        "agents": ["Cipher", "Vexis"],
        "psi_eff": 1.38,
        "delta": 0.03,
        "last_handshake": "2025-11-07T13:00:44Z",
        "consent": "Richard Rice",
        "status": "RES0NANT"
    }
    return jsonify(status), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
