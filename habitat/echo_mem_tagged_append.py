import json
import socket
from datetime import datetime
import os
import sys
from pathlib import Path

def main():
    # Usage: echo_mem_tagged_append.py <tag> <note text...>
    if len(sys.argv) < 3:
        print("Usage: echo_mem_tagged_append.py <tag> <note text>")
        sys.exit(1)

    tag = sys.argv[1].strip()
    note_text = " ".join(sys.argv[2:]).strip()

    if not tag:
        print("Error: empty tag.")
        sys.exit(1)
    if not note_text:
        print("Error: empty note text.")
        sys.exit(1)

    # Locate Echo Nexus root (one level up from habitat/)
    script_path = Path(__file__).resolve()
    root = script_path.parents[1]
    mem_stream = root / "memory" / "streams" / "root_memory.jsonl"
    mem_stream.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts_utc": datetime.utcnow().isoformat() + "Z",
        "host": socket.gethostname(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER"),
        "source": "echo_mem_tagged_append.py",
        "tag": tag,
        "note": note_text,
    }

    with mem_stream.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps(entry, ensure_ascii=False))

if __name__ == "__main__":
    main()
