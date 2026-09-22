"""Real loopback session lifecycle with mocked generation, no GPU or live data."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HABITAT = Path(__file__).resolve().parents[1] / 'habitat'
HAS_FLASK = importlib.util.find_spec('flask') is not None
if HAS_FLASK:
    with patch.object(sys, 'path', [str(HABITAT), *sys.path]):
        import session
        import local_model
        import verify_exchange

@unittest.skipUnless(HAS_FLASK, 'Flask missing')
class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.args = types.SimpleNamespace(session_facts=False, orientation=None, orientation_sha256=None, self_test=False, output_dir=self.root,
            model=self.root / 'model', expected_commit='reviewed', grant_reference='synthetic operator authorization')
        self.previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        self.addCleanup(lambda: [signal.signal(s, handler) for s, handler in self.previous.items()])

    def run_session(self, lines, worker=None):
        def git(command, **kwargs):
            return '' if 'status' in command else 'reviewed\n'
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-unexported'}, clear=True), \
             patch.object(sys, 'path', [str(HABITAT), *sys.path]), \
             patch.object(session, 'parse_args', return_value=self.args), \
             patch.object(session.subprocess, 'check_output', side_effect=git), \
             patch.object(session.TerminalInput, 'read', side_effect=lines), \
             patch.object(local_model, 'generate', side_effect=worker or (lambda *a, **k: '4')), \
             contextlib.redirect_stdout(io.StringIO()):
            code = session.main()
        report_path = next(self.root.glob('cipher-session-*/session-report.json'))
        report = json.loads(report_path.read_text())
        self.assertTrue(report['server_stopped'])
        self.assertTrue(report['temporary_credentials_removed'])
        self.assertFalse(list(self.root.rglob('grant.json')))
        self.assertEqual(report_path.parent.stat().st_mode & 0o777, 0o700)
        return code, report, report_path.parent

    def test_quit_and_eof_stop_without_generation(self):
        for line in ('/quit', ''):
            code, report, _ = self.run_session([line])
            self.assertEqual(code, 0)
            self.assertEqual(report['completed_responses'], 0)
            self.assertTrue(report['grant_revoked'])
            # Separate fixture output for the second run.
            self.root = self.root / 'next'; self.root.mkdir()
            self.args.output_dir = self.root

    def test_completed_exchanges_preserve_context_and_verify(self):
        seen = []
        def worker(path, message, persona, check, **kwargs):
            check()
            seen.append(kwargs.get('context', []))
            return '4'
        code, report, _ = self.run_session(['2+2', 'what did you say', '/quit'], worker)
        self.assertEqual(code, 0)
        self.assertEqual(seen[0], [])
        self.assertEqual(seen[1], [{'role': 'user', 'content': '2+2'}, {'role': 'assistant', 'content': '4'}])
        self.assertEqual(len(report['verifications']), 2)
        self.assertFalse(report['task_success_verified'])

    def test_failed_worker_is_nonzero_and_not_retried(self):
        calls = []
        def worker(*args, **kwargs):
            calls.append(1)
            raise local_model.LocalFailure('synthetic_failure')
        code, report, _ = self.run_session(['test'], worker)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [1])
        self.assertEqual(report['completed_responses'], 0)

    def test_keyboard_interrupt_and_sigterm_cleanup(self):
        for event in ('keyboard', 'term'):
            def interrupt(*args):
                if event == 'keyboard':
                    raise KeyboardInterrupt
                signal.raise_signal(signal.SIGTERM)
            code, report, _ = self.run_session(interrupt)
            self.assertEqual(code, 0)
            self.assertTrue(report['grant_revoked'])
            self.root = self.root / 'next'; self.root.mkdir()
            self.args.output_dir = self.root

    def test_evidence_failure_returns_nonzero_and_preserves_memory(self):
        with patch.object(verify_exchange, 'verify_exchange', side_effect=verify_exchange.EvidenceError()):
            code, report, folder = self.run_session(['test', '/quit'])
        self.assertEqual(code, 1)
        self.assertTrue((folder / 'data/memory/streams/root_memory.jsonl').is_file())
        self.assertIn('Evidence check failed; preserve files for review.', report['notes'])

    def test_input_timeout_stops_without_renewal(self):
        code, report, _ = self.run_session([None])
        self.assertEqual(code, 0)
        self.assertIn('Input window ended; no authority renewal.', report['notes'])

    def test_five_message_cap_and_context_eviction(self):
        seen = []
        def worker(path, message, persona, check, **kwargs):
            check(); seen.append(kwargs.get('context', [])); return '4'
        code, report, _ = self.run_session(['1', '2', '3', '4', '5'], worker)
        self.assertEqual(code, 0)
        self.assertEqual(report['completed_responses'], 5)
        self.assertEqual([len(c) for c in seen], [0, 2, 4, 6, 6])
        self.assertEqual(seen[-1][0]['content'], '2')

    def test_piped_lines_survive_text_buffering(self):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b'first\nsecond\n/quit\n'); os.close(write_fd)
        with os.fdopen(read_fd, 'r') as stream, patch.object(sys, 'stdin', stream):
            terminal = session.TerminalInput()
            self.assertEqual([terminal.read(1) for _ in range(4)], ['first', 'second', '/quit', ''])

    def test_revocation_write_failure_still_stops_server(self):
        original = Path.replace
        calls = []
        def replace(path, target):
            if path.name == 'grant.new':
                calls.append(1)
                if len(calls) == 2:
                    raise OSError('synthetic revocation write failure')
            return original(path, target)
        with patch.object(Path, 'replace', replace):
            code, report, _ = self.run_session(['/quit'])
        self.assertEqual(code, 1)
        self.assertFalse(report['grant_revoked'])
        self.assertIn('Grant revocation write failed; server shutdown still attempted.', report['notes'])

    def test_interactive_requires_clean_reviewed_commit_before_creating_session(self):
        with patch.object(session, 'parse_args', return_value=self.args), \
             patch.object(session.subprocess, 'check_output', side_effect=['different\n', '']), \
             self.assertRaises(SystemExit):
            session.main()
        self.assertEqual(list(self.root.iterdir()), [])
