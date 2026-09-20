"""Synthetic failure-path checks; no real provider or live memory."""
import importlib.util
import sys
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import test_authority as fixtures
with patch.object(sys, 'path', [str(fixtures.HABITAT), *sys.path]):
    from receipts import ReceiptError, append_event, verify_file, verify_bytes


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'receipts/execution.jsonl'

    def test_chain_and_external_tip_detect_changed_or_removed_events(self):
        append_event(self.root, {'event': 'first'})
        tip = append_event(self.root, {'event': 'second'})
        raw = self.path.read_bytes()
        result = verify_file(self.path, tip)
        self.assertEqual(result['events'], 2)
        self.assertFalse(result['task_success_verified'])
        with self.assertRaises(ReceiptError):
            verify_bytes(raw.replace(b'first', b'other'))
        shortened = raw.splitlines(keepends=True)[0]
        self.assertTrue(verify_bytes(shortened)['chain_valid'])
        with self.assertRaises(ReceiptError):
            verify_bytes(shortened, tip)

    def test_partial_tail_is_preserved_and_blocks_append(self):
        append_event(self.root, {'event': 'first'})
        with self.path.open('ab') as stream:
            stream.write(b'{"partial":')
        before = self.path.read_bytes()
        with self.assertRaises(ReceiptError):
            append_event(self.root, {'event': 'next'})
        self.assertEqual(self.path.read_bytes(), before)

    def test_busy_ledger_refuses_without_waiting_or_changing_it(self):
        append_event(self.root, {'event': 'first'})
        before = self.path.read_bytes()
        with self.path.open('rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ReceiptError):
                append_event(self.root, {'event': 'busy'})
        self.assertEqual(self.path.read_bytes(), before)

    def test_symlink_fifo_and_public_ledger_are_rejected(self):
        self.path.parent.mkdir()
        target = self.root / 'target'
        target.write_text('preserved')
        self.path.symlink_to(target)
        with self.assertRaises(ReceiptError):
            append_event(self.root, {'event': 'bad'})
        self.assertEqual(target.read_text(), 'preserved')
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        with self.assertRaises(ReceiptError):
            append_event(self.root, {'event': 'bad'})
        self.path.unlink()
        self.path.touch(mode=0o644)
        with self.assertRaises(ReceiptError):
            append_event(self.root, {'event': 'bad'})

    def test_partial_os_write_failure_does_not_reset_chain(self):
        append_event(self.root, {'event': 'first'})
        original = os.write
        def partial(fd, value):
            original(fd, value[:8])
            raise OSError('synthetic failure')
        with patch('receipts.os.write', side_effect=partial):
            with self.assertRaises(ReceiptError):
                append_event(self.root, {'event': 'second'})
        with self.assertRaises(ReceiptError):
            verify_file(self.path)


@unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask missing')
class HttpReceiptTests(fixtures.GrantFixture, unittest.TestCase):
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


    def enable(self, external=False):
        self.grant['actions'] = ['cipher.chat', 'vexis.chat', 'receipt.append']
        if external:
            self.grant['actions'].append('external.openai')
        self.server.USE_OPENAI = external
        self.save()

    def post(self, persona='cipher'):
        return self.http.post('/' + persona + '/chat', headers=self.headers,
                              json={'message': 'private-synthetic-message'})

    def events(self):
        return [json.loads(line) for line in
                (self.root / 'receipts/execution.jsonl').read_text().splitlines()]

    def test_missing_receipt_authority_stops_generation(self):
        self.grant['actions'] = ['cipher.chat']
        self.save()
        with patch.object(self.server, 'generate_cipher_reply') as generate:
            self.assertEqual(self.post().status_code, 403)
        generate.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_receipt_failure_before_execution_blocks_provider_and_memory(self):
        self.enable(external=True)
        with patch.object(self.server, 'append_event', side_effect=ReceiptError()), \
             patch.object(self.server, 'get_client') as provider:
            self.assertEqual(self.post().status_code, 503)
        provider.assert_not_called()
        self.assertFalse(self.server.MEMORY_STREAM.exists())

    def test_corrupt_ledger_is_preserved_and_blocks_generation(self):
        self.enable()
        append_event(self.root, {'event': 'existing'})
        path = self.root / 'receipts/execution.jsonl'
        raw = path.read_bytes() + b'partial'
        path.write_bytes(raw)
        with patch.object(self.server, 'generate_cipher_reply') as generate:
            self.assertEqual(self.post().status_code, 503)
        generate.assert_not_called()
        self.assertEqual(path.read_bytes(), raw)

    def test_provider_setup_request_and_empty_response_fail_typed(self):
        self.enable(external=True)
        for persona in ('cipher', 'vexis'):
            for failure, status, transmission in (
                    ('setup', 503, 'not_attempted'), ('request', 502, 'unknown'),
                    ('empty', 502, 'response_received')):
                with self.subTest(persona=persona, failure=failure):
                    backend = Mock()
                    backend.chat.completions.create.return_value = types.SimpleNamespace(
                        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=''))])
                    if failure == 'request':
                        backend.chat.completions.create.side_effect = TimeoutError('private error')
                    with patch.object(self.server, 'get_client', return_value=backend,
                                      side_effect=RuntimeError('private error') if failure == 'setup' else None):
                        response = self.post(persona)
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.json['execution']['transmission'], transmission)
                    self.assertNotIn('reply', response.json)
                    self.assertNotIn('private error', response.get_data(as_text=True))
        self.assertFalse(self.server.MEMORY_STREAM.exists())
        self.assertFalse(self.server.VEXIS_MEMORY_STREAM.exists())
        self.assertFalse(any(e['event'] == 'execution_result' for e in self.events()))

    def test_completed_stub_is_unverified_and_memory_hashes_match_bytes(self):
        self.enable()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['execution']['state'], 'completed_unverified')
        self.assertEqual(response.json['execution']['verification'], 'not_performed')
        path = self.root / 'receipts/execution.jsonl'
        self.assertTrue(verify_file(path, response.json['receipt']['tip'])['chain_valid'])
        self.assertNotIn('private-synthetic-message', path.read_text())
        self.assertNotIn(self.headers['Authorization'], path.read_text())
        actual = [hashlib.sha256(line).hexdigest() for line in
                  self.server.MEMORY_STREAM.read_bytes().splitlines(keepends=True)]
        recorded = [e['details']['entry_sha256'] for e in self.events()
                    if e['event'] == 'memory_append_result']
        self.assertEqual(actual, recorded)

    def test_post_memory_receipt_failure_reports_incomplete_with_partial_effect(self):
        self.enable()
        real = self.server.append_event
        def fail(root, event):
            if event['event'] == 'memory_append_result':
                raise ReceiptError()
            return real(root, event)
        with patch.object(self.server, 'append_event', side_effect=fail):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['execution']['state'], 'incomplete')
        self.assertEqual(len(self.server.MEMORY_STREAM.read_text().splitlines()), 1)
        self.assertFalse(any(e['event'] == 'execution_result' for e in self.events()))

    def test_memory_io_failure_reports_incomplete(self):
        self.enable()
        with patch.object(self.server, 'append_jsonl', side_effect=OSError('synthetic')):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.events()[-1]['event'], 'execution_incomplete')


if __name__ == '__main__':
    unittest.main()
