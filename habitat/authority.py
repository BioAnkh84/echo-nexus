"""Operator-provisioned grants for the bounded Linux HTTP development server.

The registry is the trust root, not a request body, Gate score, or receipt.
This validates possession and scope; it does not authenticate human identity.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import time


CHARTER_SHA256 = "206ffa82ad3feebe54648ebce8cb7ef8c89e11b0cad78b4795adfea1dfe68c51"
MAX_REGISTRY_BYTES = 131072
ACTIONS = frozenset({
    "cipher.import", "cipher.memory.read", "cipher.state.read", "cipher.log",
    "cipher.chat", "vexis.import", "vexis.memory.read", "vexis.chat",
    "echo.handshake", "external.openai", "memory.export", "receipt.append", "local.generate", "local.context", "local.orientation", "local.session_facts",
})


class AuthorityDenied(Exception):
    """No applicable grant; callers must stop before the next side effect."""


@dataclass(frozen=True)
class Permission:
    grant_id: str
    subject: str
    purpose: str
    actions: frozenset
    import_files: frozenset
    expires_at: int
    fingerprint: str


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityDenied()
        result[key] = value
    return result


def _invalid_constant(_value):
    raise AuthorityDenied()


def _registry(path):
    if path is None or not Path(path).is_absolute():
        raise AuthorityDenied()
    # Never follow a registry symlink or wait on a FIFO/device.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > MAX_REGISTRY_BYTES):
            raise AuthorityDenied()
        raw = stream.read(MAX_REGISTRY_BYTES + 1)
    if len(raw) > MAX_REGISTRY_BYTES:
        raise AuthorityDenied()
    data = json.loads(raw, object_pairs_hook=_unique_object,
                      parse_constant=_invalid_constant)
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data.get("schema_version") != 1
            or data.get("charter_sha256") != CHARTER_SHA256
            or not isinstance(data.get("grants"), list)):
        raise AuthorityDenied()
    return data["grants"]


def authorize(path, authorization, purpose, action, *, data_root=None, now=None):
    """Reload grants on every check; deletion/revocation/expiry fails closed."""
    try:
        if action not in ACTIONS or not isinstance(authorization, str):
            raise AuthorityDenied()
        if not authorization.startswith("Bearer "):
            raise AuthorityDenied()
        token = authorization[7:]
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token):
            raise AuthorityDenied()
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        matches = []
        grants = _registry(path)
        ids = set()
        for grant in grants:
            if not isinstance(grant, dict):
                raise AuthorityDenied()
            gid = grant.get("grant_id")
            if not isinstance(gid, str) or not gid or gid in ids:
                raise AuthorityDenied()
            ids.add(gid)
            stored = grant.get("token_sha256")
            if not isinstance(stored, str) or not re.fullmatch(r"[0-9a-f]{64}", stored):
                raise AuthorityDenied()
            if hmac.compare_digest(stored, digest):
                matches.append(grant)
        if len(matches) != 1:
            raise AuthorityDenied()
        grant = matches[0]
        if data_root is None or grant.get("data_root") != str(data_root):
            raise AuthorityDenied()
        for key in ("subject", "purpose", "human_grant_reference"):
            if not isinstance(grant.get(key), str) or not grant[key].strip():
                raise AuthorityDenied()
        if grant.get("audience") != "echo-nexus" or grant.get("revoked") is not False:
            raise AuthorityDenied()
        issued, expires = grant.get("issued_at"), grant.get("expires_at")
        current = time.time() if now is None else now
        if type(issued) is not int or type(expires) is not int or not issued <= current < expires:
            raise AuthorityDenied()
        actions = grant.get("actions")
        if (not isinstance(actions, list) or not actions
                or any(not isinstance(a, str) or a not in ACTIONS for a in actions)
                or action not in actions or purpose != grant["purpose"]):
            raise AuthorityDenied()
        imports = grant.get("import_files", [])
        if not isinstance(imports, list) or any(not valid_import_name(x) for x in imports):
            raise AuthorityDenied()
        fingerprint = hashlib.sha256(json.dumps(grant, sort_keys=True).encode()).hexdigest()
        return Permission(grant["grant_id"], grant["subject"], grant["purpose"],
                          frozenset(actions), frozenset(imports), expires, fingerprint)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise AuthorityDenied() from None


def valid_import_name(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.json", value) is not None


def read_import(root, filename, permission):
    """Read only explicitly granted regular JSON files under root/imports.

    Directory descriptors and O_NOFOLLOW prevent symlink swaps from redirecting
    the read. No directories are created by this function.
    """
    if not valid_import_name(filename) or filename not in permission.import_files:
        raise AuthorityDenied()
    limit = 1024 * 1024
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        imports_fd = os.open("imports", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=root_fd)
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=imports_fd)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                    raise ValueError("Invalid import")
                raw = stream.read(limit + 1)
        finally:
            os.close(imports_fd)
    finally:
        os.close(root_fd)
    if len(raw) > limit:
        raise ValueError("Invalid import")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Import must be an object")
    return value
