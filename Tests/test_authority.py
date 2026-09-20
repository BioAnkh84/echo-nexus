"""Synthetic grant and HTTP boundary checks; no real data or provider calls."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

HABITAT = Path(__file__).resolve().parents[1] / 'habitat'
with patch.object(sys, 'path', [str(HABITAT), *sys.path]):
    from authority import AuthorityDenied, CHARTER_SHA256, authorize

TOKEN = 'synthetic_token_for_boundary_tests_only_1234567890'


class GrantFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        self.registry = Path(self.temp.name) / 'operator-grants.json'
        self.now = int(time.time())
        self.grant = {
            'grant_id': 'synthetic-grant', 'subject': 'synthetic-agent',
            'human_grant_reference': 'synthetic-human-approval-fixture',
            'audience': 'echo-nexus', 'purpose': 'synthetic-check',
            'data_root': str(self.root),
            'token_sha256': hashlib.sha256(TOKEN.encode()).hexdigest(),
            'issued_at': self.now - 60, 'expires_at': self.now + 600,
            'revoked': False, 'actions': ['cipher.log'], 'import_files': [],
        }
        self.save()
        self.headers = {'Authorization': 'Bearer ' + TOKEN,
                        'X-Echo-Purpose': 'synthetic-check'}

    def save(self):
        self.registry.write_text(json.dumps({'schema_version': 1,
            'charter_sha256': CHARTER_SHA256, 'grants': [self.grant]}))
        self.registry.chmod(0o600)

    def check(self, **kwargs):
        return authorize(self.registry, self.headers['Authorization'],
                         self.headers['X-Echo-Purpose'], 'cipher.log',
                         data_root=self.root, **kwargs)


class GrantTests(GrantFixture, unittest.TestCase):
    def test_valid_grant_is_scoped_permission(self):
        permission = self.check()
        self.assertEqual(permission.grant_id, 'synthetic-grant')
        self.assertEqual(permission.actions, frozenset({'cipher.log'}))
        self.assertFalse(self.root.exists())

    def test_expired_future_revoked_wrong_scope_and_malformed_fail_closed(self):
        original = copy.deepcopy(self.grant)
        mutations = [
            {'expires_at': self.now}, {'issued_at': self.now + 1},
            {'revoked': True}, {'revoked': 'false'}, {'audience': 'another-server'},
            {'data_root': str(self.root / 'other')}, {'purpose': 'other'},
            {'actions': ['cipher.chat']}, {'actions': ['*']},
            {'human_grant_reference': ''}, {'subject': None},
            {'issued_at': True}, {'expires_at': float('inf')},
        ]
        for change in mutations:
            with self.subTest(change=change):
                self.grant = dict(original, **change)
                self.save()
                with self.assertRaises(AuthorityDenied):
                    self.check(now=self.now)
        self.grant = original

    def test_unknown_token_missing_file_and_bad_registry(self):
        self.headers['Authorization'] = 'Bearer ' + 'B' * 43
        with self.assertRaises(AuthorityDenied):
            self.check()
        self.headers['Authorization'] = 'Bearer ' + TOKEN
        for raw in ('[]', '{', '{"schema_version":1,"grants":[]}',
                    json.dumps({'schema_version': 1, 'charter_sha256': 'other',
                                'grants': [self.grant]})):
            self.registry.write_text(raw)
            with self.assertRaises(AuthorityDenied):
                self.check()
        self.registry.unlink()
        with self.assertRaises(AuthorityDenied):
            self.check()

    def test_registry_is_private_regular_file_not_symlink(self):
        self.registry.chmod(0o644)
        with self.assertRaises(AuthorityDenied):
            self.check()
        self.registry.chmod(0o600)
        target = self.registry.with_suffix('.saved')
        self.registry.rename(target)
        self.registry.symlink_to(target)
        with self.assertRaises(AuthorityDenied):
            self.check()
        self.registry.unlink()
        os.mkfifo(self.registry, 0o600)
        with self.assertRaises(AuthorityDenied):
            self.check()

    def test_ambiguous_registry_json_is_rejected(self):
        payload = json.dumps({'schema_version': 1, 'charter_sha256': CHARTER_SHA256,
                              'grants': [self.grant]})
        for invalid in (payload.replace('"revoked": false', '"revoked": true, "revoked": false'),
                        payload.replace('"schema_version": 1', '"schema_version": 0, "schema_version": 1'),
                        payload.replace('"revoked": false', '"unknown": NaN, "revoked": false')):
            with self.subTest(payload=invalid):
                self.registry.write_text(invalid)
                with self.assertRaises(AuthorityDenied):
                    self.check()

    def test_duplicate_token_or_grant_id_rejected(self):
        for second in (self.grant, dict(self.grant, grant_id='second')):
            self.registry.write_text(json.dumps({'schema_version': 1,
                'charter_sha256': CHARTER_SHA256, 'grants': [self.grant, second]}))
            with self.assertRaises(AuthorityDenied):
                self.check()


@unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask missing')
class HttpAuthorityTests(GrantFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {
            'ECHO_NEXUS_ENABLE_DATA_ROUTES': '1',
            'ECHO_NEXUS_ROOT': str(self.root),
            'ECHO_NEXUS_GRANTS_FILE': str(self.registry),
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        spec = importlib.util.spec_from_file_location('authority_test_server', HABITAT / 'cipher_server.py')
        self.server = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', [str(HABITAT), *sys.path]):
            spec.loader.exec_module(self.server)
        self.http = self.server.app.test_client()

    def test_every_protected_route_rejects_missing_credentials_without_side_effects(self):
        with patch.object(self.server, 'get_client', side_effect=AssertionError('provider')), \
             patch.object(self.server, 'append_jsonl', side_effect=AssertionError('write')), \
             patch.object(self.server, 'read_memory_tail', side_effect=AssertionError('read')), \
             patch.object(self.server, 'read_import', side_effect=AssertionError('import')):
            for rule in self.server.app.url_map.iter_rules():
                if rule.endpoint in {'health', 'echo_status', 'cipher_client_page'}:
                    continue
                method = 'POST' if 'POST' in rule.methods else 'GET'
                result = self.http.open(rule.rule, method=method,
                    json={'purpose_token': {'consent': 'Richard Rice'}, 'message': 'synthetic'})
                self.assertEqual(result.status_code, 403, rule.rule)
        self.assertFalse(self.root.exists())

    def test_admitted_write_records_grant_not_caller_identity_as_authority(self):
        response = self.http.post('/cipher/log', headers=self.headers,
            json={'summary': 'synthetic', 'text': 'fixture', 'author': 'spoofed-human'})
        self.assertEqual(response.status_code, 200)
        entry = json.loads(self.server.MEMORY_STREAM.read_text())
        self.assertEqual(entry['authorization']['subject'], 'synthetic-agent')
        self.assertEqual(entry['authorization']['grant_id'], self.grant['grant_id'])
        self.assertNotIn(TOKEN, self.server.MEMORY_STREAM.read_text())

    def test_route_purpose_revocation_and_expiry_reject_before_write(self):
        original = copy.deepcopy(self.grant)
        for change in ({'actions': ['cipher.chat', 'receipt.append']}, {'purpose': 'other'},
                       {'revoked': True}, {'expires_at': self.now - 1}):
            self.grant = dict(original, **change)
            self.save()
            result = self.http.post('/cipher/log', headers=self.headers,
                                   json={'summary': 'synthetic', 'text': 'fixture'})
            self.assertEqual(result.status_code, 403)
        self.assertFalse(self.root.exists())

    def test_live_registry_revocation_stops_next_side_effect(self):
        self.grant['actions'] = ['cipher.chat', 'receipt.append']
        self.save()
        def revoke(*args):
            self.grant['revoked'] = True
            self.save()
            return 'synthetic reply'
        with patch.object(self.server, 'generate_cipher_reply', side_effect=revoke):
            response = self.http.post('/cipher/chat', headers=self.headers, json={'message': 'test'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.server.MEMORY_STREAM.exists())
        self.assertFalse(self.server.VEXIS_MEMORY_STREAM.exists())

    def test_handshake_requires_bound_sender_target_scope_and_ttl(self):
        self.grant['actions'] = ['echo.handshake', 'receipt.append']
        self.save()
        body = {'from': 'synthetic-agent', 'to': 'Vexis@EchoNexus',
                'message': 'synthetic', 'purpose_token': {'scope': 'echo.handshake', 'ttl': self.now + 300}}
        invalid = [dict(body, **{'from': 'Richard Rice'}), dict(body, to='other'),
                   dict(body, purpose_token={'scope': 'anything', 'ttl': self.now + 300}),
                   dict(body, purpose_token={'scope': 'echo.handshake', 'ttl': self.now - 1}),
                   dict(body, purpose_token={'scope': 'echo.handshake', 'ttl': self.now + 9999}),
                   dict(body, purpose_token={'scope': 'echo.handshake', 'ttl': True})]
        with patch.object(self.server, 'generate_vexis_reply', side_effect=AssertionError('backend')):
            for payload in invalid:
                result = self.http.post('/echo/handshake', headers=self.headers, json=payload)
                self.assertEqual(result.status_code, 403)
        with patch.object(self.server, 'generate_vexis_reply', return_value='advisory') as reply:
            result = self.http.post('/echo/handshake', headers=self.headers, json=body)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(reply.call_args.kwargs['user'], 'synthetic-agent')
        self.assertEqual(result.json['verification'], 'not_independently_verified')
        self.assertNotIn('delta', result.json)
        self.assertNotIn('consent', result.json)

    def test_handshake_ttl_is_rechecked_before_write(self):
        self.grant['actions'] = ['echo.handshake', 'receipt.append']
        self.save()
        def advance(*args, **kwargs):
            clock = patch.object(self.server.time, 'time', return_value=self.now + 301)
            clock.start()
            self.addCleanup(clock.stop)
            return 'late response'
        with patch.object(self.server, 'generate_vexis_reply', side_effect=advance):
            response = self.http.post('/echo/handshake', headers=self.headers,
                json={'from': 'synthetic-agent', 'to': 'Vexis@EchoNexus', 'message': 'test',
                      'purpose_token': {'scope': 'echo.handshake', 'ttl': self.now + 300}})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.server.MEMORY_STREAM.exists())
        self.assertFalse(self.server.VEXIS_MEMORY_STREAM.exists())

    def test_external_and_memory_disclosures_need_distinct_grants(self):
        self.server.USE_OPENAI = True
        self.grant['actions'] = ['cipher.chat', 'receipt.append']
        self.save()
        with patch.object(self.server, 'get_client', side_effect=AssertionError('provider')):
            result = self.http.post('/cipher/chat', headers=self.headers, json={'message': 'test'})
            self.assertEqual(result.status_code, 403)
            self.grant['actions'].append('external.openai')
            self.save()
            self.server.SEND_MEMORY = True
            result = self.http.post('/cipher/chat', headers=self.headers, json={'message': 'test'})
            self.assertEqual(result.status_code, 403)
        self.assertFalse(self.root.exists())

    def test_revocation_during_client_setup_prevents_provider_request(self):
        self.server.USE_OPENAI = True
        self.grant['actions'] = ['cipher.chat', 'external.openai', 'receipt.append']
        self.save()
        backend = Mock()
        def revoke():
            self.grant['revoked'] = True
            self.save()
            return backend
        with patch.object(self.server, 'get_client', side_effect=revoke):
            response = self.http.post('/cipher/chat', headers=self.headers, json={'message': 'test'})
        self.assertEqual(response.status_code, 403)
        backend.chat.completions.create.assert_not_called()
        self.assertFalse(self.server.MEMORY_STREAM.exists())
        self.assertFalse(self.server.VEXIS_MEMORY_STREAM.exists())

    def test_revocation_after_read_prevents_response_disclosure(self):
        self.grant['actions'] = ['cipher.memory.read']
        self.save()
        def revoke(*args):
            self.grant['revoked'] = True
            self.save()
            return [{'summary': 'synthetic-private-content'}]
        with patch.object(self.server, 'read_memory_tail', side_effect=revoke):
            response = self.http.get('/cipher/memory/tail', headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('synthetic-private-content', response.get_data(as_text=True))
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_authorized_external_response_uses_mock_and_grant_subject(self):
        self.server.USE_OPENAI = True
        self.grant['actions'] = ['cipher.chat', 'external.openai', 'receipt.append']
        self.save()
        backend = Mock()
        backend.chat.completions.create.return_value = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='synthetic reply'))])
        with patch.object(self.server, 'get_client', return_value=backend):
            response = self.http.post('/cipher/chat', headers=self.headers,
                                     json={'message': 'test', 'user': 'spoofed'})
        self.assertEqual(response.status_code, 200)
        backend.chat.completions.create.assert_called_once()
        entries = [json.loads(line) for line in self.server.MEMORY_STREAM.read_text().splitlines()]
        self.assertEqual(entries[0]['author'], 'synthetic-agent')

    def test_import_is_allowlisted_and_rejects_paths_symlinks_and_nonobjects(self):
        self.grant['actions'] = ['cipher.import', 'vexis.import']
        self.grant['import_files'] = ['seed.json', 'link.json', 'array.json']
        self.save()
        imports = self.root / 'imports'
        imports.mkdir(parents=True)
        (imports / 'seed.json').write_text('{"identity":"synthetic"}')
        (imports / 'array.json').write_text('[]')
        secret = Path(self.temp.name) / 'outside.json'
        secret.write_text('{"private":"do not read"}')
        (imports / 'link.json').symlink_to(secret)
        for route in ('/cipher/import', '/vexis/import'):
            for filename in ('../outside.json', str(secret), 'unapproved.json', 'link.json', 'array.json'):
                with self.subTest(route=route, filename=filename):
                    result = self.http.post(route, headers=self.headers, json={'file': filename})
                    self.assertIn(result.status_code, (400, 403))
                    self.assertNotIn('private', result.get_data(as_text=True))
            response = self.http.post(route, headers=self.headers, json={'file': 'seed.json'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['seed'], {'identity': 'synthetic'})
        imports.rename(self.root / 'saved-imports')
        imports.symlink_to(self.root / 'saved-imports', target_is_directory=True)
        response = self.http.post('/cipher/import', headers=self.headers, json={'file': 'seed.json'})
        self.assertEqual(response.status_code, 400)

    def test_import_rejects_fifo_and_oversized_file(self):
        self.grant['actions'] = ['cipher.import']
        self.grant['import_files'] = ['fifo.json', 'large.json']
        self.save()
        imports = self.root / 'imports'
        imports.mkdir(parents=True)
        os.mkfifo(imports / 'fifo.json', 0o600)
        (imports / 'large.json').write_bytes(b' ' * (1024 * 1024 + 1))
        for filename in ('fifo.json', 'large.json'):
            response = self.http.post('/cipher/import', headers=self.headers, json={'file': filename})
            self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.server.CIPHER_STATE['seed'])

    def test_console_uses_headers_without_storage_or_auto_memory_fetch(self):
        page = self.http.get('/').get_data(as_text=True)
        self.assertIn('X-Echo-Purpose', page)
        self.assertIn("Authorization: 'Bearer ' + token", page)
        self.assertNotIn('localStorage', page)
        self.assertNotIn('sessionStorage', page)
        self.assertNotIn('window.onload = refreshTail', page)
        self.assertNotIn('await refreshTail()', page)
        self.assertFalse(self.root.exists())

    def test_unknown_route_options_and_nonobject_json_fail_closed(self):
        self.assertEqual(self.http.get('/new-route', headers=self.headers).status_code, 403)
        self.assertEqual(self.http.options('/cipher/log', headers=self.headers).status_code, 403)
        self.assertEqual(self.http.post('/cipher/log', headers=self.headers, json=[]).status_code, 400)
        self.assertFalse(self.root.exists())


if __name__ == '__main__':
    unittest.main()
