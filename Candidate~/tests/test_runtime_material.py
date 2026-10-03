"""Real SDK + loopback HTTP/WS + native PluginHub. ONLY Unity is a peer fixture.
No Unity editor, native material mutation or local approval is claimed by this suite.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

from fastmcp import Client
import httpx
import uvicorn
import websockets
import test_runtime_lifecycle as fixtures
import test_runtime_idle as idle_fixture

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'native/src')]
ROUTE = 'vrchat_agent_material_dispatch'
TOOLS = {'material_prepare', 'material_execute', 'material_status', 'material_stop'}
MANIFEST = {'task_id': 'material-task', 'source': 'Assets/Original.mat',
    'candidate': 'Assets/Candidate.mat', 'operations': ['copy', 'edit', 'reference'],
    'references': [{'renderer': 'GlobalObjectId_V1-2-0123456789abcdef0123456789abcdef-1-0', 'slot': 0}], 'ttl_seconds': 60}
REPORT = {'status': 'completed', 'grant_active': True, 'readback': {'fixture_only': True, 'value': .6},
    'transaction': {'id': 'fixture-tx', 'action': 'edit', 'outcome': 'changed',
        'before': {'asset:Assets/Candidate.mat': 'before'},
        'after': {'asset:Assets/Candidate.mat': 'after'},
        'changed': ['asset:Assets/Candidate.mat'], 'side_effects': [],
        'direct_target': 'asset:Assets/Candidate.mat'}}


class MaterialHarness(unittest.IsolatedAsyncioTestCase):
    # Reuse actual SDK initialization/assertion helpers, not a simulated MCP server.
    post = idle_fixture.IdleTests.post
    result = idle_fixture.IdleTests.result
    initialize = idle_fixture.IdleTests.initialize
    wait_for_stop = fixtures.LifecycleHarness.wait_for_stop

    @asynccontextmanager
    async def running(self):
        from candidate_runtime import create_server, create_app
        from transport.plugin_hub import PluginHub
        with tempfile.TemporaryDirectory(prefix='runtime-material-home-') as home:
            old = os.environ.copy()
            os.environ.update(HOME=home, TMPDIR=home, DISABLE_TELEMETRY='true',
                UNITY_MCP_DISABLE_TELEMETRY='1', FASTMCP_CHECK_FOR_UPDATES='off')
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            server = create_server(fixtures.PROJECT)
            self.runtime = server._candidate_runtime
            service = uvicorn.Server(uvicorn.Config(create_app(server), log_level='error',
                access_log=False, lifespan='on', timeout_graceful_shutdown=3))
            serving = asyncio.create_task(service.serve(sockets=[listener]))
            self.events = []
            self.response_hook = None
            self.hold_kind = None
            self.entered, self.release = asyncio.Event(), asyncio.Event()
            self.release.set()
            workers = []
            responder = None
            sequence = 0
            try:
                async with asyncio.timeout(8):
                    while not service.started:
                        if serving.done():
                            await serving
                            self.fail('real runtime exited before readiness')
                        await asyncio.sleep(.02)
                self.url = f'http://127.0.0.1:{port}/mcp'
                async with websockets.connect(f'ws://127.0.0.1:{port}/hub/plugin', proxy=None) as peer:
                    self.peer = peer
                    self.assertEqual(json.loads(await peer.recv())['type'], 'welcome')
                    await peer.send(json.dumps({'type': 'register', 'project_name': 'NOT-UNITY-MaterialFixture',
                        'project_hash': fixtures.PROJECT, 'unity_version': 'FIXTURE'}))
                    self.connection_id = json.loads(await peer.recv())['session_id']

                    async def reply(message, number):
                        envelope = message['params']
                        kind = envelope['kind']
                        if kind == self.hold_kind:
                            self.entered.set()
                            await self.release.wait()
                        if kind == 'prepare':
                            result = {'success': True, 'data': {'status': 'pending',
                                'plan_id': f'fixture-plan-{number}', 'digest': 'fixture-digest'}}
                        elif kind == 'stop':
                            result = {'success': True, 'data': {'status': 'stopped', 'grant_active': False}}
                        elif kind == 'execute':
                            result = {'success': True, 'data': json.loads(json.dumps(REPORT))}
                        else:
                            result = {'success': True, 'data': {'transactions': [REPORT['transaction']],
                                'grant_active': False, 'capabilities': ['copy', 'edit', 'reference']}}
                        if self.response_hook:
                            result = self.response_hook(message, result)
                        await peer.send(json.dumps({'type': 'command_result', 'id': message['id'],
                            'result': {'status': 'success', 'result': result}}))

                    async def respond():
                        nonlocal sequence
                        async for raw in peer:
                            message = json.loads(raw)
                            if message['type'] == 'ping':
                                await peer.send(json.dumps({'type': 'pong', 'session_id': self.connection_id}))
                                continue
                            self.events.append(message)
                            sequence += 1
                            workers.append(asyncio.create_task(reply(message, sequence)))
                    responder = asyncio.create_task(respond())
                    yield
            finally:
                self.release.set()
                if responder:
                    responder.cancel()
                    await asyncio.gather(responder, return_exceptions=True)
                for worker in workers:
                    if not worker.done():
                        worker.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                service.should_exit = True
                try:
                    await asyncio.wait_for(serving, 8)
                finally:
                    listener.close()
                    os.environ.clear()
                    os.environ.update(old)
                self.assertEqual(PluginHub._pending, {})
                self.assertEqual(PluginHub._connections, {})
                self.assertEqual(await PluginHub._registry.list_sessions(), {})
                self.assertEqual(self.runtime.sessions, {})
                self.assertEqual(self.runtime.preparing, {})
                if hasattr(self.runtime, 'material'):
                    self.assertEqual(self.runtime.material.plans, {})
                    self.assertEqual(self.runtime.material.preparing, {})
                    self.assertEqual(self.runtime.material.history, {})
                with socket.socket() as check:
                    self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0, 'listener leak')
        self.assertFalse(Path(home).exists())

    async def prepare(self, client, **updates):
        result = await client.call_tool('material_prepare', {**MANIFEST, **updates}, raise_on_error=False)
        self.assertFalse(result.is_error, str(result))
        self.assertTrue(result.data['success'], str(result))
        return result.data['data']['plan_id']

    def scope(self, plan, **updates):
        return {'task_id': MANIFEST['task_id'], 'plan_id': plan, **updates}


class MaterialTests(MaterialHarness):
    async def test_MR008_stop_at_final_registry_await_prevents_write(self):
        from unittest.mock import patch
        from candidate_runtime import _CURRENT
        from transport.plugin_hub import PluginHub
        async with self.running():
            async with Client(self.url) as client:
                plan = await self.prepare(client)
                entered, release = asyncio.Event(), asyncio.Event()
                registry = PluginHub._registry
                original = registry.get_session
                async def paused_lookup(*args, **kwargs):
                    result = await original(*args, **kwargs)
                    invocation = _CURRENT.get()
                    if invocation is not None and invocation.name == 'material_execute':
                        entered.set()
                        await release.wait()
                    return result
                with patch.object(registry, 'get_session', side_effect=paused_lookup):
                    executing = asyncio.create_task(client.call_tool('material_execute',
                        self.scope(plan, action='copy', arguments={}), raise_on_error=False))
                    try:
                        await asyncio.wait_for(entered.wait(), 2)
                        stopped = await client.call_tool('material_stop', self.scope(plan))
                        self.assertTrue(stopped.data['success'])
                        release.set()
                        result = await asyncio.wait_for(executing, 3)
                        self.assertTrue(result.is_error, 'revoked write crossed final routing await')
                        self.assertFalse(any(e['params']['kind'] == 'execute' for e in self.events))
                        self.assertEqual(len(await self.wait_for_stop(plan)), 1)
                    finally:
                        release.set()
                        if not executing.done():
                            executing.cancel()
                        await asyncio.gather(executing, return_exceptions=True)

    async def test_MR007_failed_replacement_revokes_old_keeps_read_history_private(self):
        async with self.running():
            async with Client(self.url) as a, Client(self.url) as b:
                old = await self.prepare(a)
                sid = self.events[-1]['params']['client_id']
                read_plan = (await a.call_tool('agent_prepare', fixtures.PREPARE)).data['data']['plan_id']
                for name, extra in [('material_status', {}), ('material_stop', {}),
                        ('material_execute', {'action': 'copy', 'arguments': {}})]:
                    before = len(self.events)
                    denied = await b.call_tool(name, self.scope(old, **extra), raise_on_error=False)
                    self.assertTrue(denied.is_error)
                    self.assertEqual(len(self.events), before)
                failure = {'success': False, 'error': 'capability_disabled', 'data': {'status': 'denied'}}
                self.response_hook = lambda m, r: failure if m['params']['kind'] == 'prepare' else r
                rejected = await a.call_tool('material_prepare', MANIFEST, raise_on_error=False)
                self.assertTrue(rejected.is_error)
                self.assertEqual(rejected.structured_content, failure)
                self.assertNotIn(sid, self.runtime.material.plans)
                self.assertEqual(self.runtime.plans[sid].plan_id, read_plan)
                stops = await self.wait_for_stop(old)
                self.assertEqual(len(stops), 1)
                self.assertEqual(stops[0]['name'], ROUTE)
                self.response_hook = None
                new = await self.prepare(a)
                await a.call_tool('material_stop', self.scope(old))
                self.assertEqual(self.runtime.material.plans[sid].plan_id, new)
                await a.call_tool('material_status', self.scope(old))
                self.assertEqual(self.events[-1]['params']['plan_id'], old)
                self.assertTrue((await a.call_tool('material_execute', self.scope(new, action='copy', arguments={}))).data['success'])

    async def test_MR006_disconnect_revokes_read_and_material_without_reconnect_grants(self):
        from transport.plugin_hub import PluginHub
        async with self.running():
            async with Client(self.url) as client:
                plan = await self.prepare(client)
                sid = self.events[-1]['params']['client_id']
                await client.call_tool('agent_prepare', fixtures.PREPARE)
                await self.peer.close(code=1001)
                async with asyncio.timeout(2):
                    while await PluginHub._registry.list_sessions():
                        await asyncio.sleep(.01)
                self.assertNotIn(sid, self.runtime.plans)
                self.assertNotIn(sid, self.runtime.material.plans)
                self.assertNotIn(sid, self.runtime.material.history)
                self.assertEqual(self.runtime.material.preparing, {})
                denied = await client.call_tool('material_status', self.scope(plan), raise_on_error=False)
                self.assertTrue(denied.is_error)
                self.assertFalse(any(e['params']['kind'] == 'stop' for e in self.events), 'never reroute stop to new peer')

    async def test_MR005_late_prepare_after_delete_never_restores_and_exact_stop(self):
        async with self.running():
            async with httpx.AsyncClient(trust_env=False, timeout=5,
                    headers={'Accept': 'application/json, text/event-stream'}) as http:
                sid = await self.initialize(http)
                self.hold_kind = 'prepare'
                self.release.clear()
                preparing = asyncio.create_task(self.post(http, 'tools/call',
                    {'name': 'material_prepare', 'arguments': MANIFEST}, 2))
                try:
                    await asyncio.wait_for(self.entered.wait(), 2)
                    self.assertEqual((await http.delete(self.url)).status_code, 200)
                    self.release.set()
                    try:
                        stops = await self.wait_for_stop('fixture-plan-1')
                    except TimeoutError:
                        self.fail('late material prepare was not precisely stopped after DELETE')
                    self.assertEqual(len(stops), 1)
                    self.assertEqual(stops[0]['name'], ROUTE)
                    self.assertEqual(stops[0]['params']['client_id'], sid)
                    self.assertNotIn(sid, self.runtime.material.plans)
                    self.assertNotIn(sid, self.runtime.material.preparing)
                finally:
                    self.release.set()
                    preparing.cancel()
                    await asyncio.gather(preparing, return_exceptions=True)

    async def test_MR004_sdk_delete_revokes_both_routes_only_own_client(self):
        async with self.running():
            async with Client(self.url) as b:
                bp = await self.prepare(b)
                b_id = self.events[-1]['params']['client_id']
                async with Client(self.url) as a:
                    ap = await self.prepare(a)
                    a_id = self.events[-1]['params']['client_id']
                    rp = (await a.call_tool('agent_prepare', fixtures.PREPARE)).data['data']['plan_id']
                    async with httpx.AsyncClient(trust_env=False, timeout=5) as http:
                        response = await http.delete(self.url, headers={'mcp-session-id': a_id,
                            'mcp-protocol-version': a.initialize_result.protocolVersion})
                        self.assertEqual(response.status_code, 200)
                    self.assertNotIn(a_id, self.runtime.plans)
                    self.assertNotIn(a_id, self.runtime.material.plans)
                    self.assertNotIn(a_id, self.runtime.material.history)
                    for plan, route in [(ap, ROUTE), (rp, 'vrchat_agent_dispatch')]:
                        stops = await self.wait_for_stop(plan)
                        self.assertEqual(len(stops), 1)
                        self.assertEqual(stops[0]['name'], route)
                        self.assertEqual(stops[0]['params']['client_id'], a_id)
                self.assertEqual(self.runtime.material.plans[b_id].plan_id, bp)
                self.assertFalse(any(e['params']['kind'] == 'stop' and e['params']['client_id'] == b_id for e in self.events))
                self.assertTrue((await b.call_tool('material_execute', self.scope(bp, action='copy', arguments={}))).data['success'])
            self.assertEqual(len(await self.wait_for_stop(bp)), 1)

    async def test_MR003_native_failure_preserves_data_marks_error_revokes_once(self):
        async with self.running():
            async with Client(self.url) as client:
                plan = await self.prepare(client)
                failure = {'success': False, 'error': 'native_write_failed', 'data': {
                    **REPORT, 'status': 'failed_preserved', 'grant_active': False}}
                self.response_hook = lambda message, result: failure if message['params']['kind'] == 'execute' else result
                result = await client.call_tool('material_execute', self.scope(plan, action='edit',
                    arguments={'property': '_Metallic', 'value': .6}), raise_on_error=False)
                self.assertEqual(result.structured_content, failure, 'keep exact native data, not the outer success wrapper')
                self.assertEqual(json.loads(result.content[0].text), failure)
                self.assertTrue(result.is_error, 'native failure must not be packaged as MCP success')
                stops = await self.wait_for_stop(plan)
                self.assertEqual(len(stops), 1)
                self.assertEqual(stops[0]['name'], ROUTE)
                self.assertEqual(sum(e['params']['kind'] == 'execute' for e in self.events), 1)
                before = len(self.events)
                denied = await client.call_tool('material_execute', self.scope(plan, action='copy', arguments={}),
                    raise_on_error=False)
                self.assertTrue(denied.is_error)
                self.assertEqual(len(self.events), before)
                self.assertEqual((await client.call_tool('material_status', self.scope(plan))).data['data']['transactions'],
                    [REPORT['transaction']])

    async def test_MR002_strict_manifest_and_action_arguments_before_ws(self):
        async with self.running():
            async with Client(self.url) as client:
                for update in [{'client_id': 'fake'}, {'approve': True}, {'ttl_seconds': True},
                    {'ttl_seconds': '60'}, {'ttl_seconds': 901}, {'source': 'Assets/../Original.mat'},
                    {'source': 'Assets/a*/Original.mat'}, {'candidate': 'Assets/Original.mat'},
                    {'candidate': 'Assets/Bad./Candidate.mat'}, {'operations': ['copy', 'copy']},
                    {'operations': ['exec']}, {'references': []},
                    {'references': [{'renderer': 'find', 'slot': 0}]},
                    {'references': [{**MANIFEST['references'][0], 'slot': True}]},
                    {'references': [{**MANIFEST['references'][0], 'slot': 256}]},
                    {'references': [MANIFEST['references'][0], MANIFEST['references'][0]]}]:
                    with self.subTest(update=update):
                        before = len(self.events)
                        result = await client.call_tool('material_prepare', {**MANIFEST, **update}, raise_on_error=False)
                        self.assertTrue(result.is_error, str(result))
                        self.assertEqual(len(self.events), before, 'invalid input reached Unity')
                plan = await self.prepare(client)
                for action, arguments in [('exec', {}), ('copy', {'path': 'Assets/Other.mat'}),
                    ('edit', {'property': '_X', 'value': {'method': 'run'}}),
                    ('edit', {'property': '_X', 'value': '{"value":1}'}),
                    ('edit', {'property': '_X', 'value': [1, True]}),
                    ('edit', {'property': '_X', 'value': [1]}),
                    ('edit', {'property': '_X', 'value': 'Packages/a.png'}),
                    ('edit', {'property': '_X', 'value': 'Assets/../a.png'}),
                    ('reference', {**MANIFEST['references'][0], 'material': 'Assets/Original.mat'}),
                    ('reference', {**MANIFEST['references'][0], 'slot': 1})]:
                    with self.subTest(action=action, arguments=arguments):
                        before = len(self.events)
                        result = await client.call_tool('material_execute', self.scope(plan,
                            action=action, arguments=arguments), raise_on_error=False)
                        self.assertTrue(result.is_error)
                        self.assertEqual(len(self.events), before, 'invalid mutation reached Unity')
                await client.call_tool('material_stop', self.scope(plan))

    async def test_MR001_real_http_ws_narrow_wire_and_readback(self):
        async with self.running():
            async with Client(self.url) as client:
                tools = await client.list_tools()
                self.assertEqual({t.name for t in tools}, TOOLS | {
                    'agent_status', 'agent_catalog', 'agent_prepare', 'agent_stop', 'manage_animation', 'manage_material', 'read_console'})
                plan = await self.prepare(client)
                wire = self.events[-1]
                self.assertEqual(wire['name'], ROUTE)
                self.assertEqual(set(wire['params']), {'protocol', 'kind', 'project_id', 'client_id',
                    'connection_id', 'task_id', 'plan_id', 'body'})
                self.assertEqual(wire['params']['body'], {k: v for k, v in MANIFEST.items() if k != 'task_id'})
                self.assertEqual(wire['params']['connection_id'], self.connection_id)
                self.assertEqual(wire['params']['plan_id'], '')
                self.assertTrue(wire['params']['client_id'])
                for action, arguments in [('copy', {}), ('edit', {'property': '_Metallic', 'value': .6}),
                        ('reference', MANIFEST['references'][0])]:
                    result = await client.call_tool('material_execute', self.scope(plan,
                        action=action, arguments=arguments))
                    self.assertEqual(result.data, {'success': True, 'data': REPORT})
                    self.assertEqual(self.events[-1]['params']['body'], {'action': action, 'arguments': arguments})
                stopped = await client.call_tool('material_stop', self.scope(plan))
                self.assertTrue(stopped.data['success'])
                status = await client.call_tool('material_status', self.scope(plan))
                self.assertEqual(status.data['data']['transactions'], [REPORT['transaction']])
                before = len(self.events)
                again = await client.call_tool('material_execute', self.scope(plan, action='copy', arguments={}),
                    raise_on_error=False)
                self.assertTrue(again.is_error)
                self.assertEqual(len(self.events), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
