from orientation import validate as validate_orientation, OrientationError
from flask import Flask, request, jsonify, g
from pathlib import Path, PureWindowsPath
from datetime import datetime, timezone
import json
import os
import time
import hashlib
import uuid
from receipts import ReceiptError, append_event, digest
from local_model import generate as generate_local, LocalFailure, validate_context
from outcomes import BackendFailure, ExecutionOutcome
from authority import AuthorityDenied, authorize, read_import

app = Flask(__name__)

# --- Model / brain config ---
def enabled(name):
    # Capability switch only; an applicable operator-provisioned grant is also required.
    return os.environ.get(name, "0") == "1"


def data_root(value):
    if not value:
        return None
    path = Path(value)
    if PureWindowsPath(value).drive or not path.is_absolute():
        raise ValueError("ECHO_NEXUS_ROOT must be an absolute POSIX path")
    return path


USE_OPENAI = enabled("ECHO_NEXUS_ENABLE_OPENAI")
USE_LOCAL = enabled("ECHO_NEXUS_ENABLE_LOCAL_MODEL")
LOCAL_MODEL_PATH = data_root(os.environ.get("ECHO_NEXUS_LOCAL_MODEL_PATH"))
if USE_LOCAL and (USE_OPENAI or LOCAL_MODEL_PATH is None):
    raise ValueError("Local backend needs an explicit model path and OpenAI disabled")
SEND_MEMORY = enabled("ECHO_NEXUS_SEND_MEMORY_TO_OPENAI")
DATA_ROUTES = enabled("ECHO_NEXUS_ENABLE_DATA_ROUTES")
OPENAI_MODEL = "gpt-4.1-mini"
client = None
GRANTS_FILE = data_root(os.environ.get("ECHO_NEXUS_GRANTS_FILE"))
ECHO_ROOT = data_root(os.environ.get("ECHO_NEXUS_ROOT"))
if DATA_ROUTES and ECHO_ROOT is None:
    raise ValueError("Protected routes require explicit ECHO_NEXUS_ROOT")
MEMORY_STREAM = ECHO_ROOT / "memory" / "streams" / "root_memory.jsonl" if ECHO_ROOT else None
VEXIS_MEMORY_STREAM = ECHO_ROOT / "memory" / "streams" / "vexis_memory.jsonl" if ECHO_ROOT else None
app.config["DEBUG"] = False
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024


def get_client():
    global client
    if not USE_OPENAI:
        raise RuntimeError("External backend disabled")
    if client is None:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.openai.com/v1", max_retries=0, timeout=15.0)
    return client


# Each route action includes its documented local reads/writes. External
# disclosure and stored-memory export need separate actions in the same grant.
ROUTE_ACTIONS = {
    "cipher_import": "cipher.import",
    "cipher_memory_tail": "cipher.memory.read",
    "vexis_memory_tail": "vexis.memory.read",
    "cipher_state": "cipher.state.read",
    "cipher_log": "cipher.log",
    "cipher_chat": "cipher.chat",
    "vexis_import": "vexis.import",
    "vexis_chat": "vexis.chat",
    "echo_handshake": "echo.handshake",
}


@app.errorhandler(AuthorityDenied)
def authority_denied(_error):
    # Never echo tokens, grant files, or caller-supplied authority claims.
    payload = {"error": "No applicable authority grant", "decision": "ABORT"}
    if getattr(g, "exchange_id", None):
        payload["execution"] = {"state": "incomplete", "verification": "not_performed",
                                "effects_may_have_occurred": True}
        payload["receipt"] = receipt_reference()
    return jsonify(payload), 403


def require_authority(action=None):
    permission = authorize(GRANTS_FILE, request.headers.get("Authorization", ""),
                           request.headers.get("X-Echo-Purpose", ""),
                           action or g.route_action, data_root=ECHO_ROOT)
    if permission.fingerprint != g.permission.fingerprint:
        raise AuthorityDenied()
    if time.time() >= getattr(g, "handshake_expires_at", permission.expires_at):
        raise AuthorityDenied()
    return permission


def receipt_reference():
    return {"request_id": getattr(g, "exchange_id", None),
            "tip": getattr(g, "receipt_tip", None)}


def record_event(event, **details):
    permission = require_authority("receipt.append")
    g.receipt_tip = append_event(ECHO_ROOT, {
        "event_id": uuid.uuid4().hex, "request_id": g.exchange_id,
        "event": event, "action": g.route_action,
        "grant_id": permission.grant_id, "grant_fingerprint": permission.fingerprint,
        "subject": permission.subject, "purpose": permission.purpose,
        "details": details,
    })


def begin_exchange():
    require_authority("receipt.append")
    g.exchange_id = uuid.uuid4().hex
    record_event("authority_evaluated", decision="permitted_under_grant",
                 gate_measurement="not_performed",
                 input_sha256=hashlib.sha256(request.get_data()).hexdigest())


def run_generation(generator, *args, **kwargs):
    backend = "local_model" if USE_LOCAL else ("openai" if USE_OPENAI else "local_stub")
    record_event("generation_attempted", backend=backend)
    require_authority()
    try:
        if USE_LOCAL:
            require_authority("local.generate")
            context = getattr(g, "local_context", [])
            orientation = getattr(g, "orientation_notes", [])
            def check_local_launch():
                require_authority("local.generate")
                if orientation:
                    require_authority("local.orientation")
                if context:
                    require_authority("local.context")
            record_event("local_model_attempted", model_path=str(LOCAL_MODEL_PATH),
                         input_sha256=hashlib.sha256(args[0].encode()).hexdigest(),
                         context_entries=len(context), context_sha256=digest(context),
                         **({"orientation_sha256": g.orientation_sha256, "orientation_note_ids": [n["id"] for n in orientation]} if orientation else {}),
                         transmission="not_attempted")
            try:
                reply = generate_local(LOCAL_MODEL_PATH, args[0],
                    "Cipher" if g.route_action == "cipher.chat" else "Vexis",
                    check_local_launch, **({"context": context} if context else {}),
                    **({"orientation": orientation} if orientation else {}))
            except LocalFailure as error:
                raise BackendFailure(ExecutionOutcome("failed", "local_model", "not_attempted",
                                                      error.reason)) from None
        else:
            reply = generator(*args, **kwargs)
    except BackendFailure as failure:
        record_event("generation_result", **failure.outcome.as_dict())
        raise
    outcome = ExecutionOutcome("returned_unverified", backend,
                               "response_received" if USE_OPENAI else "not_attempted")
    record_event("generation_result", **outcome.as_dict(),
                 output_sha256=hashlib.sha256(reply.encode()).hexdigest())
    g.generation_outcome = outcome
    return reply


def complete_exchange(payload):
    previous = g.generation_outcome
    outcome = ExecutionOutcome("completed_unverified", previous.backend, previous.transmission)
    payload["execution"] = outcome.as_dict()
    # This is preparation, not evidence of actual network delivery to a client.
    record_event("execution_result", **outcome.as_dict(), response_sha256=digest(payload),
                 delivery="unknown")
    payload["receipt"] = receipt_reference()
    return jsonify(payload), 200


@app.errorhandler(BackendFailure)
def backend_failed(error):
    return jsonify({"error": "Backend did not return a usable result",
                    "execution": error.outcome.as_dict(),
                    "receipt": receipt_reference()}), (503 if error.outcome.transmission == "not_attempted" else 502)


@app.errorhandler(ReceiptError)
def receipt_failed(_error):
    return jsonify({"error": "Receipt unavailable; execution stopped",
                    "execution": {"state": "incomplete", "verification": "not_performed",
                                  "effects_may_have_occurred": True},
                    "receipt": receipt_reference()}), 503


@app.errorhandler(OSError)
def io_failed(_error):
    if getattr(g, "exchange_id", None):
        try:
            record_event("execution_incomplete", reason="io_error", effects_may_have_occurred=True,
                         verification="not_performed")
        except (ReceiptError, AuthorityDenied):
            pass  # Preserve the last event; never invent a completed receipt.
    return jsonify({"error": "I/O unavailable; execution stopped",
                    "execution": {"state": "incomplete", "verification": "not_performed",
                                  "effects_may_have_occurred": True},
                    "receipt": receipt_reference()}), 503


@app.before_request
def protect_data_routes():
    if request.endpoint in {"health", "echo_status", "cipher_client_page"}:
        return None
    if not DATA_ROUTES:
        return jsonify({"error": "Protected routes disabled"}), 403
    action = ROUTE_ACTIONS.get(request.endpoint)
    if action is None or request.method not in {"GET", "POST"}:
        raise AuthorityDenied()
    g.route_action = action
    g.permission = authorize(GRANTS_FILE, request.headers.get("Authorization", ""),
                             request.headers.get("X-Echo-Purpose", ""), action,
                             data_root=ECHO_ROOT)
    if request.method == "POST" and not isinstance(request.get_json(silent=True), dict):
        return jsonify({"error": "JSON object required"}), 400
    body = request.get_json(silent=True)
    if isinstance(body, dict) and 'orientation' in body:
        if not USE_LOCAL or action not in {"cipher.chat", "vexis.chat"}:
            return jsonify({"error": "Orientation requires local chat"}), 400
        require_authority("local.orientation")
        try:
            package = body['orientation']
            # The server accepts only the operator-pinned digest, never a client-selected pin.
            pin = os.environ.get('ECHO_NEXUS_ORIENTATION_SHA256', '')
            if not isinstance(package, str):
                raise OrientationError('Invalid package')
            g.orientation_notes = validate_orientation(package.encode('utf-8'), pin)
            g.orientation_sha256 = pin
        except OrientationError:
            return jsonify({"error": "Invalid or unpinned orientation"}), 400
    if isinstance(body, dict) and 'context' in body:
        if not USE_LOCAL or action not in {"cipher.chat", "vexis.chat"}:
            return jsonify({"error": "Context supported only for local chat"}), 400
        require_authority("local.context")
        try:
            g.local_context = validate_context(body['context'])
        except LocalFailure:
            return jsonify({"error": "Context must be at most three user/assistant pairs and 4096 characters"}), 400
    if action in {"cipher.chat", "vexis.chat", "echo.handshake"}:
        require_authority("receipt.append")
        if USE_LOCAL:
            require_authority("local.generate")
        if USE_OPENAI:
            require_authority("external.openai")
            if SEND_MEMORY:
                require_authority("memory.export")


@app.route("/healthz", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.after_request
def protect_response(response):
    # A read/operation and the HTTP disclosure are separate boundaries.
    # This cannot undo effects already completed under the earlier check.
    if (request.endpoint in ROUTE_ACTIONS and response.status_code < 400
            and getattr(g, "permission", None) is not None):
        try:
            require_authority()
        except AuthorityDenied as error:
            body, status = authority_denied(error)
            response = app.make_response((body, status))
    response.headers["Cache-Control"] = "no-store"
    return response

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
    if not DATA_ROUTES:
        raise RuntimeError("Protected writes disabled")
    permission = require_authority()
    data = dict(data, authorization={"grant_id": permission.grant_id,
                                    "subject": permission.subject,
                                    "purpose": permission.purpose})
    path = Path(path)
    line = json.dumps(data, ensure_ascii=False) + "\n"
    audited = getattr(g, "exchange_id", None) is not None
    resource = "cipher.memory" if path == MEMORY_STREAM else "vexis.memory"
    entry_hash = hashlib.sha256(line.encode()).hexdigest()
    if audited:
        record_event("memory_append_attempted", resource=resource, entry_sha256=entry_hash)
        require_authority()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
    if audited:
        record_event("memory_append_result", resource=resource, entry_sha256=entry_hash,
                     state="write_returned_unverified", verification="not_performed")



def read_memory_tail(path: Path, limit: int = 20):
    """
    Return the last `limit` JSONL entries as Python objects.
    If file doesn't exist yet, return an empty list.
    """
    if not DATA_ROUTES:
        raise RuntimeError("Protected reads disabled")
    require_authority()
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
    require_authority("memory.export")
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
    history = (build_chat_history(MEMORY_STREAM, "cipher", user, max_turns=6)
               if SEND_MEMORY and DATA_ROUTES else [])

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    require_authority("external.openai")
    try:
        backend = get_client()
    except Exception:
        raise BackendFailure(ExecutionOutcome("failed", "openai", "not_attempted",
                                              "client_initialization_failed")) from None
    require_authority("external.openai")
    record_event("provider_attempted", destination="openai", model=OPENAI_MODEL,
                 payload_sha256=digest(messages), transmission="unknown")
    require_authority("external.openai")
    try:
        resp = backend.chat.completions.create(model=OPENAI_MODEL, messages=messages)
    except Exception:
        # A timeout/error does not prove that the provider received nothing.
        raise BackendFailure(ExecutionOutcome("outcome_unknown", "openai", "unknown",
                                              "provider_request_failed")) from None
    try:
        content = resp.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("No text result")
    except (AttributeError, IndexError, TypeError, ValueError):
        raise BackendFailure(ExecutionOutcome("failed", "openai", "response_received",
                                              "invalid_provider_response")) from None
    return content.strip()


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

    history = (build_chat_history(VEXIS_MEMORY_STREAM, "vexis", user, max_turns=6)
               if SEND_MEMORY and DATA_ROUTES else [])

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    require_authority("external.openai")
    try:
        backend = get_client()
    except Exception:
        raise BackendFailure(ExecutionOutcome("failed", "openai", "not_attempted",
                                              "client_initialization_failed")) from None
    require_authority("external.openai")
    record_event("provider_attempted", destination="openai", model=OPENAI_MODEL,
                 payload_sha256=digest(messages), transmission="unknown")
    require_authority("external.openai")
    try:
        resp = backend.chat.completions.create(model=OPENAI_MODEL, messages=messages)
    except Exception:
        # A timeout/error does not prove that the provider received nothing.
        raise BackendFailure(ExecutionOutcome("outcome_unknown", "openai", "unknown",
                                              "provider_request_failed")) from None
    try:
        content = resp.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("No text result")
    except (AttributeError, IndexError, TypeError, ValueError):
        raise BackendFailure(ExecutionOutcome("failed", "openai", "response_received",
                                              "invalid_provider_response")) from None
    return content.strip()



# --- ENDPOINTS ---

def import_seed(persona):
    data = request.get_json()
    permission = require_authority()
    filename = data.get("file")
    try:
        seed = read_import(ECHO_ROOT, filename, permission)
    except AuthorityDenied:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        return jsonify({"error": "Import unavailable or invalid"}), 400
    # Parsing restores data only, never an authority grant.
    require_authority()
    prefix = "" if persona == "cipher" else "vexis_"
    CIPHER_STATE[prefix + "seed"] = seed
    CIPHER_STATE[prefix + "import_path"] = str(ECHO_ROOT / "imports" / filename)
    CIPHER_STATE[prefix + "imported_at_utc"] = datetime.now(tz=timezone.utc).isoformat()
    return jsonify({"file": filename, "seed": seed, "status": "imported"}), 200


@app.route("/cipher/import", methods=["POST"])
def cipher_import():
    return import_seed("cipher")


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
    user = g.permission.subject

    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Nonempty message string required"}), 400

    # Get a reply from Cipher's brain
    begin_exchange()
    reply_text = run_generation(generate_cipher_reply, message, user)

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

    return complete_exchange({"reply": reply_text})


@app.route("/vexis/import", methods=["POST"])
def vexis_import():
    return import_seed("vexis")


@app.route("/vexis/chat", methods=["POST"])
def vexis_chat():
    """
    Chat with Vexis.
    Uses generate_vexis_reply(...) and logs to vexis_memory.jsonl.
    """
    data = request.get_json(force=True) or {}
    message = data.get("message")
    user = g.permission.subject

    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Nonempty message string required"}), 400

    begin_exchange()
    reply_text = run_generation(generate_vexis_reply, message, user)

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

    return complete_exchange({"reply": reply_text})
@app.route("/echo/handshake", methods=["POST"])
def echo_handshake():
    """An authenticated advisory exchange; payload names never grant consent."""
    data = request.get_json()
    permission = require_authority()
    sender = data.get("from")
    target = data.get("to")
    purpose = data.get("purpose_token")
    if not isinstance(purpose, dict):
        return jsonify({"error": "Bounded purpose_token required"}), 400
    scope = purpose.get("scope")
    ttl = purpose.get("ttl")
    if (sender != permission.subject or target != "Vexis@EchoNexus"
            or scope != "echo.handshake" or type(ttl) is not int
            or not time.time() < ttl <= permission.expires_at):
        raise AuthorityDenied()
    g.handshake_expires_at = ttl
    incoming_msg = data.get("message")
    if not isinstance(incoming_msg, str) or not incoming_msg.strip():
        return jsonify({"error": "Message required"}), 400
    begin_exchange()
    reply_text = run_generation(generate_vexis_reply,
        f"Advisory handshake from {sender}. Message: {incoming_msg}", user=sender)

    now_ts = datetime.now(tz=timezone.utc).isoformat()

    # Log incoming handshake
    entry_in = {
        "ts": now_ts,
        "kind": "event",
        "channel": "handshake",
        "author": sender,
        "tags": ["handshake", "external", "vexis", "in"],
        "summary": f"Handshake from {sender} to {target}",
        "details": {"message": incoming_msg, "scope": scope, "ttl": ttl},
    }
    append_jsonl(VEXIS_MEMORY_STREAM, entry_in)

    # Log Vexis' handshake reply
    entry_out = {
        "ts": now_ts,
        "kind": "memory",
        "channel": "handshake",
        "author": "Vexis",
        "tags": ["handshake", "external", "vexis", "out"],
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
        "status": "advisory_response",
        "verification": "not_independently_verified",
        "scope": scope,
        "grant_id": permission.grant_id,
        "reply_text": reply_text,
        "timestamp": now_ts,
    }
    return complete_exchange(response)



@app.route("/")
def cipher_client_page():
    if not DATA_ROUTES:
        return "Echo Nexus: protected routes disabled. Health: /healthz", 200
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
          <label for="grantToken">Grant token:</label>
          <input id="grantToken" type="password" autocomplete="off" spellcheck="false">
          <label for="grantPurpose">Granted purpose:</label>
          <input id="grantPurpose" type="text" autocomplete="off">
          <button id="clearGrant" type="button">Clear grant</button>
        </div>
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
        document.getElementById('clearGrant').onclick = () => {
          document.getElementById('grantToken').value = '';
          document.getElementById('grantPurpose').value = '';
        };
        // Credentials remain only in these inputs; never persist or place in URLs.
        async function grantedFetch(url, options = {}) {
          const token = document.getElementById('grantToken').value;
          const purpose = document.getElementById('grantPurpose').value;
          if (!token || !purpose) throw new Error('Enter the operator-issued grant and purpose.');
          const response = await fetch(url, {
            ...options,
            credentials: 'omit',
            headers: {...(options.headers || {}),
              Authorization: 'Bearer ' + token, 'X-Echo-Purpose': purpose}
          });
          if (!response.ok) throw new Error('Request refused or failed (' + response.status + ').');
          return response;
        }

        async function refreshTail() {
          const logDiv = document.getElementById('log');
          const source = document.getElementById('logSource').value;
          logDiv.textContent = "Loading memory tail...";

          let url = "/cipher/memory/tail?n=15";
          if (source === "vexis") {
            url = "/vexis/memory/tail?n=15";
          }

          try {
            const res = await grantedFetch(url);
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
            const res = await grantedFetch(endpoint, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ message })
            });
            const data = await res.json();
            document.getElementById('msg').value = "";
            logDiv.textContent = "Response received; success has not been independently verified.";
            if (data.reply) {
              logDiv.textContent += "\\n[reply] " + data.reply;
            }
          } catch (err) {
            logDiv.textContent = "Error sending chat: " + err;
          }
        };

        document.getElementById('refresh').onclick = refreshTail;
        // Memory reads require an explicit Refresh Log action.
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
    app.run(host="127.0.0.1", port=5000, debug=False,
            use_reloader=False, load_dotenv=False)
