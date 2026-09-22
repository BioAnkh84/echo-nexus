"""Read-only snapshot verifier, independent of server and receipt writer imports.

Checks recorded exchange consistency, never human authority or task correctness.
"""
import argparse
import hashlib
import json
import os
import re
import stat

LIMIT = 8 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceError(Exception):
    pass


def require(condition):
    if not condition:
        raise EvidenceError("Evidence is incomplete, inconsistent or unsupported")


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def invalid_constant(_value):
    raise EvidenceError("Nonstandard JSON constant")


def parse(raw):
    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def lines(raw):
    require(isinstance(raw, bytes) and len(raw) <= LIMIT and bool(raw) and raw.endswith(b"\n"))
    return raw.splitlines(keepends=True)


def verify_exchange(ledger, memory, response, request_id, expected_tip, orientation=None):
    """Inputs must be separately authorized, quiescent evidence snapshots.

    An expected tip is required but its provenance cannot be authenticated here.
    No runtime state, grant, receipt or memory is modified by this function.
    """
    try:
        require(isinstance(expected_tip, str) and bool(HEX.fullmatch(expected_tip)))
        require(isinstance(request_id, str) and bool(request_id))
        selected = []
        previous = '0' * 64
        event_ids = set()
        for sequence, line in enumerate(lines(ledger), 1):
            require(len(line) <= 16384)
            event = parse(line)
            require(isinstance(event, dict))
            saved = event.pop('hash_self')
            require(type(event['schema_version']) is int and event['schema_version'] == 1)
            require(type(event['sequence']) is int and event['sequence'] == sequence)
            require(event['hash_prev'] == previous and saved == fingerprint(event))
            require(isinstance(event['event_id'], str) and event['event_id'] not in event_ids)
            event_ids.add(event['event_id'])
            previous = saved
            if event.get('request_id') == request_id:
                selected.append(dict(event, hash_self=saved))
        require(previous == expected_tip and bool(selected))
        identity = ('action', 'grant_id', 'grant_fingerprint', 'subject', 'purpose')
        require(all(isinstance(selected[0][key], str) and selected[0][key] for key in identity))
        require(all(all(e[key] == selected[0][key] for key in identity) for e in selected))
        action = selected[0]['action']
        require(action in {'cipher.chat', 'vexis.chat', 'echo.handshake'})
        resource = 'cipher.memory' if action == 'cipher.chat' else 'vexis.memory'
        names = [e['event'] for e in selected]
        backend = selected[1]['details']['backend']
        require(backend in {'local_stub', 'openai', 'local_model'})
        prefix = ['authority_evaluated', 'generation_attempted']
        if backend == 'openai':
            prefix.append('provider_attempted')
        elif backend == 'local_model':
            prefix.append('local_model_attempted')
        require(names == prefix + ['generation_result', 'memory_append_attempted',
            'memory_append_result', 'memory_append_attempted', 'memory_append_result', 'execution_result'])
        admission = selected[0]['details']
        require(admission['decision'] == 'permitted_under_grant'
                and admission['gate_measurement'] == 'not_performed')
        if backend == 'openai':
            require(selected[2]['details']['destination'] == 'openai')
        orientation_matched = False
        if backend == 'local_model' and 'orientation_sha256' in selected[2]['details']:
            details = selected[2]['details']
            require(isinstance(orientation, bytes) and len(orientation) <= 32768)
            require(hashlib.sha256(orientation).hexdigest() == details['orientation_sha256'])
            package = parse(orientation)
            require([n['id'] for n in package['notes']] == details['orientation_note_ids'])
            orientation_matched = True
        else:
            require(orientation is None)
        generated = selected[len(prefix)]['details']
        completed = selected[-1]['details']
        transmission = 'response_received' if backend == 'openai' else 'not_attempted'
        for outcome, state in ((generated, 'returned_unverified'), (completed, 'completed_unverified')):
            require(outcome['state'] == state and outcome['backend'] == backend
                    and outcome['transmission'] == transmission
                    and outcome['verification'] == 'not_performed' and outcome.get('reason') is None)
        require(completed['delivery'] == 'unknown')
        memory_lines = lines(memory)
        entries = [parse(line) for line in memory_lines]
        require(all(isinstance(entry, dict) for entry in entries))
        hashes = [hashlib.sha256(line).hexdigest() for line in memory_lines]
        positions = []
        for offset in (len(prefix) + 1, len(prefix) + 3):
            attempt, result = selected[offset]['details'], selected[offset + 1]['details']
            require(attempt['resource'] == result['resource'] == resource)
            value = result['entry_sha256']
            require(value == attempt['entry_sha256'] and hashes.count(value) == 1)
            require(result['state'] == 'write_returned_unverified' and result['verification'] == 'not_performed')
            position = hashes.index(value)
            entry = entries[position]
            require(entry['authorization'] == {key: selected[0][key] for key in ('grant_id', 'subject', 'purpose')})
            positions.append(position)
        require(positions[0] < positions[1])
        require(len(response) <= LIMIT)
        payload = parse(response)
        require(isinstance(payload, dict))
        reference = payload.pop('receipt')
        require(reference == {'request_id': request_id, 'tip': selected[-1]['hash_self']})
        require(fingerprint(payload) == completed['response_sha256'])
        reply = payload['reply_text' if action == 'echo.handshake' else 'reply']
        require(isinstance(reply, str) and hashlib.sha256(reply.encode()).hexdigest() == generated['output_sha256'])
        require(payload['execution'] == {key: generated[key] for key in
                ('backend', 'transmission', 'reason', 'verification')} | {'state': 'completed_unverified'})
        recorded_reply = entries[positions[1]]['details']['text']
        require(recorded_reply == reply)
        return {'state': 'exchange_evidence_consistent', 'request_id': request_id,
                'chain_tip': previous, 'expected_tip_matched': True,
                'memory_entries_matched': 2, 'response_matched': True,
                'orientation_snapshot_matched': orientation_matched,
                'authority_verified': False, 'task_success_verified': False}
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError, RecursionError):
        raise EvidenceError("Malformed or unsupported evidence") from None


def snapshot(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= LIMIT)
        raw = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        require(len(raw) <= LIMIT)
        return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ledger', 'memory', 'response', 'request-id', 'expected-tip'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--orientation', help='Required snapshot when receipt uses historical orientation')
    args = parser.parse_args()
    try:
        result = verify_exchange(snapshot(args.ledger), snapshot(args.memory), snapshot(args.response),
                                 args.request_id, args.expected_tip,
                                 orientation=snapshot(args.orientation) if args.orientation else None)
    except (EvidenceError, OSError):
        print(json.dumps({'state': 'not_verified', 'task_success_verified': False,
                          'error': 'Evidence unavailable, incomplete, inconsistent or unsupported'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
