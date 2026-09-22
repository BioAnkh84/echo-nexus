"""Pure, partial Charter assessment. No grants, tools, writes or live integration."""
import math

CHARTER_SHA256 = '206ffa82ad3feebe54648ebce8cb7ef8c89e11b0cad78b4795adfea1dfe68c51'


def assess(proposal, *, now):
    """Evaluate supplied measurement claims, never authenticate them or permit work.

    now is an explicit caller-provided evaluation time for reproducible tests.
    It is not taken from proposal text. Evidence expiry is not grant expiry.
    """
    reasons = []
    measurements = 'UNKNOWN'
    posture = 'PAUSE'

    def result():
        return {'schema_version': 1, 'assessment_kind': 'offline_partial_measurement_review',
                'charter_sha256': CHARTER_SHA256, 'decision': posture,
                'measurement_state': measurements, 'difference_makers': reasons,
                'authority_evaluated': False, 'execution_authorized': False,
                'execution_attempted': False, 'cs_state_evaluated': False,
                'evidence_truth_verified': False}

    if type(now) is not int or now < 0:
        raise ValueError('Explicit nonnegative evaluation time required')
    keys = {'schema_version', 'proposal_id', 'action', 'resource', 'purpose',
            'charter_sha256', 'measurements', 'evidence'}
    if not isinstance(proposal, dict) or set(proposal) != keys:
        reasons.append('invalid_contract_or_unrecognized_fields')
        return result()
    if type(proposal['schema_version']) is not int or proposal['schema_version'] != 1:
        reasons.append('unsupported_schema')
        return result()
    if proposal['charter_sha256'] != CHARTER_SHA256:
        reasons.append('policy_identity_mismatch')
        return result()
    if any(not isinstance(proposal[k], str) or not proposal[k].strip() or len(proposal[k]) > 512
           for k in ('proposal_id', 'action', 'resource', 'purpose')):
        reasons.append('missing_or_oversized_proposal_identity')
        return result()
    values = proposal['measurements']
    if not isinstance(values, dict) or set(values) != {'rho', 'gamma_0', 'delta'}:
        reasons.append('missing_or_unrecognized_measurements')
        return result()
    if (type(values['gamma_0']) is not int or values['gamma_0'] not in (0, 1)
            or any(type(values[k]) not in (int, float) or not 0 <= values[k] <= 1
                   or not math.isfinite(values[k]) for k in ('rho', 'delta'))):
        reasons.append('invalid_measurement_domain')
        return result()
    # Never soften a supplied hard denial because another input is stale/missing.
    if values['gamma_0'] == 0:
        posture = 'ABORT'; reasons.append('supplied_consent_or_scope_denied')
    if values['delta'] > 0.40:
        posture = 'ABORT'; reasons.append('supplied_drift_above_0_40')
    evidence = proposal['evidence']
    valid = (isinstance(evidence, dict) and set(evidence) == {'source_ref', 'observed_at', 'valid_until'}
             and isinstance(evidence['source_ref'], str) and bool(evidence['source_ref'].strip())
             and len(evidence['source_ref']) <= 512
             and type(evidence['observed_at']) is int and type(evidence['valid_until']) is int
             and 0 <= evidence['observed_at'] <= now < evidence['valid_until'])
    if not valid:
        reasons.append('missing_invalid_or_stale_evidence_metadata')
        return result()
    if posture == 'ABORT':
        measurements = 'REJECTED'
        return result()
    if values['rho'] < 0.70:
        reasons.append('confidence_below_0_70')
    if values['delta'] > 0.30:
        reasons.append('drift_attention_band')
    if reasons:
        measurements = 'ATTENTION_REQUIRED'
    else:
        measurements = 'WITHIN_BASELINE_THRESHOLDS'
    reasons.extend(['applicable_authority_not_evaluated', 'full_gate_cs_state_not_evaluated'])
    return result()
