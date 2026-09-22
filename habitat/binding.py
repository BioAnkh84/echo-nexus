"""Read-only snapshot/registry binding; no execution or automatic promotion."""
import hashlib
import json
import os
from pathlib import Path
import stat

from assessment import assess
from authority import authorize

LIMIT = 65536


class BindingError(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False, ensure_ascii=True).encode()).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BindingError('Duplicate record field')
        result[key] = value
    return result


def snapshot(path):
    """Operator-selected regular file. No paths are obtained from proposal content."""
    if not Path(path).is_absolute():
        raise BindingError('Absolute evidence path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > LIMIT:
            raise BindingError('Regular bounded evidence file required')
        raw = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
        if len(raw) > LIMIT or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise BindingError('Evidence changed during read')
    return raw


def bind(proposal, *, record_path, record_sha256, source_path,
         registry_path, authorization, data_root, now):
    """All keyword arguments must come from the operator/integration, not the model.

    Reads evidence bytes separately and checks declared linkage, not their meaning.
    The grant covers only its existing action/purpose/data-root scope; no finer
    resource delegation is inferred. This function supports root-scoped proposals
    only and never returns permission to execute.
    """
    assessment = assess(proposal, now=now)
    if assessment['measurement_state'] != 'WITHIN_BASELINE_THRESHOLDS':
        raise BindingError('Proposal not eligible for this partial binding check')
    if not Path(data_root).is_absolute() or proposal['resource'] != str(data_root):
        raise BindingError('Only exact operator-selected data-root scope supported')
    # Freeze the proposal identity before any acquisition or registry calls.
    proposed_digest = fingerprint(proposal)
    permission = authorize(registry_path, authorization, proposal['purpose'], proposal['action'],
                           data_root=data_root, now=now)
    raw = snapshot(record_path)
    if not isinstance(record_sha256, str) or hashlib.sha256(raw).hexdigest() != record_sha256:
        raise BindingError('Operator-pinned evidence record mismatch')
    try:
        record = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(BindingError('Invalid constant')))
        if (not isinstance(record, dict) or set(record) != {'schema_version', 'proposal_sha256',
                'source_sha256', 'measurements', 'evidence'}
                or type(record['schema_version']) is not int or record['schema_version'] != 1
                or record['proposal_sha256'] != proposed_digest
                or fingerprint(record['measurements']) != fingerprint(proposal['measurements'])
                or fingerprint(record['evidence']) != fingerprint(proposal['evidence'])):
            raise BindingError('Evidence record does not bind this proposal')
    except (KeyError, TypeError, UnicodeError, RecursionError, ValueError) as error:
        raise BindingError('Malformed or mismatched evidence record') from error
    source = snapshot(source_path)
    source_digest = hashlib.sha256(source).hexdigest()
    if source_digest != record['source_sha256']:
        raise BindingError('Source bytes do not match evidence record')
    # Check changed registry state again. Explicit now is a snapshot evaluation
    # time, not a claim that this result remains applicable at later execution.
    after = authorize(registry_path, authorization, proposal['purpose'], proposal['action'],
                      data_root=data_root, now=now)
    if permission.fingerprint != after.fingerprint or fingerprint(proposal) != proposed_digest:
        raise BindingError('Grant or proposal changed during binding')
    return {'schema_version': 1, 'state': 'offline_binding_consistent',
            'decision': 'PAUSE', 'proposal_sha256': proposed_digest,
            'record_sha256': record_sha256, 'source_sha256': source_digest,
            'grant_id': after.grant_id, 'grant_fingerprint': after.fingerprint,
            'evaluated_at': now, 'assessment': assessment,
            'registry_scope_matched_at_evaluation_time': True,
            'human_identity_authenticated': False, 'evidence_truth_verified': False,
            'cs_state_evaluated': False, 'execution_authorized': False,
            'execution_attempted': False,
            'difference_makers': ['pinned_record_and_source_bytes_match',
                                  'registry_action_purpose_root_match',
                                  'full_gate_and_execution_boundary_not_evaluated']}
