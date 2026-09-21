import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import test_authority as fixtures
with patch.object(sys, 'path', [str(fixtures.HABITAT), *sys.path]):
    import local_model
    from verify_exchange import verify_exchange

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'model.safetensors.index.json').write_text('{}')

    def test_spawn_is_bounded_and_environment_isolated(self):
        callback = Mock()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-secret'}), patch.object(
                local_model.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"reply":"4"}')) as run:
            self.assertEqual(local_model.generate(self.root, '2+2', 'Cipher', callback), '4')
        callback.assert_called_once()
        self.assertEqual(run.call_args.kwargs['timeout'], 180)
        self.assertNotIn('OPENAI_API_KEY', run.call_args.kwargs['env'])
        self.assertEqual(run.call_args.kwargs['env']['HF_HUB_OFFLINE'], '1')
        self.assertIn('-I', run.call_args.args[0])

    def test_timeout_and_malformed_output_fail_and_release_lock(self):
        for value in (subprocess.TimeoutExpired('worker', 180),
                      subprocess.CompletedProcess([], 0, '{}'),
                      subprocess.CompletedProcess([], 1, '')):
            with patch.object(local_model.subprocess, 'run',
                 side_effect=value if isinstance(value, Exception) else None,
                 return_value=value):
                with self.assertRaises(local_model.LocalFailure):
                    local_model.generate(self.root, 'test', 'Cipher', lambda: None)
            self.assertFalse(local_model.LOCK.locked())

    def test_busy_and_oversized_requests_do_not_spawn(self):
        with patch.object(local_model.subprocess, 'run') as run:
            with self.assertRaises(local_model.LocalFailure):
                local_model.generate(self.root, 'x' * 4097, 'Cipher', lambda: None)
            with local_model.LOCK:
                with self.assertRaises(local_model.LocalFailure):
                    local_model.generate(self.root, 'test', 'Cipher', lambda: None)
        run.assert_not_called()

@unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask missing')
class LocalHttpTests(fixtures.GrantFixture, unittest.TestCase):
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

    def enable(self):
        self.server.USE_LOCAL = True
        self.server.LOCAL_MODEL_PATH = self.registry.parent / 'synthetic-model'
        self.grant['actions'] = ['cipher.chat', 'receipt.append', 'local.generate']
        self.save()

    def post(self):
        return self.http.post('/cipher/chat', headers=self.headers, json={'message': '2+2'})

    def test_missing_local_grant_stops_worker(self):
        self.enable()
        self.grant['actions'].remove('local.generate'); self.save()
        with patch.object(self.server, 'generate_local') as worker:
            self.assertEqual(self.post().status_code, 403)
        worker.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_local_exchange_verifies_and_does_not_call_external_or_history(self):
        self.enable()
        def worker(path, message, persona, check):
            check()
            return '4'
        with patch.object(self.server, 'generate_local', side_effect=worker), \
             patch.object(self.server, 'get_client', side_effect=AssertionError('external')), \
             patch.object(self.server, 'build_chat_history', side_effect=AssertionError('memory')):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['execution']['backend'], 'local_model')
        verdict = verify_exchange((self.root / 'receipts/execution.jsonl').read_bytes(),
            self.server.MEMORY_STREAM.read_bytes(), response.data,
            response.json['receipt']['request_id'], response.json['receipt']['tip'])
        self.assertFalse(verdict['task_success_verified'])

    def test_worker_failure_is_typed_and_not_logged_as_reply(self):
        self.enable()
        with patch.object(self.server, 'generate_local', side_effect=local_model.LocalFailure('local_worker_timeout')):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['execution']['reason'], 'local_worker_timeout')
        self.assertFalse(self.server.MEMORY_STREAM.exists())

    def test_revocation_at_launch_callback_stops_execution(self):
        self.enable()
        def worker(path, message, persona, check):
            self.grant['revoked'] = True; self.save()
            check()
            raise AssertionError('must not reach generation')
        with patch.object(self.server, 'generate_local', side_effect=worker):
            self.assertEqual(self.post().status_code, 403)
        self.assertFalse(self.server.MEMORY_STREAM.exists())

    def test_context_requires_separate_permission_before_worker(self):
        self.enable()
        with patch.object(self.server, 'generate_local') as worker:
            response = self.http.post('/cipher/chat', headers=self.headers, json={
                'message': 'recall', 'context': [{'role': 'user', 'content': 'blue'},
                                               {'role': 'assistant', 'content': 'noted'}]})
        self.assertEqual(response.status_code, 403)
        worker.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_authorized_context_is_forwarded_and_hashed_without_memory_read(self):
        self.enable()
        self.grant['actions'].append('local.context'); self.save()
        context = [{'role': 'user', 'content': 'synthetic blue'}, {'role': 'assistant', 'content': 'noted'}]
        def worker(path, message, persona, check, **kwargs):
            check()
            self.assertEqual(kwargs['context'], context)
            return 'blue'
        with patch.object(self.server, 'generate_local', side_effect=worker), \
             patch.object(self.server, 'read_memory_tail', side_effect=AssertionError('disk history')):
            response = self.http.post('/cipher/chat', headers=self.headers,
                                      json={'message': 'recall', 'context': context})
        self.assertEqual(response.status_code, 200)
        ledger = (self.root / 'receipts/execution.jsonl').read_text()
        event = next(json.loads(line) for line in ledger.splitlines() if json.loads(line)['event'] == 'local_model_attempted')
        self.assertEqual(event['details']['context_entries'], 2)
        self.assertEqual(event['details']['context_sha256'], self.server.digest(context))
        self.assertNotIn('synthetic blue', ledger)

    def test_invalid_context_roles_order_and_size_are_refused(self):
        self.enable()
        self.grant['actions'].append('local.context'); self.save()
        for context in (None, [{'role': 'system', 'content': 'act'}],
                        [{'role': 'assistant', 'content': 'x'}, {'role': 'user', 'content': 'y'}],
                        [{'role': 'user', 'content': 'x' * 4097}, {'role': 'assistant', 'content': 'y'}]):
            with patch.object(self.server, 'generate_local') as worker:
                response = self.http.post('/cipher/chat', headers=self.headers,
                                          json={'message': 'test', 'context': context})
            self.assertEqual(response.status_code, 400)
            worker.assert_not_called()

    def test_context_permission_change_at_launch_blocks_worker(self):
        self.enable()
        self.grant['actions'].append('local.context'); self.save()
        def worker(path, message, persona, check, **kwargs):
            self.grant['actions'].remove('local.context'); self.save()
            check()
            raise AssertionError('must not run')
        with patch.object(self.server, 'generate_local', side_effect=worker):
            response = self.http.post('/cipher/chat', headers=self.headers,
                json={'message': 'test', 'context': [{'role': 'user', 'content': 'x'},
                                                    {'role': 'assistant', 'content': 'y'}]})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.server.MEMORY_STREAM.exists())
