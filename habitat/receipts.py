"""Append-only, hash-linked execution events; hashes are not approval or success.

Linux local prototype. A trusted external tip is required to detect whole-chain
rewrites or removal of a valid tail by the filesystem owner.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from datetime import datetime, timezone


MAX_LEDGER_BYTES = 8 * 1024 * 1024
MAX_EVENT_BYTES = 16384
GENESIS = "0" * 64


class ReceiptError(Exception):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("Duplicate receipt key")
        result[key] = value
    return result


def verify_bytes(raw, expected_tip=None):
    if len(raw) > MAX_LEDGER_BYTES or (raw and not raw.endswith(b"\n")):
        raise ReceiptError("Incomplete or oversized ledger")
    tip = GENESIS
    count = 0
    try:
        for line in raw.splitlines():
            if len(line) > MAX_EVENT_BYTES:
                raise ReceiptError("Oversized event")
            record = json.loads(line, object_pairs_hook=_object)
            if not isinstance(record, dict):
                raise ReceiptError("Invalid receipt")
            saved = record.pop("hash_self")
            count += 1
            if (type(record.get("schema_version")) is not int
                    or record["schema_version"] != 1
                    or type(record.get("sequence")) is not int
                    or record["sequence"] != count
                    or record.get("hash_prev") != tip
                    or saved != digest(record)):
                raise ReceiptError("Receipt chain mismatch")
            tip = saved
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ReceiptError("Invalid receipt") from None
    if expected_tip is not None and tip != expected_tip:
        raise ReceiptError("Expected tip mismatch")
    return {"events": count, "tip": tip, "chain_valid": True,
            "tip_anchored": expected_tip is not None,
            "task_success_verified": False}


def append_event(root, event):
    """Caller must validate receipt.append authority immediately before use.

    Never reset/repair/truncate a broken ledger. A failed append can leave a
    partial tail; subsequent operations fail closed until operator recovery.
    """
    if not isinstance(event, dict) or "hash_self" in event:
        raise ReceiptError("Invalid event")
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                os.mkdir("receipts", mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            directory_fd = os.open("receipts", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                   dir_fd=root_fd)
            try:
                fd = os.open("execution.jsonl", os.O_RDWR | os.O_APPEND | os.O_CREAT
                             | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory_fd)
                with os.fdopen(fd, "r+b", buffering=0) as stream:
                    info = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                            or info.st_mode & 0o077 or info.st_size > MAX_LEDGER_BYTES):
                        raise ReceiptError("Unsafe ledger")
                    # Busy writers are a refusal, never an unbounded wait.
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    raw = stream.read(MAX_LEDGER_BYTES + 1)
                    state = verify_bytes(raw)
                    record = dict(event, schema_version=1, sequence=state["events"] + 1,
                                  hash_prev=state["tip"],
                                  timestamp=datetime.now(timezone.utc).isoformat())
                    record["hash_self"] = digest(record)
                    line = canonical(record) + b"\n"
                    if len(line) > MAX_EVENT_BYTES or len(raw) + len(line) > MAX_LEDGER_BYTES:
                        raise ReceiptError("Receipt capacity reached")
                    remaining = memoryview(line)
                    while remaining:
                        written = os.write(stream.fileno(), remaining)
                        if written <= 0:
                            raise ReceiptError("Receipt write incomplete")
                        remaining = remaining[written:]
                    os.fsync(stream.fileno())
                    os.fsync(directory_fd)
                    return record["hash_self"]
            finally:
                os.close(directory_fd)
        finally:
            os.close(root_fd)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ReceiptError("Receipt unavailable") from None


def verify_file(path, expected_tip=None):
    """Read-only verification. A missing file is not a verified empty ledger."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ReceiptError("Not a regular ledger")
            fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            return verify_bytes(stream.read(MAX_LEDGER_BYTES + 1), expected_tip)
    except OSError:
        raise ReceiptError("Receipt unavailable") from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify receipt integrity, not task success")
    parser.add_argument("ledger")
    parser.add_argument("--expected-tip")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_file(args.ledger, args.expected_tip)))
    except ReceiptError as error:
        print(json.dumps({"chain_valid": False, "error": str(error)}))
        raise SystemExit(1)
