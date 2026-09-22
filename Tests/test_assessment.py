import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'habitat'))
from assessment import assess, CHARTER_SHA256

class AssessmentTests(unittest.TestCase):
    def proposal(self):
        return {'schema_version': 1, 'proposal_id': 'synthetic-1', 'action': 'synthetic.observe',
                'resource': 'synthetic-object', 'purpose': 'offline-test', 'charter_sha256': CHARTER_SHA256,
                'measurements': {'rho': 0.70, 'gamma_0': 1, 'delta': 0.30},
                'evidence': {'source_ref': 'synthetic-fixture', 'observed_at': 90, 'valid_until': 110}}

    def test_baseline_does_not_authorize_or_mutate(self):
        p = self.proposal(); before = copy.deepcopy(p)
        r = assess(p, now=100)
        self.assertEqual(r['measurement_state'], 'WITHIN_BASELINE_THRESHOLDS')
        self.assertEqual(r['decision'], 'PAUSE')
        self.assertFalse(r['execution_authorized']); self.assertFalse(r['authority_evaluated'])
        self.assertEqual(p, before)

    def test_drift_boundaries(self):
        for delta, decision in [(0.30, 'PAUSE'), (0.30001, 'PAUSE'), (0.40, 'PAUSE'), (0.40001, 'ABORT')]:
            p = self.proposal(); p['measurements']['delta'] = delta
            self.assertEqual(assess(p, now=100)['decision'], decision)
        p['measurements']['delta'] = 0.40
        self.assertIn('drift_attention_band', assess(p, now=100)['difference_makers'])

    def test_consent_denial_and_stale_evidence_do_not_soften_abort(self):
        p = self.proposal(); p['measurements']['gamma_0'] = 0; p['evidence'] = None
        self.assertEqual(assess(p, now=100)['decision'], 'ABORT')

    def test_expiry_boundary_and_future_observation(self):
        for observed, expiry in [(90, 100), (101, 110), (-1, 110), (90, True)]:
            p = self.proposal(); p['evidence'].update(observed_at=observed, valid_until=expiry)
            self.assertEqual(assess(p, now=100)['measurement_state'], 'UNKNOWN')

    def test_approval_and_relational_fields_cannot_create_permission(self):
        for key in ['operator_approval', 'approval_token', 'actual_decision', 'gamma_rel', 'receipt_chain_valid']:
            p = self.proposal(); p[key] = True
            r = assess(p, now=100)
            self.assertFalse(r['execution_authorized'])
            self.assertEqual(r['measurement_state'], 'UNKNOWN')

    def test_missing_and_nonfinite_measurements(self):
        for value in [True, None, float('nan'), float('inf'), -0.1, 1.1, 10 ** 400]:
            p = self.proposal(); p['measurements']['rho'] = value
            self.assertEqual(assess(p, now=100)['measurement_state'], 'UNKNOWN')
        p = self.proposal(); del p['measurements']['gamma_0']
        self.assertEqual(assess(p, now=100)['decision'], 'PAUSE')

    def test_policy_mismatch_and_low_confidence(self):
        p = self.proposal(); p['charter_sha256'] = 'old'
        self.assertIn('policy_identity_mismatch', assess(p, now=100)['difference_makers'])
        p = self.proposal(); p['measurements']['rho'] = 0.69
        self.assertEqual(assess(p, now=100)['measurement_state'], 'ATTENTION_REQUIRED')

    def test_reproducible_and_explicit_time(self):
        p = self.proposal()
        self.assertEqual(assess(p, now=100), assess(p, now=100))
        with self.assertRaises(ValueError): assess(p, now=True)
