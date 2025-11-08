import json
import sys
from pathlib import Path


def main():
    # Usage:
    #   echo_mem_search.py                      -> show last 10 entries
    #   echo_mem_search.py Nexus                -> search "Nexus" in note
    #   echo_mem_search.py Nexus Echo           -> search "Nexus" with tag="Echo"
    #
    query = ""
    tag = None

    if len(sys.argv) >= 2:
        query = sys.argv[1].strip()
    if len(sys.argv) >= 3:
        t = sys.argv[2].strip()
        if t:
            tag = t

    script_path = Path(__file__).resolve()
    root = script_path.parents[1]
    mem_stream = root / "memory" / "streams" / "root_memory.jsonl"

    if not mem_stream.exists():
        print(f"Memory stream not found at {mem_stream}")
        sys.exit(1)

    text = mem_stream.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    entries = []
    for line in lines:
        line = line.lstrip("\ufeff")
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not entries:
        print("No valid memory entries found.")
        sys.exit(0)

    # Filter by query/tag if provided
    def matches(entry):
        if query:
            note = (entry.get("note") or "").lower()
            if query.lower() not in note:
                return False
        if tag is not None:
            if entry.get("tag") != tag:
                return False
        return True

    results = [e for e in entries if matches(e)]

    # If no filters, just show last 10
    if not query and tag is None:
        results = entries[-10:]

    print(f"{len(results)} matching entries (of {len(entries)} total) in {mem_stream}:")
    for e in results:
        ts = e.get("ts_utc", "?")
        src = e.get("source", "unknown")
        t = e.get("tag")
        note = e.get("note", "")

        if t:
            print(f"[{ts}] [{t}] ({src}) {note}")
        else:
            print(f"[{ts}] ({src}) {note}")


if __name__ == "__main__":
    main()
