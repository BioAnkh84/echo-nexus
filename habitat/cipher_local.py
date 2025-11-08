import sys
import json
import datetime
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEM_STREAM = ROOT / "memory" / "streams" / "root_memory.jsonl"
PROFILE_PATH = ROOT / "memory" / "profiles" / "cipher_profile.json"

def now_utc():
    return datetime.datetime.utcnow().isoformat() + "Z"

def get_host():
    return os.getenv("COMPUTERNAME") or getattr(
        os,
        "uname",
        lambda: type("U", (), {"nodename": "unknown"})()
    )().nodename

def get_user():
    return os.getenv("USERNAME") or os.getenv("USER")

def load_profile():
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def tail_mem(n=10):
    if not MEM_STREAM.exists():
        return []
    text = MEM_STREAM.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    tail = lines[-n:]
    out = []
    for line in tail:
        try:
            obj = json.loads(line)
            out.append(obj)
        except Exception:
            out.append({"raw": line})
    return out

def cmd_ping():
    return {
        "ts_utc": now_utc(),
        "status": "ok",
        "host": get_host(),
        "user": get_user(),
        "echo_root": str(ROOT),
    }

def cmd_state():
    return {
        "ts_utc": now_utc(),
        "host": get_host(),
        "user": get_user(),
        "echo_root": str(ROOT),
        "profile": load_profile(),
        "recent_memories": tail_mem(10),
        "snapshot": None,
    }

def cmd_reflect(message: str):
    mems = tail_mem(10)
    notes = []
    for m in mems:
        if isinstance(m, dict):
            if "note" in m:
                notes.append(m["note"])
            elif "summary" in m:
                notes.append(m["summary"])
    return {
        "ts_utc": now_utc(),
        "echo_root": str(ROOT),
        "input": message,
        "recent_memory_notes": notes,
        "meta": {
            "description": "Local Cipher reflection stub. Replace/augment with LLM logic."
        },
    }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no command"}, ensure_ascii=False))
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "ping":
        out = cmd_ping()
    elif cmd == "state":
        out = cmd_state()
    elif cmd == "reflect":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "no message"}, ensure_ascii=False))
            sys.exit(1)
        msg = " ".join(sys.argv[2:])
        out = cmd_reflect(msg)
    else:
        print(json.dumps({"error": f"unknown command: {cmd}"}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
