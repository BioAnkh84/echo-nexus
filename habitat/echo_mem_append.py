import json
import socket
from datetime import datetime
import os
import sys
from pathlib import Path


def main():
    # Combine all CLI args into one note string
    if len(sys.argv) < 2:
        print("Usage: echo_mem_append.py <note text>")
        sys.exit(1)

    note_text = " ".join(sys.argv[1:]).strip()
    if not note_text:
        print("Error: empty note text.")
        sys.exit(1)

    # Figure out Echo Nexus root from this script's location:
    # this file is in: Echo_Nexus/habitat/echo_mem_append.py
    # root is one level up
    script_path = Path(__file__).resolve()
    root = script_path.parents[1]  # Echo_Nexus
    mem_stream = root / "memory" / "streams" / "root_memory.jsonl"

    # Make sure the directory exists
    mem_stream.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts_utc": datetime.utcnow().isoformat() + "Z",
        "host": socket.gethostname(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER"),
        "source": "echo_mem_append.py",
        "note": note_text,
    }

    # Append as one-line JSONL
    with mem_stream.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Echo back what we wrote so shell sees it
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
