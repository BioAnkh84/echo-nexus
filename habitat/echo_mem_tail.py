import json
import sys
from pathlib import Path


def main():
    # Default: last 5 entries
    n = 5
    if len(sys.argv) >= 2:
        try:
            n_arg = int(sys.argv[1])
            if n_arg > 0:
                n = n_arg
        except ValueError:
            # Ignore bad input, keep default
            pass

    # Figure out Echo Nexus root from this script's location
    script_path = Path(__file__).resolve()
    root = script_path.parents[1]  # Echo_Nexus
    mem_stream = root / "memory" / "streams" / "root_memory.jsonl"

    if not mem_stream.exists():
        print(f"Memory stream not found at {mem_stream}")
        sys.exit(1)

    # Use utf-8-sig so any BOM at the start is stripped
    text = mem_stream.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    if not lines:
        print("No memory entries found.")
        sys.exit(0)

    tail = lines[-n:] if len(lines) > n else lines

    entries = []
    for line in tail:
        # Just in case there are stray BOMs or weird chars, strip BOM manually too
        line = line.lstrip("\ufeff")
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"raw": line})

    print(f"Last {len(entries)} memory entries from {mem_stream}:")
    for e in entries:
        if "raw" in e:
            # Make sure printing can't explode on weird chars
            raw = e["raw"].replace("\ufeff", "")
            print("RAW:", raw)
            continue

        ts = e.get("ts_utc", "?")
        note = e.get("note", "")
        src = e.get("source", "unknown")

        print(f"[{ts}] ({src}) {note}")


if __name__ == "__main__":
    main()
