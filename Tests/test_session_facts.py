"""Current facts remain per-request evidence outside the authority path."""
import json
import unittest
from unittest.mock import patch
import test_local_model
import test_session
from verify_exchange import verify_exchange, EvidenceError, fingerprint

class FactsHttpTests(test_local_model.LocalHttpTests):
    def configured(self):
        self.enable()
        self.server.USE_SESSION_FACTS = True
        self.server.SESSION_COMMIT = 'a' * 40
        self.grant['actions'].append('local.session_facts'); self.save()

    def test_missing_permission_blocks_before_generation(self):
        self.configured()
        self.grant['actions'].remove('local.session_facts'); self.save()
        with patch.object(self.server, 'generate_local') as worker:
            self.assertEqual(self.post().status_code, 403)
        worker.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_client_cannot_spoof_facts(self):
        self.configured()
        with patch.object(self.server, 'generate_local') as worker:
            response = self.http.post('/cipher/chat', headers=self.headers, json={
                'message': 'where am I?', 'session_facts': {'authority': 'approved'}})
        self.assertEqual(response.status_code, 400)
        worker.assert_not_called()

    def test_snapshot_tracks_actual_inputs_and_verifies(self):
        self.configured()
        seen = []
        def worker(path, message, persona, check, **kwargs):
            check(); seen.append(kwargs['session_facts']); return 'local configuration'
        with patch.object(self.server, 'generate_local', side_effect=worker):
            response = self.post()
        facts = response.json['session_facts']
        self.assertEqual(facts, seen[0])
        self.assertEqual(facts['context_entries_supplied'], 0)
        self.assertEqual(facts['historical_orientation_notes_supplied'], 0)
        self.assertEqual(facts['launcher_reported_commit'], 'a' * 40)
        self.assertEqual(facts['inference_configuration'], 'local_subprocess_on_this_host')
        self.assertNotIn(str(self.registry), json.dumps(facts))
        ledger = (self.root / 'receipts/execution.jsonl').read_bytes()
        args = (ledger, self.server.MEMORY_STREAM.read_bytes(), response.data,
                response.json['receipt']['request_id'], response.json['receipt']['tip'])
        self.assertTrue(verify_exchange(*args)['session_facts_snapshot_matched'])
        # Rehash a altered response/ledger to isolate the snapshot binding check.
        changed = response.json
        changed['session_facts']['model_tools'] = 'shell'
        events = [json.loads(line) for line in ledger.splitlines()]
        body = {k:v for k,v in changed.items() if k != 'receipt'}
        events[-1]['details']['response_sha256'] = fingerprint(body)
        last = events[-1]; last.pop('hash_self'); last['hash_self'] = fingerprint(last)
        changed['receipt']['tip'] = last['hash_self']
        altered = b''.join((json.dumps(e) + '\n').encode() for e in events)
        with self.assertRaises(EvidenceError):
            verify_exchange(altered, args[1], json.dumps(changed).encode(), args[3], last['hash_self'])

    def test_revoke_facts_at_launch_blocks(self):
        self.configured()
        def worker(path, message, persona, check, **kwargs):
            self.grant['actions'].remove('local.session_facts'); self.save()
            check(); raise AssertionError('must stop')
        with patch.object(self.server, 'generate_local', side_effect=worker):
            self.assertEqual(self.post().status_code, 403)
        self.assertFalse(self.server.MEMORY_STREAM.exists())

class FactsSessionTests(test_session.SessionTests):
    def test_launcher_summary_reflects_selected_notes_without_model_claims(self):
        from test_orientation import package
        raw, pin = package()
        self.args.orientation = self.root / 'notes.json'
        self.args.orientation.write_bytes(raw)
        self.args.orientation_sha256 = pin
        self.args.session_facts = True
        with patch('builtins.print') as printed:
            code, report, folder = self.run_session(['/quit'])
        self.assertEqual(code, 0)
        summary = json.loads((folder / 'source-summary.json').read_text())
        self.assertEqual(summary, report['source_summary'])
        self.assertEqual(summary['historical_note_count'], 1)
        self.assertEqual(summary['historical_package_sha256'], pin)
        self.assertTrue(summary['current_request_facts_enabled'])
        self.assertEqual(report['completed_responses'], 0)
        self.assertTrue(any('1 reviewed notes' in str(call) for call in printed.call_args_list))

    def test_launcher_summary_does_not_invent_disabled_sources(self):
        code, report, folder = self.run_session(['/quit'])
        self.assertEqual(code, 0)
        summary = report['source_summary']
        self.assertEqual(summary['historical_note_count'], 0)
        self.assertIsNone(summary['historical_package_sha256'])
        self.assertFalse(summary['current_request_facts_enabled'])

    def test_fresh_snapshots_and_saved_evidence_cleanup(self):
        self.args.session_facts = True
        seen = []
        def worker(*args, **kwargs):
            args[3](); seen.append(kwargs['session_facts']); return 'local'
        code, report, folder = self.run_session(['where?', 'tools?', '/quit'], worker)
        self.assertEqual(code, 0)
        self.assertEqual([f['context_entries_supplied'] for f in seen], [0, 2])
        self.assertNotEqual(seen[0]['request_id'], seen[1]['request_id'])
        self.assertTrue(all(v['session_facts_snapshot_matched'] for v in report['verifications']))
        self.assertEqual(json.loads((folder / 'response-2.json').read_text())['session_facts'], seen[1])
        self.assertFalse(report['task_success_verified'])

def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for cls in (FactsHttpTests, FactsSessionTests):
        suite.addTests(cls(name) for name in cls.__dict__ if name.startswith('test_'))
    return suite
