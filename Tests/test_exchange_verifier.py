"""Verifier checks real synthetic handler output and rejects altered evidence."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch, Mock
import test_authority as fixtures
with patch.object(sys, 'path', [str(fixtures.HABITAT), *sys.path]):
    from verify_exchange import EvidenceError, verify_exchange, snapshot

@unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask missing')
class ExchangeVerifierTests(fixtures.GrantFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            'ECHO_NEXUS_ENABLE_DATA_ROUTES': '1',
            'ECHO_NEXUS_ROOT': str(self.root),
            'ECHO_NEXUS_GRANTS_FILE': str(self.registry),
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        spec = importlib.util.spec_from_file_location('authority_test_server', fixtures.HABITAT / 'cipher_server.py')
        self.server = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', [str(fixtures.HABITAT), *sys.path]):
            spec.loader.exec_module(self.server)
        self.http = self.server.app.test_client()

    def capture(self, persona='cipher'):
        self.grant['actions'] = ['cipher.chat', 'vexis.chat', 'receipt.append']
        self.save()
        response = self.http.post('/' + persona + '/chat', headers=self.headers,
                                  json={'message': 'synthetic verifier input'})
        self.assertEqual(response.status_code, 200)
        ledger = (self.root / 'receipts/execution.jsonl').read_bytes()
        memory_path = self.server.MEMORY_STREAM if persona == 'cipher' else self.server.VEXIS_MEMORY_STREAM
        return [ledger, memory_path.read_bytes(), response.data,
                response.json['receipt']['request_id'], response.json['receipt']['tip']]

    def test_real_exchange_matches_without_promoting_authority_or_success(self):
        for persona in ('cipher', 'vexis'):
            result = verify_exchange(*self.capture(persona))
            self.assertEqual(result['state'], 'exchange_evidence_consistent')
            self.assertFalse(result['authority_verified'])
            self.assertFalse(result['task_success_verified'])

    def test_changed_missing_duplicate_or_reordered_memory_is_not_verified(self):
        args = self.capture()
        first, second = args[1].splitlines(keepends=True)
        for altered in (first, second + first, first + second + second,
                        args[1].replace(b'synthetic verifier input', b'altered input'), args[1][:-1]):
            with self.subTest(altered=altered):
                bad = args.copy(); bad[1] = altered
                with self.assertRaises(EvidenceError):
                    verify_exchange(*bad)

    def test_response_request_tip_and_broken_chain_fail(self):
        args = self.capture()
        for index, value in ((0, args[0][:-1]), (2, b'{}'), (3, 'missing'), (4, '0' * 64)):
            bad = args.copy(); bad[index] = value
            with self.assertRaises(EvidenceError):
                verify_exchange(*bad)

    def test_rehashed_incomplete_or_self_verified_claim_still_fails(self):
        args = self.capture()
        original = [json.loads(line) for line in args[0].splitlines()]
        for mode in ('incomplete', 'verified', 'identity', 'order'):
            events = copy.deepcopy(original)
            if mode == 'incomplete':
                events.pop()
            elif mode == 'verified':
                events[-1]['details']['verification'] = 'verified'
            elif mode == 'identity':
                events[3]['grant_id'] = 'different'
            else:
                events[3], events[4] = events[4], events[3]
            previous = '0' * 64
            for sequence, event in enumerate(events, 1):
                event.pop('hash_self')
                event['hash_prev'] = previous
                event['sequence'] = sequence
                previous = hashlib.sha256(json.dumps(event, sort_keys=True,
                    separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
                event['hash_self'] = previous
            bad = args.copy()
            bad[0] = b''.join(json.dumps(event).encode() + b'\n' for event in events)
            bad[4] = previous
            with self.assertRaises(EvidenceError):
                verify_exchange(*bad)

    def test_later_exchange_does_not_invalidate_earlier_response_reference(self):
        earlier = self.capture()
        later = self.capture()
        earlier[0], earlier[1], earlier[4] = later[0], later[1], later[4]
        self.assertEqual(verify_exchange(*earlier)['memory_entries_matched'], 2)

    def test_external_response_and_handshake_forms(self):
        self.server.USE_OPENAI = True
        self.grant['actions'] = ['echo.handshake', 'external.openai', 'receipt.append']
        self.save()
        backend = Mock()
        backend.chat.completions.create.return_value = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='synthetic advisory'))])
        with patch.object(self.server, 'get_client', return_value=backend):
            response = self.http.post('/echo/handshake', headers=self.headers,
                json={'from': self.grant['subject'], 'to': 'Vexis@EchoNexus', 'message': 'synthetic',
                      'purpose_token': {'scope': 'echo.handshake', 'ttl': self.now + 30}})
        self.assertEqual(response.status_code, 200)
        result = verify_exchange((self.root / 'receipts/execution.jsonl').read_bytes(),
            self.server.VEXIS_MEMORY_STREAM.read_bytes(), response.data,
            response.json['receipt']['request_id'], response.json['receipt']['tip'])
        self.assertFalse(result['task_success_verified'])

    def test_snapshot_refuses_symlink_and_fifo_without_writes(self):
        path = self.registry.parent / 'evidence'
        path.symlink_to(self.registry)
        with self.assertRaises(OSError):
            snapshot(path)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(EvidenceError):
            snapshot(path)

if __name__ == '__main__':
    unittest.main()
