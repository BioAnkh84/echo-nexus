"""Bounded historical summaries. Package labels never confer runtime authority."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

LIMIT = 32768

class OrientationError(ValueError):
    pass

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OrientationError('Duplicate key')
        result[key] = value
    return result

def validate(raw, expected):
    if not isinstance(raw, bytes) or len(raw) > LIMIT or not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise OrientationError('Invalid bounded package')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise OrientationError('Package digest mismatch')
    try:
        data = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(OrientationError('Invalid constant')))
        if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['record_type'] != 'reviewed_historical_orientation':
            raise OrientationError('Unsupported package')
        notes = data['notes']
        if not isinstance(notes, list) or not 1 <= len(notes) <= 3:
            raise OrientationError('Note count limit')
        ids = set()
        for note in notes:
            if (not isinstance(note['id'], str) or not re.fullmatch('[a-z0-9_]{1,80}', note['id']) or note['id'] in ids
                    or not isinstance(note['text'], str) or not note['text'].strip()
                    or note['authority'] != 'orientation_only_not_permission'
                    or not isinstance(note['source_lines'], list) or not note['source_lines']
                    or any(type(n) is not int or n < 1 for n in note['source_lines'])):
                raise OrientationError('Invalid note')
            ids.add(note['id'])
        if sum(len(n['text']) for n in notes) > 4096:
            raise OrientationError('Text limit')
        refs = data['source_refs']
        if not isinstance(refs, list) or any(not any(r['line'] == n for r in refs) for note in notes for n in note['source_lines']):
            raise OrientationError('Missing source locator')
        return [{'id': n['id'], 'text': n['text']} for n in notes]
    except (KeyError, TypeError, UnicodeError, ValueError, RecursionError) as error:
        raise OrientationError('Invalid orientation package') from error

def load(path, expected):
    if not Path(path).is_absolute():
        raise OrientationError('Absolute package path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > LIMIT:
            raise OrientationError('Regular bounded file required')
        raw = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise OrientationError('Package changed during read')
    validate(raw, expected)
    return raw
