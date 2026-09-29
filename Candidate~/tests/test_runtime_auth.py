"""Real SDK HTTP principal isolation with ephemeral synthetic JWTs only.

No Unity/real client config or durable secrets; does not prove sidecar identity.
"""
import asyncio
from contextlib import asynccontextmanager
import socket
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'runtime'), str(ROOT / 'native/src')]

from fastmcp import Client
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
import httpx
import uvicorn

from candidate_runtime import create_app, create_server


class AuthHTTPTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def fixture(self):
        keys = RSAKeyPair.generate()
        issuer, audience = 'candidate-fixture-issuer', 'candidate-fixture-mcp'
        from candidate_auth import CandidateJWTVerifier
        verifier = CandidateJWTVerifier(public_key=keys.public_key,
            issuer=issuer, audience=audience, required_scope='candidate:mcp',
            principals=('fixture-client-a', 'fixture-client-b'))
        tokens = {name: keys.create_token(subject=name, issuer=issuer, audience=audience,
                  scopes=['candidate:mcp'], expires_in_seconds=60,
                  additional_claims={'client_id': name})
                  for name in ('fixture-client-a', 'fixture-client-b')}
        tokens['wrong-audience'] = keys.create_token(subject='fixture-client-a', issuer=issuer,
            audience='not-this-sidecar', scopes=['candidate:mcp'], expires_in_seconds=60)
        tokens['expired'] = keys.create_token(subject='fixture-client-a', issuer=issuer,
            audience=audience, scopes=['candidate:mcp'], expires_in_seconds=-60)
        tokens['wrong-scope'] = keys.create_token(subject='fixture-client-a', issuer=issuer,
            audience=audience, scopes=['candidate:unity'], expires_in_seconds=60)
        tokens['wrong-key'] = RSAKeyPair.generate().create_token(subject='fixture-client-a',
            issuer=issuer, audience=audience, scopes=['candidate:mcp'], expires_in_seconds=60)
        tokens['no-expiry'] = keys.create_token(subject='fixture-client-a', issuer=issuer,
            audience=audience, scopes=['candidate:mcp'],
            additional_claims={'client_id': 'fixture-client-a', 'exp': None})
        tokens['no-explicit-client'] = keys.create_token(subject='fixture-client-a', issuer=issuer,
            audience=audience, scopes=['candidate:mcp'])
        tokens['unassigned-client'] = keys.create_token(subject='fixture-unassigned', issuer=issuer,
            audience=audience, scopes=['candidate:mcp'],
            additional_claims={'client_id': 'fixture-unassigned'})
        mcp = create_server('auth-fixture-project', mcp_auth=verifier)
        app = create_app(mcp)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, log_level='error',
                access_log=False, timeout_graceful_shutdown=3))
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(5):
                    while not server.started:
                        if task.done():
                            await task
                            self.fail('fixture server ended before readiness')
                        await asyncio.sleep(.01)
                yield f'http://127.0.0.1:{port}/mcp', tokens, mcp, verifier
            finally:
                server.should_exit = True
                await asyncio.wait_for(task, 6)
        with socket.socket() as check:
            check.settimeout(.2)
            self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0)
        self.assertTrue(task.done())
        self.assertEqual(mcp._candidate_runtime.sessions, {})

    async def test_AU005_authenticated_mcp_must_not_leave_unity_socket_unauthenticated(self):
        import websockets
        async with self.fixture() as (url, tokens, server, verifier):
            for path in ('/hub/plugin', '/hub'):
                with self.subTest(path=path):
                    with self.assertRaises(websockets.exceptions.InvalidStatus):
                        async with websockets.connect(url.removesuffix('/mcp').replace('http:', 'ws:') + path,
                                                      proxy=None):
                            self.fail('unauthenticated Unity peer reached the native hub')

    def test_AU004_empty_or_ambiguous_trusted_policy_is_rejected_at_construction(self):
        from candidate_auth import CandidateJWTVerifier
        key = RSAKeyPair.generate().public_key
        base = dict(public_key=key, issuer='fixture-issuer', audience='fixture-audience',
                    principals=('fixture-a', 'fixture-b'), required_scope='candidate:mcp')
        bad = [('issuer', ''), ('issuer', None), ('audience', ''), ('audience', ['fixture-audience']),
               ('required_scope', ''), ('principals', 'fixture-a'), ('principals', ()),
               ('principals', ('fixture-a', 'fixture-a')), ('principals', ('unknown',)),
               ('principals', (' fixture-a',)), ('principals', (None,))]
        for field, value in bad:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    CandidateJWTVerifier(**{**base, field: value})

    async def test_AU003_valid_signature_does_not_replace_explicit_finite_client_binding(self):
        async with self.fixture() as (url, tokens, server, verifier):
            async with httpx.AsyncClient(trust_env=False, timeout=3) as raw:
                for label in ('no-expiry', 'no-explicit-client', 'unassigned-client'):
                    with self.subTest(label=label):
                        response = await raw.post(url, headers={
                            'accept': 'application/json, text/event-stream',
                            'authorization': 'Bearer ' + tokens[label]},
                            json={'jsonrpc': '2.0', 'id': 'not-authorized', 'method': 'ping'})
                        self.assertEqual(response.status_code, 401)
            self.assertEqual(server._candidate_runtime.sessions, {})

    async def test_AU002_existing_jwt_verifier_rejects_bad_bearers_on_real_http(self):
        # Characterization of the fixed upstream verifier; not a manufactured RED.
        async with self.fixture() as (url, tokens, server, verifier):
            async with httpx.AsyncClient(trust_env=False, timeout=3) as raw:
                for label in ('missing', 'malformed', 'wrong-audience', 'expired', 'wrong-scope', 'wrong-key'):
                    headers = {'accept': 'application/json, text/event-stream'}
                    if label != 'missing':
                        headers['authorization'] = 'Bearer ' + tokens.get(label, 'not-a-jwt')
                    with self.subTest(label=label):
                        response = await raw.post(url, headers=headers,
                            json={'jsonrpc': '2.0', 'id': 'unauthorized', 'method': 'ping'})
                        self.assertEqual(response.status_code, 401)
            self.assertEqual(server._candidate_runtime.sessions, {})
            self.assertEqual(server._candidate_runtime.plans, {})
            self.assertEqual(server._candidate_runtime.material.plans, {})

    async def test_AU001_different_signed_principal_cannot_use_or_delete_owner_session(self):
        async with self.fixture() as (url, tokens, server, verifier):
            async with Client(url, auth=tokens['fixture-client-a']) as owner:
                self.assertEqual(len(await owner.list_tools()), 9)
                headers = {'accept': 'application/json, text/event-stream',
                    'authorization': 'Bearer ' + tokens['fixture-client-b'],
                    'mcp-session-id': owner.transport.get_session_id(),
                    'mcp-protocol-version': owner.initialize_result.protocolVersion}
                async with httpx.AsyncClient(trust_env=False, timeout=3) as raw:
                    for method in ('GET', 'POST', 'DELETE'):
                        with self.subTest(method=method):
                            body = {'jsonrpc': '2.0', 'id': 'cross-principal',
                                    'method': 'ping'} if method == 'POST' else None
                            response = await raw.request(method, url, headers=headers, json=body)
                            self.assertEqual(response.status_code, 404)
                self.assertTrue(await owner.ping(), 'foreign DELETE must not close owner session')
            async with Client(url, auth=tokens['fixture-client-b']) as other:
                self.assertEqual(len(await other.list_tools()), 9)
            self.assertEqual(server._candidate_runtime.plans, {})
            self.assertEqual(server._candidate_runtime.material.plans, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
