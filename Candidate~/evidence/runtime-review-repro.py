"""Independent finite runtime probes. No implementation or existing test edits.
Run `python -B evidence/runtime-review-repro.py sdk|http` in an empty env.
Native Unity remains a labeled fixture; native wire shape comes from fixed
TransportCommandDispatcher.cs:415 and WebSocketTransportClient.cs:657-664.
Failing assertions are review findings, NOT passing acceptance tests.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODE = sys.argv.pop(1)
os.environ.update(DISABLE_TELEMETRY='true', FASTMCP_CHECK_FOR_UPDATES='off')
OBSERVATIONS = []


def observe(case, **values):
    OBSERVATIONS.append({'case': case, **values})
    print(json.dumps(OBSERVATIONS[-1], ensure_ascii=False), flush=True)


if MODE == 'sdk':
    sys.path.insert(0, str(ROOT / 'tests'))
    import test_runtime as fixture
    from candidate_runtime import _CURRENT
    from transport.plugin_hub import PluginHub
    from transport.models import CommandResultMessage

    class ReviewSDK(unittest.IsolatedAsyncioTestCase):
        asyncSetUp = fixture.RuntimeTests.asyncSetUp
        asyncTearDown = fixture.RuntimeTests.asyncTearDown

        def native_wire_peer(self, kind=None, success=True):
            original = self.peer.send_json
            async def respond(payload):
                if kind and payload['params']['kind'] != kind:
                    return await original(payload)
                self.peer.events.append(payload)
                inner = {'success': success, 'data': {'status': 'pending', 'plan_id': 'native-wire-plan'}}
                if not success:
                    inner['error'] = 'fixture_native_denial'
                result = {'status': 'success', 'result': inner}
                # Real native result parser and pending resolution, not a replacement handler.
                await PluginHub._handle_command_result(object.__new__(PluginHub),
                    CommandResultMessage(id=payload['id'], result=result))
            self.peer.send_json = respond

        async def test_RR001_native_wire_prepare_is_accepted(self):
            self.native_wire_peer()
            result = await self.client.call_tool('agent_prepare', fixture.PREPARE, raise_on_error=False)
            observe('RR001', is_error=result.is_error, data=result.data,
                    content=[getattr(c, 'text', '') for c in result.content])
            self.assertFalse(result.is_error, 'native status/result-wrapped pending must be accepted')

        async def test_RR002_successful_native_wire_read_keeps_current_plan(self):
            await self.client.call_tool('agent_prepare', fixture.PREPARE)
            self.native_wire_peer(kind='execute')
            first = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            second = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            observe('RR002', first_data=first.data, second_is_error=second.is_error,
                    second_data=second.data, execute_count=sum(e['params']['kind']=='execute' for e in self.peer.events))
            self.assertTrue(first.data['success'])
            self.assertFalse(second.is_error, 'successful native read must not revoke the plan')

        async def test_RR003_cancel_during_native_route_await_revokes_plan(self):
            await self.client.call_tool('agent_prepare', fixture.PREPARE)
            self.peer.approved = True
            entered, ended = asyncio.Event(), asyncio.Event()
            async def pending_route(*args, **kwargs):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    ended.set()
            with patch.object(PluginHub._registry, 'get_session_id_by_hash', pending_route):
                request = asyncio.create_task(self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False))
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                finally:
                    request.cancel()
                    await asyncio.gather(request, return_exceptions=True)
                await asyncio.wait_for(ended.wait(), 3)
            again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            observe('RR003', after_cancel_is_error=again.is_error, after_cancel_data=again.data)
            self.assertTrue(again.is_error or (again.data or {}).get('success') is False,
                            'SDK cancellation before send must require a fresh plan')

        async def test_RR004_native_route_failure_revokes_plan(self):
            await self.client.call_tool('agent_prepare', fixture.PREPARE)
            self.peer.approved = True
            with patch.object(PluginHub._registry, 'get_session_id_by_hash', side_effect=RuntimeError('fixture routing failure')):
                failed = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            observe('RR004', failure_data=failed.data, after_failure_is_error=again.is_error, after_failure_data=again.data)
            self.assertFalse(failed.data['success'])
            self.assertTrue(again.is_error or (again.data or {}).get('success') is False,
                            'native pre-egress failure must revoke current mapping')

        async def test_RR005_stop_at_final_envelope_await_blocks_send(self):
            await self.client.call_tool('agent_prepare', fixture.PREPARE)
            self.peer.approved = True
            entered, release = asyncio.Event(), asyncio.Event()
            original = PluginHub._registry.get_session
            async def paused(session):
                if _CURRENT.get().name == 'manage_animation':
                    entered.set()
                    await release.wait()
                return await original(session)
            with patch.object(PluginHub._registry, 'get_session', paused):
                request = asyncio.create_task(self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False))
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                    stopped = await self.client.call_tool('agent_stop', {'task_id': fixture.PREPARE['task_id']})
                    self.assertTrue(stopped.data['success'])
                finally:
                    release.set()
                result = await request
            executes = [e for e in self.peer.events if e['params']['kind']=='execute']
            observe('RR005', data=result.data, execute_count=len(executes))
            self.assertEqual(executes, [])
            self.assertFalse(result.data['success'])

        async def test_RR006_final_await_uses_detached_wire_snapshot(self):
            await self.client.call_tool('agent_prepare', fixture.PREPARE)
            self.peer.approved = True
            entered, release = asyncio.Event(), asyncio.Event()
            original_envelope, original_get = PluginHub.command_envelope, PluginHub._registry.get_session
            inputs = []
            async def capture(session, command, params):
                inputs.append(params)
                return await original_envelope(session, command, params)
            async def paused(session):
                entered.set()
                await release.wait()
                return await original_get(session)
            with patch.object(PluginHub, 'command_envelope', capture), patch.object(PluginHub._registry, 'get_session', paused):
                request = asyncio.create_task(self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False))
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                    inputs[-1]['controllerPath'] = 'Assets/Unapproved.controller'
                finally:
                    release.set()
                result = await request
            sent = self.peer.events[-1]['params']['body']['params']['controllerPath']
            observe('RR006', data=result.data, sent_path=sent)
            self.assertTrue(result.data['success'])
            self.assertEqual(sent, fixture.CONTROLLER)

        async def test_RR007_outer_success_preserves_inner_failure(self):
            await self.client.call_tool('agent_prepare', fixture.PREPARE)
            self.native_wire_peer(kind='execute', success=False)
            first = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            observe('RR007', first_data=first.data, second_is_error=again.is_error)
            self.assertFalse(first.data['success'])
            self.assertEqual(first.data['error'], 'fixture_native_denial')
            self.assertTrue(again.is_error)

        async def test_RR008_replacement_at_final_envelope_await_blocks_old_send(self):
            await self.client.call_tool('agent_prepare', fixture.PREPARE)
            self.peer.approved = True
            entered, release = asyncio.Event(), asyncio.Event()
            original = PluginHub._registry.get_session
            async def paused(session):
                if _CURRENT.get().name == 'manage_animation':
                    entered.set()
                    await release.wait()
                return await original(session)
            with patch.object(PluginHub._registry, 'get_session', paused):
                request = asyncio.create_task(self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False))
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                    await self.client.call_tool('agent_prepare', {**fixture.PREPARE, 'task_id': 'replacement'})
                finally:
                    release.set()
                result = await request
            executes = [e for e in self.peer.events if e['params']['kind']=='execute']
            observe('RR008', data=result.data, execute_count=len(executes))
            self.assertEqual(executes, [])
            self.assertFalse(result.data['success'])

elif MODE == 'http':
    import socket
    import tempfile
    import time
    import httpx
    import websockets

    class ReviewHTTP(unittest.IsolatedAsyncioTestCase):
        async def test_RR009_untrusted_origin_and_host_are_rejected(self):
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1', 0))
                port = reserved.getsockname()[1]
            pid = None
            with tempfile.TemporaryDirectory(prefix='runtime-review-http-') as home, tempfile.TemporaryFile() as output:
                proc = await asyncio.create_subprocess_exec(sys.executable, '-B', str(ROOT/'runtime'),
                    '--project', '0123456789abcdef0123456789abcdef', '--port', str(port),
                    env={'PATH':'/usr/bin:/bin','HOME':home,'LANG':'C.UTF-8','DISABLE_TELEMETRY':'true'},
                    stdout=output, stderr=output)
                pid = proc.pid
                try:
                    async with httpx.AsyncClient(trust_env=False, timeout=.5) as http:
                        url = f'http://127.0.0.1:{port}'
                        deadline = time.monotonic() + 8
                        while True:
                            try:
                                if (await http.get(url+'/does-not-exist')).status_code == 404:
                                    break
                            except httpx.HTTPError:
                                pass
                            if proc.returncode is not None or time.monotonic() >= deadline:
                                output.seek(0)
                                self.fail('CLI readiness failure: '+output.read(5000).decode(errors='replace'))
                            await asyncio.sleep(.05)
                        response = await http.post(url+'/mcp', headers={
                            'Origin':'https://untrusted.invalid', 'Host':'untrusted.invalid',
                            'Accept':'application/json, text/event-stream'}, json={
                            'jsonrpc':'2.0','id':1,'method':'initialize','params':{
                            'protocolVersion':'2025-03-26','capabilities':{},
                            'clientInfo':{'name':'review-fixture','version':'1'}}})
                        accepted = False
                        try:
                            async with websockets.connect(f'ws://127.0.0.1:{port}/hub',
                                    origin='https://untrusted.invalid', proxy=None) as peer:
                                welcome = json.loads(await peer.recv())
                                accepted = welcome.get('type') == 'welcome'
                        except websockets.exceptions.InvalidStatus:
                            pass
                        observe('RR009', http_status=response.status_code,
                                http_session_issued='mcp-session-id' in response.headers,
                                cross_origin_websocket_accepted=accepted)
                        # Close the synthetic HTTP session when one was issued.
                        sid = response.headers.get('mcp-session-id')
                        if sid:
                            await http.delete(url+'/mcp', headers={'mcp-session-id':sid})
                        self.assertFalse(accepted, 'remote page Origin must not reach the unauthenticated native peer socket')
                        self.assertIn(response.status_code, (400,403,421), 'untrusted Host must be rejected')
                finally:
                    if proc.returncode is None:
                        proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), 8)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
                        self.fail('cleanup required forced kill')
                    self.assertFalse(Path(f'/proc/{pid}').exists())
                    with socket.socket() as check:
                        check.settimeout(.2)
                        self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0)
            self.assertFalse(Path(home).exists())
else:
    raise SystemExit('use sdk or http')

if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = runner.run(suite)
    print(json.dumps({'mode':MODE,'tests':result.testsRun,'failures':len(result.failures),
                      'errors':len(result.errors),'observations':OBSERVATIONS},ensure_ascii=False), flush=True)
    raise SystemExit(not result.wasSuccessful())
