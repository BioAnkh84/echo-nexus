"""Token-stop metadata is evidence of stopping, never semantic completeness."""
import json
import subprocess
import unittest
from unittest.mock import patch
import test_session
import test_local_model
import local_model
from verify_exchange import verify_exchange

class FinishTests(unittest.TestCase):
    def test_eos_at_limit_wins_over_length_and_multiple_eos_work(self):
        self.assertEqual(local_model.generation_metadata([4] * 63 + [9], [8, 9])['finish_reason'], 'eos')
        self.assertEqual(local_model.generation_metadata([4] * 64, [8, 9])['finish_reason'], 'length')
        self.assertEqual(local_model.generation_metadata([4], None)['finish_reason'], 'unknown')

    def test_invalid_metadata_is_rejected(self):
        for value in ({}, {'finish_reason': 'length', 'generated_tokens': 3, 'max_new_tokens': 64},
                      {'finish_reason': 'eos', 'generated_tokens': True, 'max_new_tokens': 64},
                      {'finish_reason': 'eos', 'generated_tokens': 65, 'max_new_tokens': 64}):
            with self.assertRaises(ValueError): local_model.validate_generation(value)

class WorkerFinishTests(test_local_model.WorkerTests):
    def test_worker_metadata_survives_parent_boundary(self):
        meta = {'finish_reason': 'length', 'generated_tokens': 64, 'max_new_tokens': 64}
        with patch.object(local_model.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, json.dumps({'reply': 'partial answer', 'generation': meta}))):
            reply = local_model.generate(self.root, 'test', 'Cipher', lambda: None)
        self.assertEqual(reply.generation, meta)
        self.assertEqual(str(reply), 'partial answer')

    def test_missing_metadata_fails_closed(self):
        with patch.object(local_model.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"reply":"4"}')):
            with self.assertRaises(local_model.LocalFailure):
                local_model.generate(self.root, 'test', 'Cipher', lambda: None)

class HttpFinishTests(test_local_model.LocalHttpTests):
    def test_length_metadata_is_in_response_and_verified_receipt(self):
        self.enable()
        meta = {'finish_reason': 'length', 'generated_tokens': 64, 'max_new_tokens': 64}
        def worker(path, message, persona, check):
            check()
            return local_model.LocalReply('unfinished answer', meta)
        with patch.object(self.server, 'generate_local', side_effect=worker):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['generation'], meta)
        ledger = (self.root / 'receipts/execution.jsonl').read_bytes()
        event = next(json.loads(line) for line in ledger.splitlines() if json.loads(line)['event'] == 'generation_result')
        self.assertEqual(event['details']['generation'], meta)
        verdict = verify_exchange(ledger, self.server.MEMORY_STREAM.read_bytes(), response.data,
                                  response.json['receipt']['request_id'], response.json['receipt']['tip'])
        self.assertFalse(verdict['task_success_verified'])

class SessionFinishTests(test_session.SessionTests):
    def test_output_limit_warning_and_evidence_survive_cleanup(self):
        meta = {'finish_reason': 'length', 'generated_tokens': 64, 'max_new_tokens': 64}
        def worker(*args, **kwargs):
            args[3]()
            return local_model.LocalReply('partial', meta)
        with patch('builtins.print') as printed:
            code, report, folder = self.run_session(['question', '/quit'], worker)
        self.assertEqual(code, 0)
        self.assertTrue(any('Output limit reached' in str(call) for call in printed.call_args_list))
        self.assertEqual(json.loads((folder / 'response-1.json').read_text())['generation'], meta)
        self.assertFalse(report['task_success_verified'])


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for cls in (FinishTests, WorkerFinishTests, HttpFinishTests, SessionFinishTests):
        suite.addTests(cls(name) for name in cls.__dict__ if name.startswith('test_'))
    return suite
