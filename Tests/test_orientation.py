"""Synthetic package, HTTP boundary and receipt snapshot tests; no personal exports."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_authority as fixtures
import test_local_model
import test_session
sys.path.insert(0, str(fixtures.HABITAT))
import orientation
from verify_exchange import verify_exchange, EvidenceError

def package():
    raw = json.dumps({'schema_version': 1, 'record_type': 'reviewed_historical_orientation',
        'notes': [{'id': 'historical_example', 'text': 'Historical test marker: lantern.',
                   'source_lines': [1], 'authority': 'orientation_only_not_permission'}],
        'source_refs': [{'line': 1}]}).encode()
    return raw, hashlib.sha256(raw).hexdigest()

class PackageTests(unittest.TestCase):
    def test_tamper_and_invalid_schema_are_rejected(self):
        raw, pin = package()
        for value in (raw + b' ', b'{}', b'x' * 32769):
            with self.assertRaises(orientation.OrientationError):
                orientation.validate(value, pin)
        for mutation in ('duplicate', 'oversize', 'missing_source', 'instruction'):
            data = json.loads(raw)
            if mutation == 'duplicate': data['notes'] *= 2
            if mutation == 'oversize': data['notes'][0]['text'] = 'x' * 4097
            if mutation == 'missing_source': data['source_refs'] = []
            if mutation == 'instruction': data['notes'][0]['authority'] = 'permission'
            value = json.dumps(data).encode()
            with self.assertRaises(orientation.OrientationError):
                orientation.validate(value, hashlib.sha256(value).hexdigest())

    def test_bounded_regular_file_and_symlink(self):
        raw, pin = package()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'package.json'; path.write_bytes(raw)
            self.assertEqual(orientation.load(path, pin), raw)
            link = Path(tmp) / 'link'; link.symlink_to(path)
            with self.assertRaises(OSError): orientation.load(link, pin)
            fifo = Path(tmp) / 'fifo'; os.mkfifo(fifo)
            with self.assertRaises(orientation.OrientationError): orientation.load(fifo, pin)

class HttpOrientationTests(test_local_model.LocalHttpTests):
    def send_orientation(self, raw):
        return self.http.post('/cipher/chat', headers=self.headers,
                              json={'message': 'historical marker?', 'orientation': raw.decode()})

    def test_missing_permission_and_pin_block_before_worker(self):
        self.enable(); raw, pin = package()
        with patch.dict(os.environ, {'ECHO_NEXUS_ORIENTATION_SHA256': pin}), patch.object(self.server, 'generate_local') as worker:
            self.assertEqual(self.send_orientation(raw).status_code, 403)
            self.grant['actions'].append('local.orientation'); self.save()
            self.assertEqual(self.send_orientation(raw + b' ').status_code, 400)
        worker.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_snapshot_required_and_tamper_detected(self):
        self.enable(); self.grant['actions'].append('local.orientation'); self.save()
        raw, pin = package()
        def worker(path, message, persona, check, **kwargs):
            check()
            self.assertEqual(kwargs['orientation'][0]['id'], 'historical_example')
            return 'lantern'
        with patch.dict(os.environ, {'ECHO_NEXUS_ORIENTATION_SHA256': pin}), patch.object(self.server, 'generate_local', side_effect=worker):
            response = self.send_orientation(raw)
        self.assertEqual(response.status_code, 200)
        args = ((self.root / 'receipts/execution.jsonl').read_bytes(), self.server.MEMORY_STREAM.read_bytes(),
                response.data, response.json['receipt']['request_id'], response.json['receipt']['tip'])
        self.assertTrue(verify_exchange(*args, orientation=raw)['orientation_snapshot_matched'])
        for snapshot in (None, raw + b' '):
            with self.assertRaises(EvidenceError): verify_exchange(*args, orientation=snapshot)

    def test_orientation_revoked_at_launch(self):
        self.enable(); self.grant['actions'].append('local.orientation'); self.save()
        raw, pin = package()
        def worker(path, message, persona, check, **kwargs):
            self.grant['actions'].remove('local.orientation'); self.save()
            check()
            raise AssertionError('Revoked permission must stop')
        with patch.dict(os.environ, {'ECHO_NEXUS_ORIENTATION_SHA256': pin}), patch.object(self.server, 'generate_local', side_effect=worker):
            self.assertEqual(self.send_orientation(raw).status_code, 403)
        self.assertFalse(self.server.MEMORY_STREAM.exists())

class OrientationSessionTests(test_session.SessionTests):
    def test_snapshot_cleanup_and_report(self):
        raw, pin = package()
        self.args.orientation = self.root / 'reviewed.json'
        self.args.orientation.write_bytes(raw)
        self.args.orientation_sha256 = pin
        def worker(*args, **kwargs):
            args[3]()
            self.assertEqual(kwargs['orientation'][0]['id'], 'historical_example')
            return 'lantern'
        code, report, folder = self.run_session(['marker?', '/quit'], worker)
        self.assertEqual(code, 0)
        self.assertEqual((folder / 'orientation.json').read_bytes(), raw)
        self.assertTrue(report['verifications'][0]['orientation_snapshot_matched'])


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for cls in (PackageTests, HttpOrientationTests, OrientationSessionTests):
        suite.addTests(cls(name) for name in cls.__dict__ if name.startswith('test_'))
    return suite
