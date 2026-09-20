"""No real habitat data, network calls, or listening sockets are used."""
import ast
import copy
import importlib.util
import os
from pathlib import Path, PureWindowsPath
import shutil
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "habitat" / "cipher_server.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))


def isolated(*names, **namespace):
    """Execute selected pure/gated functions, never module startup or handlers."""
    nodes = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for node in nodes:
        node = copy.deepcopy(node)
        node.decorator_list = []
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


class SafetyTests(unittest.TestCase):
    def test_paths(self):
        root = isolated('data_root', Path=Path, PureWindowsPath=PureWindowsPath)['data_root']
        self.assertIsNone(root(None))
        for value in ('relative', r'C:\synthetic', r'\\host\synthetic'):
            with self.assertRaises(ValueError):
                root(value)
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / 'not created with spaces'
            self.assertEqual(root(str(expected)), expected)
            self.assertFalse(expected.exists())

    def test_explicit_opt_in(self):
        enabled = isolated('enabled', os=os)['enabled']
        for value in ('0', 'true', 'yes', '', '1'):
            with patch.dict(os.environ, {'TEST_FLAG': value}, clear=True):
                self.assertEqual(enabled('TEST_FLAG'), value == '1')

    def test_safe_startup_defaults(self):
        main = TREE.body[-1]
        self.assertIsInstance(main, ast.If)
        call = main.body[0].value
        self.assertEqual({k.arg: ast.literal_eval(k.value) for k in call.keywords}, {
            'host': '127.0.0.1', 'port': 5000, 'debug': False,
            'use_reloader': False, 'load_dotenv': False})
        for node in TREE.body:
            if isinstance(node, (ast.Assign, ast.Expr)):
                self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                                     and n.func.id == 'OpenAI' for n in ast.walk(node)))

    def test_disabled_backend_never_constructed(self):
        factory = Mock(side_effect=AssertionError('backend must not be constructed'))
        fake = types.SimpleNamespace(OpenAI=factory)
        ns = isolated('get_client', 'generate_cipher_reply', 'generate_vexis_reply',
                      USE_OPENAI=False, client=None)
        with patch.dict(sys.modules, {'openai': fake}):
            with self.assertRaises(RuntimeError):
                ns['get_client']()
            for persona in ('cipher', 'vexis'):
                self.assertIn('stub', ns[f'generate_{persona}_reply']('synthetic', 'tester'))
        factory.assert_not_called()

    def test_enabled_backend_is_lazy_and_cached(self):
        factory = Mock()
        ns = isolated('get_client', USE_OPENAI=True, client=None)
        factory.assert_not_called()
        with patch.dict(sys.modules, {'openai': types.SimpleNamespace(OpenAI=factory)}):
            self.assertIs(ns['get_client'](), factory.return_value)
            self.assertIs(ns['get_client'](), factory.return_value)
        factory.assert_called_once_with(base_url='https://api.openai.com/v1', max_retries=0, timeout=15.0)

    def test_health_function_has_no_io(self):
        health = isolated('health', jsonify=lambda value: value)['health']
        with patch('builtins.open', side_effect=AssertionError('unexpected file access')):
            self.assertEqual(health(), ({'status': 'ok'}, 200))

    def test_memory_requires_both_permissions(self):
        for persona in ('cipher', 'vexis'):
            for send, routes in ((False, False), (False, True), (True, False), (True, True)):
                backend = Mock()
                backend.chat.completions.create.return_value = types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='synthetic reply'))])
                history = Mock(return_value=[{'role': 'user', 'content': 'synthetic memory'}])
                ns = isolated(f'generate_{persona}_reply', USE_OPENAI=True,
                              SEND_MEMORY=send, DATA_ROUTES=routes,
                              MEMORY_STREAM=None, VEXIS_MEMORY_STREAM=None,
                              OPENAI_MODEL='mock', build_chat_history=history,
                              get_client=lambda: backend, require_authority=lambda *args: None)
                ns[f'generate_{persona}_reply']('synthetic input', 'tester')
                self.assertEqual(history.call_count, int(send and routes))
                messages = backend.chat.completions.create.call_args.kwargs['messages']
                self.assertEqual(any(m['content'] == 'synthetic memory' for m in messages), send and routes)

    def test_disabled_io_helpers(self):
        ns = isolated('append_jsonl', 'read_memory_tail', DATA_ROUTES=False, Path=Path)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.jsonl'
            with self.assertRaises(RuntimeError):
                ns['append_jsonl'](path, {})
            with self.assertRaises(RuntimeError):
                ns['read_memory_tail'](path)
            self.assertFalse(path.exists())

    def test_launcher_exit_and_signal(self):
        with tempfile.TemporaryDirectory(prefix='cipher launcher ') as tmp:
            root = Path(tmp)
            (root / 'habitat').mkdir()
            (root / '.venv/bin').mkdir(parents=True)
            launcher = root / 'habitat/run_cipher_server.sh'
            shutil.copyfile(ROOT / 'habitat/run_cipher_server.sh', launcher)
            fake = root / '.venv/bin/python'
            fake.write_text('#!/bin/sh\n[ "$1" = "-B" ] || exit 2\n[ "$FLASK_SKIP_DOTENV" = 1 ] || exit 3\nexit 37\n')
            fake.chmod(0o700)
            result = subprocess.run(['sh', str(launcher)], cwd='/', capture_output=True)
            self.assertEqual(result.returncode, 37)
            fake.write_text('#!/bin/sh\nkill -TERM "$$"\n')
            result = subprocess.run(['sh', str(launcher)], cwd='/', capture_output=True)
            self.assertEqual(result.returncode, -signal.SIGTERM)


@unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask missing; HTTP runtime tests pending')
class FlaskRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        spec = importlib.util.spec_from_file_location('cipher_test_server', SOURCE)
        self.server = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'openai': None}), \
             patch.object(sys, 'path', [str(SOURCE.parent), *sys.path]):
            spec.loader.exec_module(self.server)
        self.http = self.server.app.test_client()

    def test_health_no_io_or_backend(self):
        with patch('builtins.open', side_effect=AssertionError('unexpected file access')), \
             patch.object(Path, 'open', side_effect=AssertionError('unexpected file access')), \
             patch.object(Path, 'exists', side_effect=AssertionError('unexpected stat')), \
             patch.object(Path, 'mkdir', side_effect=AssertionError('unexpected mkdir')), \
             patch.object(self.server, 'get_client', side_effect=AssertionError('backend')):
            for _ in range(2):
                self.assertEqual(self.http.get('/healthz').json, {'status': 'ok'})
                self.assertEqual(self.http.get('/echo/status').status_code, 200)
        self.assertIsNone(self.server.ECHO_ROOT)
        self.assertIsNone(self.server.client)
        self.assertFalse(self.server.app.debug)

    def test_all_protected_routes_blocked(self):
        with patch.object(self.server, 'append_jsonl', side_effect=AssertionError('write')), \
             patch.object(self.server, 'read_memory_tail', side_effect=AssertionError('read')), \
             patch.object(self.server, 'get_client', side_effect=AssertionError('backend')):
            for rule in self.server.app.url_map.iter_rules():
                if rule.endpoint in ('health', 'echo_status', 'cipher_client_page', 'static'):
                    continue
                method = 'POST' if 'POST' in rule.methods else 'GET'
                response = self.http.open(rule.rule, method=method, json={'message': 'synthetic'})
                self.assertEqual(response.status_code, 403, rule.rule)
        self.assertIn(b'protected routes disabled', self.http.get('/').data)

    def test_capability_switch_alone_cannot_authorize_write(self):
        path = Path(self.temp.name) / 'synthetic.jsonl'
        with patch.object(self.server, 'DATA_ROUTES', True), \
             patch.object(self.server, 'MEMORY_STREAM', path):
            response = self.http.post('/cipher/log', json={'summary': 'synthetic', 'text': 'fixture'})
            self.assertEqual(response.status_code, 403)
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
