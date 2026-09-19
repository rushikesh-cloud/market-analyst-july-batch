"""Real RSA verification at the API boundary, without external Clerk calls."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from app.main import app


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        env = patch.dict('os.environ', {
            'CLERK_ISSUER_URL': 'https://test.clerk.accounts.dev',
            'CLERK_AUTHORIZED_PARTIES': 'http://localhost:5173',
            'CLERK_ACCESS_MODE': 'approved_users',
            'CLERK_ALLOWED_USER_IDS': 'user_test',
            'CLERK_ADMIN_USER_IDS': '',
        })
        env.start()
        self.addCleanup(env.stop)
        keys = patch('app.auth.jwks_client')
        self.keys = keys.start().return_value
        self.keys.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())
        self.addCleanup(keys.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def token(self, remove=(), key=None, **changes):
        now = int(time.time())
        claims = dict(iss='https://test.clerk.accounts.dev', sub='user_test', sid='sess_test',
                      azp='http://localhost:5173', iat=now, nbf=now, exp=now + 60)
        claims.update(changes)
        for name in remove:
            claims.pop(name)
        return jwt.encode(claims, key or self.key, algorithm='RS256', headers={'kid': 'test'})

    def get_me(self, token):
        return self.client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})

    def test_every_data_route_requires_authentication(self):
        for route in app.routes:
            if not isinstance(route, APIRoute) or route.path == '/api/health':
                continue
            path = route.path.replace('{company_id}', 'missing').replace('{document_id}', 'missing')
            for method in route.methods:
                with self.subTest(path=path, method=method):
                    response = self.client.request(method, path)
                    self.assertEqual(response.status_code, 401, response.text)
                    self.assertEqual(response.headers['www-authenticate'], 'Bearer')
        self.keys.get_signing_key_from_jwt.assert_not_called()

    def test_valid_session_returns_verified_identity(self):
        response = self.get_me(self.token())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'user_id': 'user_test', 'role': 'general'})

    def test_rejects_expired_premature_foreign_or_pending_sessions(self):
        now = int(time.time())
        for changes in [
            {'exp': now - 1}, {'nbf': now + 60}, {'iat': now + 60},
            {'iss': 'https://other.clerk.accounts.dev'}, {'azp': 'https://attacker.example'},
            {'sts': 'pending'}, {'sid': ''}, {'sub': ''}, {'sub': 12}, {'sid': []},
            {'aud': 'custom-template'}, {'exp': 'invalid'},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(self.get_me(self.token(**changes)).status_code, 401)
        for claim in ['exp', 'nbf', 'iat', 'iss', 'sub', 'sid', 'azp']:
            with self.subTest(missing=claim):
                self.assertEqual(self.get_me(self.token(remove=[claim])).status_code, 401)

    def test_rejects_forged_malformed_and_wrong_algorithm_tokens(self):
        for token in [self.token(key=self.other_key), 'garbage',
                      jwt.encode({'sub': 'user_test'}, 'attacker-key-that-is-at-least-32-bytes', algorithm='HS256'),
                      jwt.encode({'sub': 'user_test'}, '', algorithm='none')]:
            self.assertEqual(self.get_me(token).status_code, 401)

    def test_cookie_or_user_header_cannot_bypass_bearer_auth(self):
        response = self.client.get('/api/auth/me', headers={
            'Cookie': f'__session={self.token()}', 'X-User-Id': 'user_test',
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Basic abc'}).status_code, 401)

    def test_workspace_access_policy(self):
        self.assertEqual(self.get_me(self.token(sub='user_other')).status_code, 403)
        with patch.dict('os.environ', {'CLERK_ACCESS_MODE': 'all_signed_in'}):
            self.assertEqual(self.get_me(self.token(sub='user_other')).status_code, 200)
        with patch.dict('os.environ', {'CLERK_ALLOWED_USER_IDS': ''}):
            self.assertEqual(self.get_me(self.token()).status_code, 403)
        with patch.dict('os.environ', {'CLERK_ACCESS_MODE': 'typo'}):
            self.assertEqual(self.get_me(self.token()).status_code, 503)

    def test_missing_configuration_fails_closed(self):
        for issuer in ['', 'http://test.example', 'https://test.example/path']:
            with patch.dict('os.environ', {'CLERK_ISSUER_URL': issuer}):
                self.assertEqual(self.get_me(self.token()).status_code, 503)
        with patch.dict('os.environ', {'CLERK_AUTHORIZED_PARTIES': ''}):
            self.assertEqual(self.get_me(self.token()).status_code, 503)

    def test_key_service_failures_do_not_leak_details(self):
        for error, status in [(PyJWKClientConnectionError('private details'), 503),
                              (PyJWKClientError('private details'), 401)]:
            self.keys.get_signing_key_from_jwt.side_effect = error
            response = self.get_me(self.token())
            self.assertEqual(response.status_code, status)
            self.assertNotIn('private details', response.text)

    def test_health_and_preflight_are_public(self):
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        response = self.client.options('/api/companies', headers={
            'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['access-control-allow-origin'], 'http://localhost:5173')
        response = self.client.options('/api/companies', headers={
            'Origin': 'https://attacker.example', 'Access-Control-Request-Method': 'POST',
        })
        self.assertNotIn('access-control-allow-origin', response.headers)


    def test_roles_are_assigned_by_server_not_token_claims(self):
        with patch.dict('os.environ', {'CLERK_ADMIN_USER_IDS': 'user_admin', 'CLERK_ACCESS_MODE': 'all_signed_in'}):
            self.assertEqual(self.get_me(self.token(sub='user_admin')).json(),
                             {'user_id': 'user_admin', 'role': 'admin'})
            self.assertEqual(self.get_me(self.token(role='admin', public_metadata={'role': 'admin'})).json(),
                             {'user_id': 'user_test', 'role': 'general'})
            self.assertEqual(self.get_me(self.token(sub='user_new')).json()['role'], 'general')

    def test_general_user_cannot_access_any_management_route(self):
        from app.companies import router as companies
        from app.documents import router as documents
        from app.document_search import router as search
        headers = {'Authorization': f'Bearer {self.token(role="admin")}', 'X-Role': 'admin'}
        for router in [companies, documents, search]:
            for route in router.routes:
                path = route.path.replace('{company_id}', 'missing').replace('{document_id}', 'missing')
                for method in route.methods:
                    with self.subTest(path=path, method=method):
                        response = self.client.request(method, path, headers=headers)
                        self.assertEqual(response.status_code, 403, response.text)

    def test_admin_can_manage_companies_and_general_user_can_select_them(self):
        import tempfile
        from sqlalchemy import create_engine
        from app import companies
        from app.analysis import api
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f'sqlite:///{folder}/roles.db')
            companies.Base.metadata.create_all(engine)
            self.addCleanup(engine.dispose)
            with patch.object(companies, 'engine', engine), patch.object(api, 'engine', engine), patch.dict(
                'os.environ', {'CLERK_ADMIN_USER_IDS': 'user_admin', 'CLERK_ACCESS_MODE': 'all_signed_in'}
            ):
                admin_headers = {'Authorization': f'Bearer {self.token(sub="user_admin")}'}
                response = self.client.post('/api/companies', json={'name': 'Reliance', 'ticker': 'RELIANCE'}, headers=admin_headers)
                self.assertEqual(response.status_code, 201, response.text)
                company = response.json()
                general_headers = {'Authorization': f'Bearer {self.token()}'}
                response = self.client.get('/api/analysis/companies', headers=general_headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), [company])
                self.assertEqual(self.client.get('/api/companies', headers=admin_headers).json(), [company])
                self.assertEqual(self.client.get('/api/analysis-agents', headers=general_headers).status_code, 200)
                self.assertEqual(self.client.post('/api/analysis/companies', json={'name': 'Bypass', 'ticker': 'BYPASS'}, headers=general_headers).status_code, 405)

    def test_admin_revocation_takes_effect_on_existing_session(self):
        headers = {'Authorization': f'Bearer {self.token()}'}
        with patch.dict('os.environ', {'CLERK_ADMIN_USER_IDS': 'user_test'}):
            self.assertEqual(self.get_me(self.token()).json()['role'], 'admin')
        self.assertEqual(self.client.get('/api/companies', headers=headers).status_code, 403)

    def test_general_user_can_submit_and_read_analysis_and_artifacts(self):
        from contextlib import ExitStack
        from datetime import datetime, timezone
        from app.analysis import api
        from app.analysis.contracts import CompanySnapshot
        company = CompanySnapshot(id='company', name='Reliance', ticker='RELIANCE.NS')
        run = SimpleNamespace(
            id='run', company_id='company', company_snapshot=company,
            agent_type='fundamental', status='queued', created_at=datetime.now(timezone.utc),
            started_at=None, finished_at=None, as_of=None, progress={}, result=None, error=None,
        )
        headers = {'Authorization': f'Bearer {self.token()}'}
        with ExitStack() as stack:
            stack.enter_context(patch.object(api, 'require_postgres'))
            stack.enter_context(patch.object(api, 'company_snapshot', return_value=company))
            stack.enter_context(patch.object(api, 'find_active_run', return_value=None))
            stack.enter_context(patch.object(api, 'registry'))
            stack.enter_context(patch.object(api, 'resolve_configuration'))
            enqueue = stack.enter_context(patch.object(api, 'enqueue_run', return_value=run))
            stack.enter_context(patch.object(api, 'list_runs', return_value=[run]))
            stack.enter_context(patch.object(api, 'get_run', return_value=run))
            store = stack.enter_context(patch.object(api, 'ArtifactStore'))
            store.return_value.read.return_value = SimpleNamespace(
                data=b'analysis evidence', metadata=SimpleNamespace(mime_type='text/plain', id='evidence.txt'),
            )
            response = self.client.post('/api/companies/company/analysis-runs', json={'agent_type': 'fundamental'}, headers=headers)
            self.assertEqual(response.status_code, 202, response.text)
            enqueue.assert_called_once()
            self.assertEqual(self.client.get('/api/companies/company/analysis-runs', headers=headers).json()['items'][0]['id'], 'run')
            self.assertEqual(self.client.get('/api/analysis-runs/run', headers=headers).json()['id'], 'run')
            response = self.client.get('/api/analysis-runs/run/artifacts/evidence', headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b'analysis evidence')
