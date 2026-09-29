"""Real SDK/HTTP/WS lifecycle. Unity peer only is explicitly a fixture."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'runtime'), str(ROOT / 'native/src')]
PROJECT = 'fixture-project'  # Same explicit synthetic identity as WirePeer.cs.
PREPARE = {'task_id': 'fixture-task', 'operations': [
    {'command': 'manage_material', 'action': 'get_material_info'}],
    'targets': ['Assets/Read.mat'], 'ttl_seconds': 60}
READ = {'action': 'get_material_info', 'material_path': 'Assets/Read.mat'}
WIRE_DLL = None  # Fresh-build verifier supplies this. Never use an old bin/ DLL.
DOTNET = '/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet'


class LifecycleHarness(unittest.IsolatedAsyncioTestCase):
    use_core = False

    @asynccontextmanager
    async def running(self):
        with tempfile.TemporaryDirectory(prefix='candidate-lifecycle-') as home:
            old = os.environ.copy()
            os.environ.clear()
            os.environ.update(PATH='/usr/bin:/bin', HOME=home, TMPDIR=home,
                LANG='C.UTF-8', DISABLE_TELEMETRY='true', UNITY_MCP_DISABLE_TELEMETRY='1',
                UNITY_MCP_SKIP_STARTUP_CONNECT='1', FASTMCP_CHECK_FOR_UPDATES='off')
            from candidate_runtime import create_server, create_app
            from transport.plugin_hub import PluginHub
            server = create_server(PROJECT)
            self.runtime = PluginHub.command_envelope.__self__
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            service = uvicorn.Server(uvicorn.Config(create_app(server), log_level='error',
                access_log=False, lifespan='on', timeout_graceful_shutdown=3))
            serving = asyncio.create_task(service.serve(sockets=[listener]))
            responder = None
            self.events, self.replies = [], []
            self.hold_kind = None
            self.entered, self.release = asyncio.Event(), asyncio.Event()
            self.release.set()
            self.peer_failure = False
            self.peer_silence = False
            self.counter = 0
            core = None
            core_log = tempfile.TemporaryFile()
            try:
                if self.use_core:
                    self.assertTrue(WIRE_DLL and Path(WIRE_DLL).is_file(),
                        'fresh-build verifier must supply the real compiled gate')
                    core = await asyncio.create_subprocess_exec(DOTNET, str(WIRE_DLL),
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=core_log, env={**os.environ, 'DOTNET_CLI_TELEMETRY_OPTOUT': '1'})
                    assert core.stdin is not None and core.stdout is not None
                    mutex = asyncio.Lock()
                    async def exchange(message):
                        assert core is not None and core.stdin is not None and core.stdout is not None
                        async with mutex:
                            core.stdin.write((json.dumps(message) + '\n').encode())
                            await core.stdin.drain()
                            raw = await asyncio.wait_for(core.stdout.readline(), 3)
                            self.assertTrue(raw, 'compiled gate exited without a response')
                            return json.loads(raw)
                    self.exchange = exchange
                async with asyncio.timeout(8):
                    while not service.started:
                        if serving.done():
                            await serving
                            self.fail('server exited before readiness')
                        await asyncio.sleep(.02)
                self.url = f'http://127.0.0.1:{port}/mcp'
                async with websockets.connect(f'ws://127.0.0.1:{port}/hub/plugin', proxy=None) as ws:
                    self.assertEqual(json.loads(await ws.recv())['type'], 'welcome')
                    await ws.send(json.dumps({'type': 'register', 'project_name': 'NOT-UNITY-LifecycleFixture',
                        'project_hash': PROJECT, 'unity_version': 'FIXTURE'}))
                    self.connection_id = json.loads(await ws.recv())['session_id']
                    if core:
                        self.assertTrue((await self.exchange({'fixture_connection': self.connection_id}))['fixture_ready'])
                    async def respond():
                        async for raw in ws:
                            message = json.loads(raw)
                            if message['type'] == 'ping':
                                await ws.send(json.dumps({'type': 'pong', 'session_id': self.connection_id}))
                                continue
                            self.events.append(message)
                            envelope = message['params']
                            kind = envelope['kind']
                            if core:
                                wrapped = await self.exchange({'request': envelope})
                                self.replies.append(wrapped)
                                await ws.send(json.dumps({'type': 'command_result', 'id': message['id'], 'result': wrapped}))
                                continue
                            if kind == self.hold_kind:
                                self.entered.set()
                                await self.release.wait()
                            if kind == 'prepare':
                                self.counter += 1
                                result = {'success': True, 'data': {
                                    'plan_id': f'fixture-plan-{self.counter}', 'status': 'pending'}}
                            elif kind == 'stop':
                                if self.peer_silence:
                                    continue
                                result = {'success': not self.peer_failure, 'data': {'status': 'stopped'}}
                            else:
                                result = {'success': True, 'data': {'fixture_only': True}}
                            self.replies.append(result)
                            await ws.send(json.dumps({'type': 'command_result', 'id': message['id'],
                                'result': {'status': 'success', 'result': result}}))
                    responder = asyncio.create_task(respond())
                    yield
            finally:
                self.release.set()
                if responder:
                    responder.cancel()
                    await asyncio.gather(responder, return_exceptions=True)
                service.should_exit = True
                try:
                    await asyncio.wait_for(serving, 8)
                finally:
                    listener.close()
                    cleanup_errors = []
                    try:
                        if core:
                            assert core.stdin is not None
                            core.stdin.close()
                            try:
                                await asyncio.wait_for(core.wait(), 5)
                            except TimeoutError:
                                core.kill()
                                await core.wait()
                                cleanup_errors.append('compiled gate cleanup required kill')
                            if core.returncode != 0 or Path(f'/proc/{core.pid}').exists():
                                cleanup_errors.append('compiled gate unclean exit')
                    finally:
                        core_log.close()
                        os.environ.clear()
                        os.environ.update(old)
                    self.assertEqual(cleanup_errors, [])
                self.assertEqual(PluginHub._pending, {}, 'native pending command leak')
                self.assertEqual(PluginHub._connections, {}, 'native WebSocket connection leak')
                self.assertEqual(await PluginHub._registry.list_sessions(), {}, 'native registry leak')
                self.assertEqual(self.runtime.sessions, {}, 'runtime SDK session binding leak')
                self.assertEqual(self.runtime.preparing, {}, 'runtime preparing invocation leak')
                with socket.socket() as check:
                    self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0, 'listener leak')
        self.assertFalse(Path(home).exists(), 'temporary home leak')

    async def wait_for_stop(self, plan_id, timeout=3):
        async with asyncio.timeout(timeout):
            while True:
                stops = [e for e in self.events if e['params']['kind'] == 'stop'
                         and e['params']['plan_id'] == plan_id]
                if stops:
                    return stops
                await asyncio.sleep(.02)

class LifecycleTests(LifecycleHarness):
    async def test_LC001_sdk_exit_stops_only_its_exact_plan(self):
        async with self.running():
            async with Client(self.url) as b:
                pb = await b.call_tool('agent_prepare', PREPARE)
                async with Client(self.url) as a:
                    pa = await a.call_tool('agent_prepare', PREPARE)
                    ea = self.events[-1]['params']
                try:
                    stops = await self.wait_for_stop(pa.data['data']['plan_id'])
                except TimeoutError:
                    self.fail('SDK session ended without a Unity stop command')
                stop = stops[0]['params']
                self.assertEqual(len(stops), 1)
                self.assertEqual({k: stop[k] for k in ('client_id', 'connection_id', 'task_id', 'project_id')},
                    {k: ea[k] for k in ('client_id', 'connection_id', 'task_id', 'project_id')})
                self.assertNotIn(ea['client_id'], self.runtime.plans)
                self.assertFalse(any(e['params']['kind'] == 'stop' and
                    e['params']['plan_id'] == pb.data['data']['plan_id'] for e in self.events))
                self.assertTrue((await b.call_tool('manage_material', READ)).data['success'])
            await self.wait_for_stop(pb.data['data']['plan_id'])
            self.assertEqual(self.runtime.plans, {})

    async def test_LC002_delete_revokes_while_native_read_is_in_flight(self):
        async with self.running():
            async with Client(self.url) as a:
                pa = await a.call_tool('agent_prepare', PREPARE)
                client_id = self.events[-1]['params']['client_id']
                self.hold_kind = 'execute'
                self.release.clear()
                reading = asyncio.create_task(a.call_tool('manage_material', READ, raise_on_error=False))
                try:
                    await asyncio.wait_for(self.entered.wait(), 3)
                    async with httpx.AsyncClient(trust_env=False, timeout=4) as http:
                        deleted = await http.delete(self.url, headers={'mcp-session-id': client_id,
                            'mcp-protocol-version': a.initialize_result.protocolVersion})
                    self.assertEqual(deleted.status_code, 200, 'SDK must accept termination first')
                    self.assertNotIn(client_id, self.runtime.plans,
                        'successful SDK DELETE returned while local grant remained active')
                    self.release.set()
                    await self.wait_for_stop(pa.data['data']['plan_id'])
                finally:
                    self.release.set()
                    reading.cancel()
                    await asyncio.gather(reading, return_exceptions=True)

    async def test_LC003_late_prepare_after_delete_is_revoked_not_restored(self):
        async with self.running():
            async with Client(self.url) as a:
                self.hold_kind = 'prepare'
                self.release.clear()
                preparing = asyncio.create_task(a.call_tool('agent_prepare', PREPARE, raise_on_error=False))
                try:
                    await asyncio.wait_for(self.entered.wait(), 3)
                    client_id = self.events[-1]['params']['client_id']
                    async with httpx.AsyncClient(trust_env=False, timeout=4) as http:
                        deleted = await http.delete(self.url, headers={'mcp-session-id': client_id,
                            'mcp-protocol-version': a.initialize_result.protocolVersion})
                    self.assertEqual(deleted.status_code, 200)
                    self.assertNotIn(client_id, self.runtime.plans)
                    self.release.set()
                    try:
                        stops = await self.wait_for_stop('fixture-plan-1')
                    except TimeoutError:
                        self.fail('late Unity prepare was not stopped after SDK session ended')
                    self.assertEqual(stops[0]['params']['client_id'], client_id)
                    self.assertNotIn(client_id, self.runtime.plans)
                    self.assertNotIn(client_id, self.runtime.preparing)
                finally:
                    self.release.set()
                    preparing.cancel()
                    await asyncio.gather(preparing, return_exceptions=True)

    async def test_LC004_rejected_delete_cannot_revoke_a_live_session(self):
        async with self.running():
            async with Client(self.url) as a:
                await a.call_tool('agent_prepare', PREPARE)
                client_id = self.events[-1]['params']['client_id']
                headers = {'mcp-session-id': client_id,
                    'mcp-protocol-version': a.initialize_result.protocolVersion}
                async with httpx.AsyncClient(trust_env=False, timeout=3) as http:
                    for extra, expected in (({'origin': 'https://fixture.invalid'}, 403),
                        ({'host': 'fixture.invalid'}, 403),
                        ({'mcp-protocol-version': 'fixture-invalid'}, 400),
                        ({'mcp-session-id': 'fixture-unknown'}, 404)):
                        response = await http.delete(self.url, headers={**headers, **extra})
                        self.assertEqual(response.status_code, expected)
                        self.assertIn(client_id, self.runtime.plans)
                self.assertFalse(any(e['params']['kind'] == 'stop' for e in self.events))
                self.assertTrue((await a.call_tool('manage_material', READ)).data['success'])

    async def test_LC005_missing_ack_is_bounded_unconfirmed_and_reported(self):
        async with self.running():
            with self.assertLogs('vrchat_agent.lifecycle', level='WARNING') as logs:
                async with Client(self.url) as a:
                    await a.call_tool('agent_prepare', PREPARE)
                    client_id = self.events[-1]['params']['client_id']
                    self.peer_silence = True
            self.assertNotIn(client_id, self.runtime.plans)
            self.assertNotIn(client_id, self.runtime.sessions)
            self.assertEqual(len(self.runtime.lifecycle_results), 1)
            receipt = self.runtime.lifecycle_results[-1]
            self.assertFalse(receipt['unity_confirmed'])
            self.assertEqual(receipt['reason'], 'unity_stop_timeout')
            self.assertTrue(receipt['local_revoked'])
            self.assertEqual(sum(e['params']['kind'] == 'stop' for e in self.events), 1,
                'cleanup must not retry')
            self.assertIn('Unity撤权未确认', '\n'.join(logs.output))

    async def test_LC007_negative_ack_cannot_be_reported_as_confirmed(self):
        async with self.running():
            with self.assertLogs('vrchat_agent.lifecycle', level='WARNING'):
                async with Client(self.url) as a:
                    await a.call_tool('agent_prepare', PREPARE)
                    self.peer_failure = True
            self.assertEqual(self.runtime.plans, {})
            self.assertFalse(self.runtime.lifecycle_results[-1]['unity_confirmed'])
            self.assertEqual(self.runtime.lifecycle_results[-1]['reason'], 'unity_stop_rejected')


class WireLifecycleTests(LifecycleHarness):
    use_core = True

    async def test_LC006_sdk_exit_removes_plan_in_compiled_csharp_gate(self):
        async with self.running():
            async with Client(self.url) as a:
                prepared = await a.call_tool('agent_prepare', PREPARE)
                self.assertTrue(prepared.data['success'])
                plan_id = prepared.data['data']['plan_id']
                self.assertTrue((await self.exchange({'fixture_local_approve': True}))['fixture_approved'])
                self.assertTrue((await a.call_tool('manage_material', READ)).data['success'])
                self.assertEqual(len((await self.exchange({'fixture_local_plans': True}))['fixture_plans']), 1)
            await self.wait_for_stop(plan_id)
            self.assertEqual((await self.exchange({'fixture_local_plans': True}))['fixture_plans'], [])
            async with asyncio.timeout(3):
                while not self.runtime.lifecycle_results:
                    await asyncio.sleep(.02)
            self.assertTrue(self.runtime.lifecycle_results[-1]['unity_confirmed'])
            async with Client(self.url) as new_client:
                before = len(self.events)
                denied = await new_client.call_tool('manage_material', READ, raise_on_error=False)
                self.assertTrue(denied.is_error)
                self.assertEqual(len(self.events), before, 'fresh SDK session must not inherit authorization')


if __name__ == '__main__':
    unittest.main(verbosity=2)
