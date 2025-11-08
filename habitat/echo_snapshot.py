import json
from pathlib import Path
from datetime import datetime
import socket
import os


def main():
    script_path = Path(__file__).resolve()
    root = script_path.parents[1]

    profile_path = root / "memory" / "profiles" / "cipher_profile.json"
    mem_stream = root / "memory" / "streams" / "root_memory.jsonl"

    profile = None
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        except Exception:
            profile = None

    # Load last N memory entries
    N = 20
    memories = []
    if mem_stream.exists():
        text = mem_stream.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        tail = lines[-N:] if len(lines) > N else lines

        for line in tail:
            line = line.lstrip("\ufeff")
            try:
                memories.append(json.loads(line))
            except json.JSONDecodeError:
                memories.append({"raw": line})

    snapshot = {
        "ts_utc": datetime.utcnow().isoformat() + "Z",
        "host": socket.gethostname(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER"),
        "echo_root": str(root),
        "cipher_profile": profile,
        "recent_memories": memories,
    }

    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
