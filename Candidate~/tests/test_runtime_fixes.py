"""Targeted fix regressions. Native/SDK are real; Unity is a wire fixture."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_runtime as fixture
from transport.plugin_hub import PluginHub
from transport.models import CommandResultMessage


class RuntimeFixTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.RuntimeTests.asyncSetUp
    asyncTearDown = fixture.RuntimeTests.asyncTearDown

    def wire_response(self, inner):
        async def respond(payload):
            self.peer.events.append(payload)
            await PluginHub._handle_command_result(object.__new__(PluginHub),
                CommandResultMessage(id=payload['id'], result={'status': 'success', 'result': inner}))
        self.peer.send_json = respond

    async def test_RF001_control_status_preserves_native_inner_failure(self):
        self.wire_response({'success': False, 'error': 'fixture_denied', 'data': {'fixture_only': True}})
        result = await self.client.call_tool('agent_status', {})
        self.assertEqual(result.data.get('success'), False)
        self.assertEqual(result.data.get('error'), 'fixture_denied')

    async def test_RF002_control_stop_preserves_native_inner_failure(self):
        await self.client.call_tool('agent_prepare', fixture.PREPARE)
        self.wire_response({'success': False, 'error': 'fixture_denied'})
        result = await self.client.call_tool('agent_stop', {'task_id': fixture.PREPARE['task_id']})
        self.assertEqual(result.data.get('success'), False)
        self.assertEqual(result.data.get('error'), 'fixture_denied')
        again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
        self.assertTrue(again.is_error)

    async def test_RF003_prepare_inner_failure_cannot_become_pending(self):
        self.wire_response({'success': False, 'data': {'status': 'pending', 'plan_id': 'fixture-invalid'}})
        result = await self.client.call_tool('agent_prepare', fixture.PREPARE, raise_on_error=False)
        self.assertTrue(result.is_error)
        again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
        self.assertTrue(again.is_error)
        self.assertEqual(len(self.peer.events), 1)

    async def test_RF004_native_route_unavailable_return_revokes_plan(self):
        from transport.plugin_hub import NoUnitySessionError
        await self.client.call_tool('agent_prepare', fixture.PREPARE)
        with patch.object(PluginHub, 'instance_resolver', side_effect=NoUnitySessionError('fixture unavailable')):
            result = await self.client.call_tool('manage_animation', fixture.READ)
        self.assertFalse(result.data['success'])
        before = len(self.peer.events)
        again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
        self.assertTrue(again.is_error)
        self.assertEqual(before, len(self.peer.events))

    async def test_RF005_exception_before_native_handler_revokes_plan(self):
        from fastmcp import Context
        await self.client.call_tool('agent_prepare', fixture.PREPARE)
        with patch.object(Context, 'set_state', side_effect=RuntimeError('fixture state failure')):
            result = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
        self.assertTrue(result.is_error)
        before = len(self.peer.events)
        again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
        self.assertTrue(again.is_error)
        self.assertEqual(before, len(self.peer.events))

    async def cancel_at_native_route(self, replace=False):
        # Deliberately cancel the server-bound coroutine, NOT the SDK client task.
        # RR003's unconfirmed client cancellation propagation remains out of scope.
        from dataclasses import replace as copy_plan
        from types import SimpleNamespace
        from fastmcp.tools.base import ToolResult
        from candidate_runtime import _CURRENT
        from services.tools.manage_animation import manage_animation
        await self.client.call_tool('agent_prepare', fixture.PREPARE)
        runtime = PluginHub.command_envelope.__self__
        client_id, old_plan = next(iter(runtime.plans.items()))
        state = {}
        async def set_state(key, value):
            state[key] = value
        async def get_state(key):
            return state.get(key)
        # Reuse the real SDK session created by the prepare above; the context
        # shim only isolates coroutine cancellation, not session lifecycle.
        ctx = SimpleNamespace(session_id=client_id, session=runtime.sessions[client_id],
                              set_state=set_state, get_state=get_state)
        context = SimpleNamespace(message=SimpleNamespace(name='manage_animation', arguments=fixture.READ),
                                  fastmcp_context=ctx)
        entered = asyncio.Event()
        async def paused(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        async def call_next(context):
            result = await manage_animation(ctx, **fixture.READ)
            return ToolResult(structured_content=result)
        before = len(self.peer.events)
        replacement = None
        with patch.object(PluginHub, 'instance_resolver', paused):
            request = asyncio.create_task(runtime.on_call_tool(context, call_next))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                if replace:
                    replacement = copy_plan(old_plan)
                    self.assertEqual(replacement, old_plan)
                    self.assertIsNot(replacement, old_plan)
                    runtime.plans[client_id] = replacement
            finally:
                request.cancel()
                settled = await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 3)
        self.assertIsInstance(settled[0], asyncio.CancelledError)
        self.assertIsNone(_CURRENT.get())
        # New behavior sends precise revocation even when dispatch was not yet
        # reached. Preserve no-read/no-replay guarantee; don't forbid the stop.
        added = self.peer.events[before:]
        if replace:
            self.assertEqual(added, [])
        else:
            self.assertEqual(len(added), 1)
            self.assertEqual(added[0]['params']['kind'], 'stop')
            self.assertEqual(added[0]['params']['plan_id'], old_plan.plan_id)
            self.assertEqual(added[0]['params']['client_id'], client_id)
        if replace:
            self.assertIs(runtime.plans.get(client_id), replacement)
        else:
            self.assertNotIn(client_id, runtime.plans)
            again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
            self.assertTrue(again.is_error)

    async def test_RF006_server_boundary_cancel_during_native_route_revokes_plan(self):
        await self.cancel_at_native_route()

    async def test_RF007_old_cancel_does_not_remove_equal_distinct_replacement_plan(self):
        await self.cancel_at_native_route(replace=True)

    async def test_RF008_old_routing_failure_does_not_remove_new_sdk_plan(self):
        await self.client.call_tool('agent_prepare', fixture.PREPARE)
        entered, release = asyncio.Event(), asyncio.Event()
        async def paused(*args, **kwargs):
            entered.set()
            await release.wait()
            raise RuntimeError('fixture old routing failure')
        with patch.object(PluginHub, 'instance_resolver', paused):
            request = asyncio.create_task(self.client.call_tool('manage_animation', fixture.READ))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                prepared = await self.client.call_tool('agent_prepare', {**fixture.PREPARE, 'task_id': 'replacement'})
            finally:
                release.set()
            result = await asyncio.wait_for(request, 3)
        self.assertFalse(result.data['success'])
        self.peer.approved = True
        again = await self.client.call_tool('manage_animation', fixture.READ)
        self.assertTrue(again.data['success'])
        self.assertEqual(self.peer.events[-1]['params']['plan_id'], prepared.data['data']['plan_id'])


    async def test_RF012_asgi_missing_duplicate_host_origin_and_forwarded_headers(self):
        # Characterization of fail-closed raw ASGI header handling; real HTTP/WS
        # acceptance/rejection is covered separately by RF009/RF011.
        from candidate_runtime import LocalRequestBoundary
        reached = []
        async def inner(scope, receive, send):
            reached.append(scope['type'])
        async def receive():
            return {'type': 'http.disconnect'}
        boundary = LocalRequestBoundary(inner)
        port = 23456
        valid = (b'host', b'127.0.0.1:23456')
        cases = [([], False), ([valid], True), ([valid, valid], False),
                 ([valid, (b'origin', b'')], False),
                 ([valid, (b'Origin', b'null'), (b'origin', b'http://127.0.0.1:23456')], False),
                 ([(b'host', b'evil.invalid'), (b'x-forwarded-host', valid[1])], False),
                 ([valid, (b'x-forwarded-host', b'evil.invalid')], True)]
        for kind in ('http', 'websocket'):
            for headers, allowed in cases:
                with self.subTest(kind=kind, headers=headers):
                    sent = []
                    async def send(message):
                        sent.append(message)
                    reached.clear()
                    await boundary({'type': kind, 'headers': headers, 'scheme': 'http',
                                    'server': ('127.0.0.1', port)}, receive, send)
                    self.assertEqual(bool(reached), allowed)
                    if not allowed:
                        if kind == 'http':
                            self.assertEqual(sent[0]['status'], 403)
                        else:
                            self.assertEqual(sent, [{'type': 'websocket.close', 'code': 1008}])


if __name__ == '__main__':
    unittest.main(verbosity=2)
