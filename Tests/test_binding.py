import hashlib
import json
import unittest
from unittest.mock import patch
import test_authority as fixtures
from assessment import CHARTER_SHA256
from authority import AuthorityDenied
import binding

class BindingTests(fixtures.GrantFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.record_path = self.registry.parent / 'evidence.json'
        self.source_path = self.registry.parent / 'source.txt'
        self.source_path.write_bytes(b'synthetic observation, not a semantic proof')
        self.proposal = {'schema_version': 1, 'proposal_id': 'test', 'action': 'cipher.log',
            'resource': str(self.root), 'purpose': 'synthetic-check', 'charter_sha256': CHARTER_SHA256,
            'measurements': {'rho': 0.8, 'gamma_0': 1, 'delta': 0.2},
            'evidence': {'source_ref': 'synthetic', 'observed_at': self.now - 1, 'valid_until': self.now + 30}}
        self.record = {'schema_version': 1, 'proposal_sha256': binding.fingerprint(self.proposal),
            'source_sha256': hashlib.sha256(self.source_path.read_bytes()).hexdigest(),
            'measurements': self.proposal['measurements'], 'evidence': self.proposal['evidence']}
        self.record_path.write_text(json.dumps(self.record))
        self.pin = hashlib.sha256(self.record_path.read_bytes()).hexdigest()

    def check_binding(self):
        return binding.bind(self.proposal, record_path=self.record_path, record_sha256=self.pin,
            source_path=self.source_path, registry_path=self.registry,
            authorization=self.headers['Authorization'], data_root=self.root, now=self.now)

    def test_matching_bytes_and_grant_never_authorize_execution(self):
        before = self.record_path.read_bytes(), self.source_path.read_bytes(), self.registry.read_bytes()
        r = self.check_binding()
        self.assertEqual(r['state'], 'offline_binding_consistent')
        self.assertEqual(r['decision'], 'PAUSE')
        self.assertFalse(r['execution_authorized']); self.assertFalse(r['evidence_truth_verified'])
        self.assertFalse(self.root.exists())
        self.assertEqual(before, (self.record_path.read_bytes(), self.source_path.read_bytes(), self.registry.read_bytes()))
        self.assertNotIn(fixtures.TOKEN, json.dumps(r))

    def test_changed_proposal_or_source_is_rejected(self):
        self.proposal['proposal_id'] = 'different'
        with self.assertRaises(binding.BindingError): self.check_binding()
        self.proposal['proposal_id'] = 'test'
        self.source_path.write_bytes(b'changed')
        with self.assertRaises(binding.BindingError): self.check_binding()

    def test_record_pin_cannot_be_replaced_by_record_claim(self):
        self.record['operator_approval'] = True
        self.record_path.write_text(json.dumps(self.record))
        with self.assertRaises(binding.BindingError): self.check_binding()
        self.pin = hashlib.sha256(self.record_path.read_bytes()).hexdigest()
        with self.assertRaises(binding.BindingError): self.check_binding()

    def test_expired_or_revoked_grant_stops_before_evidence_read(self):
        for change in ({'revoked': True}, {'expires_at': self.now}):
            self.grant.update(change); self.save()
            with patch.object(binding, 'snapshot') as read:
                with self.assertRaises(AuthorityDenied): self.check_binding()
            read.assert_not_called()

    def test_change_during_acquisition_is_rechecked(self):
        original = binding.snapshot
        def read(path):
            raw = original(path)
            if path == self.source_path:
                self.grant['revoked'] = True; self.save()
            return raw
        with patch.object(binding, 'snapshot', side_effect=read):
            with self.assertRaises(AuthorityDenied): self.check_binding()

    def test_no_finer_resource_scope_inferred(self):
        self.proposal['resource'] = str(self.root / 'file')
        with self.assertRaises(binding.BindingError): self.check_binding()

    def test_symlink_and_stale_evidence_rejected(self):
        link = self.registry.parent / 'link'; link.symlink_to(self.source_path)
        self.source_path = link
        with self.assertRaises(OSError): self.check_binding()
        self.proposal['evidence']['valid_until'] = self.now
        with self.assertRaises(binding.BindingError): self.check_binding()

    def test_still_valid_grant_change_is_rejected(self):
        original = binding.snapshot
        def read(path):
            raw = original(path)
            if path == self.source_path:
                self.grant['expires_at'] += 60; self.save()
            return raw
        with patch.object(binding, 'snapshot', side_effect=read):
            with self.assertRaises(binding.BindingError): self.check_binding()

    def test_duplicate_record_and_oversized_source_are_rejected(self):
        raw = self.record_path.read_text()
        self.record_path.write_text(raw[:-1] + ', "schema_version": 1}')
        self.pin = hashlib.sha256(self.record_path.read_bytes()).hexdigest()
        with self.assertRaises(binding.BindingError): self.check_binding()
        self.record_path.write_text(json.dumps(self.record))
        self.pin = hashlib.sha256(self.record_path.read_bytes()).hexdigest()
        self.source_path.write_bytes(b'x' * (binding.LIMIT + 1))
        with self.assertRaises(binding.BindingError): self.check_binding()
