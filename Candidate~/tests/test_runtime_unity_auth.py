"""Actual HTTP/WS with synthetic principals; not TLS/Unity acceptance."""
import asyncio
from contextlib import asynccontextmanager
import inspect
import json
from pathlib import Path
import socket
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'native/src')]
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from fastmcp import Client
import httpx
import uvicorn
import websockets
from candidate_auth import CandidateJWTVerifier
from candidate_runtime import create_app, create_server
from transport.plugin_hub import PluginHub


class UnityAuthTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def fixture(self, ttl=60):
        self.assertIn('unity_auth', inspect.signature(create_app).parameters,
                      'authenticated native Unity ingress is missing')
        keys = RSAKeyPair.generate()
        def verifier(audience, principal, scope):
            return CandidateJWTVerifier(public_key=keys.public_key,
                issuer='fixture-run', audience=audience, principals=(principal,), required_scope=scope)
        mcp_auth = CandidateJWTVerifier(public_key=keys.public_key, issuer='fixture-run',
            audience='fixture-mcp', principals=('fixture-client', 'fixture-client-b'), required_scope='candidate:mcp')
        unity_auth = verifier('fixture-unity', 'fixture-editor', 'candidate:unity')
        def issue(audience, principal, scope):
            return keys.create_token(subject=principal, issuer='fixture-run', audience=audience,
                scopes=[scope], expires_in_seconds=ttl, additional_claims={'client_id': principal})
        tokens = {'unity': issue('fixture-unity', 'fixture-editor', 'candidate:unity'),
                  'mcp': issue('fixture-mcp', 'fixture-client', 'candidate:mcp'),
                  'mcp-b': issue('fixture-mcp', 'fixture-client-b', 'candidate:mcp'),
                  'wrong-project-principal': issue('fixture-unity', 'other-editor', 'candidate:unity')}
        mcp = create_server('fixture-project', mcp_auth=mcp_auth)
        app = create_app(mcp, unity_auth=unity_auth)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False,
                ws_max_size=1024*1024, timeout_graceful_shutdown=3))
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(5):
                    while not server.started:
                        if task.done():
                            await task
                            self.fail('server ended before readiness')
                        await asyncio.sleep(.01)
                yield f'ws://127.0.0.1:{port}/hub/plugin', tokens, mcp
            finally:
                server.should_exit = True
                await asyncio.wait_for(task, 6)
        with socket.socket() as probe:
            probe.settimeout(.2)
            self.assertNotEqual(probe.connect_ex(('127.0.0.1', port)), 0)
        self.assertEqual(await PluginHub._registry.list_sessions(), {})
        self.assertEqual(PluginHub._connections, {})
        self.assertEqual(PluginHub._pending, {})
        self.assertEqual(PluginHub._ping_tasks, {})
        self.assertEqual(mcp._candidate_runtime.sessions, {})

    def connect(self, url, token):
        return websockets.connect(url, proxy=None, additional_headers={'Authorization': 'Bearer '+token})

    async def register(self, ws):
        self.assertEqual(json.loads(await ws.recv())['type'], 'welcome')
        await ws.send(json.dumps({'type':'register', 'project_hash':'fixture-project',
                                 'project_name':'fixture', 'unity_version':'fixture'}))
        reply = json.loads(await ws.recv())
        self.assertEqual(reply['type'], 'registered')
        return reply['session_id']

    async def test_UA101_signed_editor_connects_native_registry_and_roles_do_not_cross(self):
        async with self.fixture() as (url, tokens, mcp):
            for token in ('not-a-jwt', tokens['mcp'], tokens['wrong-project-principal']):
                with self.assertRaises(websockets.exceptions.InvalidStatus):
                    async with self.connect(url, token):
                        self.fail('unassigned credential accepted')
            self.assertEqual(await PluginHub._registry.list_sessions(), {})
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                async with asyncio.timeout(2):
                    while (session := await PluginHub._registry.get_session(sid)) is None:
                        await asyncio.sleep(.01)
                self.assertEqual(session.user_id, 'fixture-editor')
                self.assertEqual(await mcp._candidate_runtime.connection(), sid)
                http_url = url.replace('ws:', 'http:').removesuffix('/hub/plugin')+'/mcp'
                async with httpx.AsyncClient(trust_env=False) as raw:
                    denied = await raw.post(http_url, headers={'Authorization':'Bearer '+tokens['unity'],
                        'Accept':'application/json, text/event-stream'},
                        json={'jsonrpc':'2.0','id':1,'method':'ping'})
                    self.assertEqual(denied.status_code, 401)
                async with Client(http_url, auth=tokens['mcp']) as client:
                    self.assertEqual({t.name for t in await client.list_tools()}, {'agent_status','agent_catalog','agent_prepare','agent_stop','manage_animation','manage_material','read_console','manage_scene','find_gameobjects','get_gameobject','get_gameobject_components','get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items','manage_packages','manage_script','get_sha','manage_shader','unity_reflect','get_test_job','manage_asset','manage_prefabs','get_tests','material_prepare','material_execute','material_status','material_stop'})

    async def test_UA102_signed_editor_cannot_register_a_different_project(self):
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                self.assertEqual(json.loads(await ws.recv())['type'], 'welcome')
                await ws.send(json.dumps({'type':'register', 'project_hash':'other-project'}))
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    await asyncio.wait_for(ws.recv(), 2)
                self.assertEqual(await PluginHub._registry.list_sessions(), {})

    async def test_UA103_one_admitted_socket_cannot_be_replaced_or_automatically_reconnected(self):
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                with self.assertRaises(websockets.exceptions.InvalidStatus):
                    async with self.connect(url, tokens['unity']):
                        self.fail('second connection admitted for the same run')
                self.assertEqual(await mcp._candidate_runtime.connection(), sid)
            with self.assertRaises(websockets.exceptions.InvalidStatus):
                async with self.connect(url, tokens['unity']):
                    self.fail('disconnection silently restored the old run')

    async def test_UA104_expiry_closes_idle_socket_and_revokes_both_plan_families(self):
        from candidate_runtime import Plan
        import time
        async with self.fixture(ttl=3) as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                runtime = mcp._candidate_runtime
                plan = Plan('fixture-task', sid, time.monotonic()+60, frozenset(), frozenset(), 'fixture-plan')
                runtime.plans['fixture-client'] = plan
                runtime.material.plans['fixture-client'] = plan
                try:
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):
                        await asyncio.wait_for(ws.recv(), 5)
                except asyncio.TimeoutError:
                    self.fail('expired credential retained an idle native Unity socket')
                async with asyncio.timeout(2):
                    while runtime.plans or runtime.material.plans:
                        await asyncio.sleep(.01)
                self.assertEqual(runtime.plans, {})
                self.assertEqual(runtime.material.plans, {})

    async def test_UA105_principal_rechecked_before_native_and_material_dispatch(self):
        from dataclasses import replace
        from unittest.mock import AsyncMock, patch, Mock
        from fastmcp.exceptions import ToolError
        from candidate_runtime import Invocation, _CURRENT
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                runtime = mcp._candidate_runtime
                real = await PluginHub._registry.get_session(sid)
                forged = replace(real, user_id='untrusted-editor')
                with patch.object(PluginHub._registry, 'list_sessions', AsyncMock(return_value={sid:forged})):
                    with self.assertRaises(ToolError):
                        await runtime.connection()
                for command in ('agent_status', 'material_status'):
                    token = _CURRENT.set(Invocation(runtime, 'fixture-client', command, {}))
                    try:
                        with patch.object(PluginHub._registry, 'get_session', AsyncMock(return_value=forged)), \
                             patch.object(runtime.material, 'envelope', Mock(return_value=('unsafe',{}))) as dispatch:
                            with self.assertRaises(ToolError):
                                await runtime.envelope(sid, command, {})
                            dispatch.assert_not_called()
                    finally:
                        _CURRENT.reset(token)

    async def test_UA106_peer_cannot_complete_a_foreign_pending_command(self):
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                await self.register(ws)
                future = asyncio.get_running_loop().create_future()
                PluginHub._pending['foreign-command'] = {'future':future, 'session_id':'foreign-session'}
                try:
                    await ws.send(json.dumps({'type':'command_result','id':'foreign-command',
                        'result':{'success':True, 'data':{'injected':True}}}))
                    try:
                        with self.assertRaises(websockets.exceptions.ConnectionClosed):
                            await asyncio.wait_for(ws.recv(), 1)
                    except asyncio.TimeoutError:
                        self.fail('foreign command result was not rejected at ingress')
                    self.assertFalse(future.done(), 'foreign command was completed by wrong connection')
                finally:
                    PluginHub._pending.pop('foreign-command', None)
                    if future.done() and not future.cancelled():
                        future.exception()
                    else:
                        future.cancel()

    async def test_UA107_editor_cannot_mutate_global_discovery_or_tool_visibility(self):
        from unittest.mock import AsyncMock, patch
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                await self.register(ws)
                with patch.object(PluginHub, '_handle_register_tools', AsyncMock()) as discovery:
                    await ws.send(json.dumps({'type':'register_tools', 'tools':[]}))
                    try:
                        with self.assertRaises(websockets.exceptions.ConnectionClosed):
                            await asyncio.wait_for(ws.recv(), 1)
                    except asyncio.TimeoutError:
                        self.fail('global discovery message reached candidate native ingress')
                    discovery.assert_not_called()

    async def test_UA108_factory_requires_disjoint_finite_role_policies(self):
        from fastmcp.server.auth.providers.jwt import JWTVerifier
        keys = RSAKeyPair.generate()
        def policy(audience='fixture-unity', principals=('fixture-editor',), scope='candidate:unity'):
            return CandidateJWTVerifier(public_key=keys.public_key, issuer='fixture-run',
                audience=audience, principals=principals, required_scope=scope)
        mcp = create_server('fixture-project', mcp_auth=policy('fixture-mcp', ('fixture-client',), 'candidate:mcp'))
        for bad in (policy('fixture-mcp'), policy(principals=('fixture-client',)),
                    policy(principals=('fixture-editor','extra-editor')), policy(scope='candidate:mcp'),
                    JWTVerifier(public_key=keys.public_key, algorithm='RS256')):
            with self.subTest(policy_type=type(bad).__name__):
                with self.assertRaises(ValueError):
                    create_app(mcp, unity_auth=bad)

    async def test_UA109_authenticated_native_command_wire_and_response_readback(self):
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                await ws.send(json.dumps({'type':'pong', 'session_id':sid}))
                http_url = url.replace('ws:', 'http:').removesuffix('/hub/plugin')+'/mcp'
                async with Client(http_url, auth=tokens['mcp']) as client:
                    async def peer():
                        wire = json.loads(await ws.recv())
                        self.assertEqual(wire['type'], 'execute')
                        self.assertEqual(wire['name'], 'vrchat_agent_dispatch')
                        self.assertEqual(wire['params']['kind'], 'status')
                        self.assertEqual(wire['params']['project_id'], 'fixture-project')
                        self.assertEqual(wire['params']['connection_id'], sid)
                        await ws.send(json.dumps({'type':'command_result', 'id':wire['id'],
                            'result':{'success':True, 'data':{'probe':'native-auth-readback'}}}))
                    task = asyncio.create_task(peer())
                    try:
                        result = await asyncio.wait_for(client.call_tool('agent_status', {}), 3)
                        await asyncio.wait_for(task, 3)
                        self.assertFalse(result.is_error)
                        self.assertIn('native-auth-readback', str(result))
                    finally:
                        if not task.done():
                            task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                self.assertEqual(PluginHub._pending, {})

    async def test_UA110_repeated_registration_closes_and_removes_original_session(self):
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                await ws.send(json.dumps({'type':'register', 'project_hash':'fixture-project'}))
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    await asyncio.wait_for(ws.recv(), 2)
                async with asyncio.timeout(2):
                    while await PluginHub._registry.get_session(sid) is not None:
                        await asyncio.sleep(.01)

    async def test_UA111_foreign_pong_rejected_before_native_session_touch(self):
        from unittest.mock import AsyncMock, patch
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                await self.register(ws)
                with patch.object(PluginHub, '_handle_pong', AsyncMock()) as pong:
                    await ws.send(json.dumps({'type':'pong', 'session_id':'foreign-session'}))
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):
                        await asyncio.wait_for(ws.recv(), 2)
                    pong.assert_not_called()

    async def test_UA112_expiry_while_receive_waits_rejected_before_native_handler(self):
        import time
        from unittest.mock import AsyncMock, patch
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                with patch.object(PluginHub, '_handle_pong', AsyncMock()) as pong:
                    # Deterministic final-check race after native receive has begun.
                    mcp._candidate_runtime.unity_ingress.deadline = time.monotonic()-1
                    await ws.send(json.dumps({'type':'pong', 'session_id':sid}))
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):
                        await asyncio.wait_for(ws.recv(), 2)
                    pong.assert_not_called()

    async def test_UA113_revokes_before_awaiting_native_disconnect_cleanup(self):
        from unittest.mock import patch
        async with self.fixture() as (url, tokens, mcp):
            entered, release = asyncio.Event(), asyncio.Event()
            original = PluginHub.on_disconnect
            async def delayed(hub, websocket, close_code):
                entered.set()
                await release.wait()
                return await original(hub, websocket, close_code)
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                with patch.object(PluginHub, 'on_disconnect', delayed):
                    try:
                        await ws.send(json.dumps({'type':'register', 'project_hash':'fixture-project'}))
                        await asyncio.wait_for(entered.wait(), 2)
                        from fastmcp.exceptions import ToolError
                        with self.assertRaises(ToolError, msg='revocation must precede awaited native cleanup'):
                            await mcp._candidate_runtime.connection()
                    finally:
                        release.set()

    async def test_UA114_owned_native_route_never_uses_global_discovery_or_reload_retry(self):
        from unittest.mock import AsyncMock, patch
        from candidate_runtime import Invocation, _CURRENT
        from fastmcp.exceptions import ToolError
        async with self.fixture() as (url, tokens, mcp):
            async with self.connect(url, tokens['unity']) as ws:
                sid = await self.register(ws)
                runtime = mcp._candidate_runtime
                with patch.object(PluginHub, '_resolve_session_id', AsyncMock(side_effect=AssertionError('global resolution reached'))) as global_resolve:
                    with self.assertRaises(ToolError):
                        await PluginHub.send_command_for_instance('fixture-project', 'agent_status', {})
                    token = _CURRENT.set(Invocation(runtime, 'test-synthetic-client', 'agent_status', {}))
                    try:
                        for project, user in [('foreign', None), (None, None), ('fixture-project', 'foreign-principal')]:
                            with self.assertRaises(ToolError):
                                await PluginHub.send_command_for_instance(project, 'agent_status', {}, user_id=user)
                        with patch.object(PluginHub, 'send_command', AsyncMock(return_value={'success': True})) as send:
                            await PluginHub.send_command_for_instance('fixture-project', 'agent_status', {})
                            send.assert_awaited_once_with(sid, 'agent_status', {})
                        # Even though the upstream call defaults retry_on_reload=True,
                        # admission expiry rejects immediately, never adopting another peer.
                        runtime.unity_ingress.revoke()
                        with self.assertRaises(ToolError):
                            await asyncio.wait_for(PluginHub.send_command_for_instance('fixture-project', 'agent_status', {}), .5)
                    finally:
                        _CURRENT.reset(token)
                    global_resolve.assert_not_called()
