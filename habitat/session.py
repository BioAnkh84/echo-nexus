"""Bounded operator-run Cipher session; isolated data, no live Habitat imports."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import select
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from werkzeug.serving import make_server, WSGIRequestHandler

REPO = Path(__file__).resolve().parent.parent

class Quiet(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


class TerminalInput:
    """Bounded input without TextIO buffering hiding later piped lines."""
    def __init__(self):
        self.pending = b''

    def read(self, timeout):
        deadline = time.monotonic() + timeout
        while b'\n' not in self.pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([sys.stdin], [], [], remaining)[0]:
                return None
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk:
                value, self.pending = self.pending, b''
                return value.decode('utf-8', errors='replace')
            self.pending += chunk
            if len(self.pending) > 65536:
                raise ValueError('Input buffer limit')
        line, self.pending = self.pending.split(b'\n', 1)
        return line.decode('utf-8', errors='replace')


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='One synthetic stub exchange; no GPU')
    parser.add_argument('--output-dir', required=True, type=Path, help='Existing authorized directory for private session evidence')
    parser.add_argument('--model', type=Path, help='Existing local model directory; no downloads')
    parser.add_argument('--grant-reference', required=True, help='Reference to the operator authorization for this session')
    parser.add_argument('--expected-commit', help='Reviewed repository commit required for interactive sessions')
    parser.add_argument('--orientation', type=Path, help='Explicit reviewed historical package')
    parser.add_argument('--orientation-sha256', help='Operator-reviewed package digest')
    args = parser.parse_args()
    if bool(args.orientation) != bool(args.orientation_sha256) or (args.self_test and args.orientation):
        parser.error('Orientation requires both path and digest, and a local-model session')
    if not args.output_dir.is_absolute() or not args.output_dir.is_dir():
        parser.error('--output-dir must be an existing absolute directory')
    if not args.grant_reference.strip():
        parser.error('--grant-reference cannot be empty')
    if not args.self_test and (not args.expected_commit or not args.model or
            not args.model.is_absolute() or not (args.model / 'model.safetensors.index.json').is_file()):
        parser.error('Interactive sessions require --expected-commit and an existing absolute --model directory')
    return args


def main():
    args = parse_args()
    sha = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True).strip())
    if not args.self_test and (sha != args.expected_commit or dirty):
        raise SystemExit('STOP: checkout differs from the reviewed commit or has local changes.')
    sys.path.insert(0, str(REPO / 'habitat'))
    from authority import CHARTER_SHA256
    from verify_exchange import verify_exchange, EvidenceError
    from orientation import load as load_orientation
    orientation = load_orientation(args.orientation, args.orientation_sha256) if args.orientation else None
    session = Path(tempfile.mkdtemp(prefix='cipher-session-', dir=args.output_dir))
    session.chmod(0o700)
    if orientation is not None:
        (session / 'orientation.json').write_bytes(orientation)
    root = session / 'data'
    responses = []
    history = []
    notes = []
    token = secrets.token_urlsafe(32)
    started = int(time.time())
    expiry = started + 600
    monotonic_end = time.monotonic() + 600
    failed = False
    terminal = TerminalInput()
    print('Session files (including your messages):', session, flush=True)
    print('Five messages maximum; ten-minute grant. /quit ends the session.', flush=True)
    print('Context: up to three prior exchanges from this session only. Responses remain unverified.', flush=True)
    with tempfile.TemporaryDirectory(prefix='cipher-session-grant-', dir=session) as temporary:
        registry = Path(temporary) / 'grant.json'
        grant = {'grant_id': session.name, 'human_grant_reference': args.grant_reference.strip(),
            'subject': 'local-operator', 'audience': 'echo-nexus', 'purpose': 'bounded-interactive-session',
            'data_root': str(root), 'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
            'issued_at': started - 1, 'expires_at': expiry, 'revoked': False,
            'actions': ['cipher.chat', 'receipt.append'] + ([] if args.self_test else ['local.generate', 'local.context']) + (['local.orientation'] if orientation else []),
            'import_files': []}
        def save_grant():
            replacement = registry.with_suffix('.new')
            replacement.touch(mode=0o600)
            replacement.write_text(json.dumps({'schema_version': 1, 'charter_sha256': CHARTER_SHA256, 'grants': [grant]}))
            replacement.replace(registry)
        save_grant()
        os.environ.clear()
        os.environ.update(ECHO_NEXUS_ENABLE_DATA_ROUTES='1', ECHO_NEXUS_ROOT=str(root),
            ECHO_NEXUS_GRANTS_FILE=str(registry), ECHO_NEXUS_ENABLE_LOCAL_MODEL='0' if args.self_test else '1',
            ECHO_NEXUS_LOCAL_MODEL_PATH=str(args.model) if args.model else '',
            ECHO_NEXUS_ORIENTATION_SHA256=args.orientation_sha256 or '')
        spec = importlib.util.spec_from_file_location('session_server', REPO / 'habitat/cipher_server.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        httpd = make_server('127.0.0.1', 0, module.app, request_handler=Quiet)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        try:
            for index in range(5):
                # Reserve enough grant lifetime for a complete bounded worker attempt.
                remaining = min(expiry - time.time(), monotonic_end - time.monotonic()) - 190
                if remaining <= 0:
                    notes.append('Stopped admitting messages before grant expiry.')
                    break
                if args.self_test:
                    message = 'Synthetic session lifecycle check.'
                else:
                    print('You> ', end='', flush=True)
                    message = terminal.read(remaining)
                    if message is None:
                        notes.append('Input window ended; no authority renewal.')
                        break
                    if not message or message.strip() == '/quit':
                        break
                    message = message.strip()
                    if not message:
                        continue
                if len(message) > 4000:
                    print('Message too long; limit is 4000 characters.', flush=True)
                    continue
                request = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/cipher/chat',
                    data=json.dumps({'message': message, **({'orientation': orientation.decode('utf-8')} if orientation else {}), **({'context': history} if not args.self_test else {})}).encode(), headers={
                    'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token,
                    'X-Echo-Purpose': grant['purpose']})
                try:
                    try:
                        response = opener.open(request, timeout=190)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        status, raw = response.status, response.read()
                    body = json.loads(raw)
                    (session / f'response-{index + 1}.json').write_bytes(raw)
                    if status != 200:
                        failed = True
                        notes.append(f'HTTP {status}; stopped, no automatic retry.')
                        print('Exchange stopped:', body.get('error'), flush=True)
                        break
                    responses.append(raw)
                    history.extend([{'role': 'user', 'content': message},
                                    {'role': 'assistant', 'content': body['reply']}])
                    dropped = False
                    while len(history) > 6 or sum(len(entry['content']) for entry in history) > 4096:
                        del history[:2]
                        dropped = True
                    if dropped:
                        print('[Oldest context removed to stay within the session limit.]', flush=True)
                    print('Cipher>', body['reply'], flush=True)
                    print('[completed_unverified]', flush=True)
                    if body.get('generation', {}).get('finish_reason') == 'length':
                        print('[Output limit reached; this reply may be incomplete.]', flush=True)
                    elif body.get('generation', {}).get('finish_reason') == 'unknown':
                        print('[Generation stop reason unknown; completeness is unverified.]', flush=True)
                except (OSError, ValueError):
                    failed = True
                    notes.append('Client I/O failed; effects may have occurred. No retry.')
                    break
                if args.self_test:
                    break
        except (OSError, ValueError):
            failed = True
            notes.append('Input unavailable; stopped without retry.')
        except KeyboardInterrupt:
            notes.append('Operator interrupted; any in-flight computation is allowed to finish or time out before evidence verification.')
        finally:
            # Finish the bounded shutdown once; repeated signals cannot skip cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            grant['revoked'] = True
            revoked = False
            try:
                save_grant()
                revoked = True
            except OSError:
                failed = True
                notes.append('Grant revocation write failed; server shutdown still attempted.')
            finally:
                # Removing the registry also makes subsequent authority checks fail closed.
                try:
                    registry.unlink(missing_ok=True)
                except OSError:
                    failed = True
                    notes.append('Registry removal failed; temporary-directory cleanup will retry.')
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError('Server shutdown not confirmed')
            token = None
        results = []
        ledger_path = root / 'receipts/execution.jsonl'
        if responses:
            try:
                ledger = ledger_path.read_bytes()
                memory = (root / 'memory/streams/root_memory.jsonl').read_bytes()
                tip = json.loads(ledger.splitlines()[-1])['hash_self']
                for raw in responses:
                    request_id = json.loads(raw)['receipt']['request_id']
                    results.append(verify_exchange(ledger, memory, raw, request_id, tip, orientation=orientation))
            except (EvidenceError, OSError, ValueError, KeyError, IndexError):
                failed = True
                notes.append('Evidence check failed; preserve files for review.')
        else:
            notes.append('No completed response available to verify.')
        report = {'commit': sha, 'checkout_dirty': dirty, 'self_test': args.self_test, 'backend': 'local_stub' if args.self_test else 'local_model',
            'server_stopped': True, 'grant_revoked': revoked, 'completed_responses': len(responses),
            'verifications': results, 'notes': notes, 'task_success_verified': False,
            'tip_provenance': 'Read from stopped-server snapshot; not an independent trusted anchor.'}
    report['temporary_credentials_removed'] = True
    (session / 'session-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Server stopped; temporary credentials removed. Saved report:', session / 'session-report.json', flush=True)
    return 0 if not failed and len(results) == len(responses) else 1

if __name__ == '__main__':
    raise SystemExit(main())
