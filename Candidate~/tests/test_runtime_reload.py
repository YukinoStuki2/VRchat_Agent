"""Real SDK/native dispatch; Unity approval/peer and host route are fixtures.
No real Editor reload, authenticated owner reattach or production grant transfer.
"""
import asyncio
import unittest
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'dependencies/mcp-1.29.1')]
import test_runtime as fixtures


class ReloadPeer(fixtures.UnityPeerFixture):
    async def send_json(self, payload):
        if payload['params']['kind'] != 'stop':
            return await super().send_json(payload)
        self.events.append(payload)
        if self.hook:
            await self.hook(payload)
        from transport.models import CommandResultMessage
        await fixtures.PluginHub._handle_command_result(object.__new__(fixtures.PluginHub),
            CommandResultMessage(id=payload['id'], result={'status': 'success',
                'result': {'success': True, 'data': {'status': 'stopped'}}}))


class ReloadRuntimeTests(unittest.IsolatedAsyncioTestCase):
    server: Any
    client: Any
    peer: Any

    async def asyncSetUp(self):
        await fixtures.RuntimeTests.asyncSetUp(cast(Any, self))
        self.peer = ReloadPeer()
        fixtures.PluginHub._connections[fixtures.CONNECTION] = self.peer
    async def asyncTearDown(self):
        runtime = self.server._candidate_runtime
        self.peer.hook = None
        for plan in list(runtime.plans.values()):
            await self.client.call_tool('agent_stop', {'task_id': plan.task_id}, raise_on_error=False)
        for plan in list(runtime.material.plans.values()):
            await self.client.call_tool('material_stop', {'task_id': plan.task_id, 'plan_id': plan.plan_id}, raise_on_error=False)
        await fixtures.RuntimeTests.asyncTearDown(cast(Any, self))

    async def test_RL001_read_invocation_stays_inflight_until_readback_finishes(self):
        runtime = self.server._candidate_runtime
        self.assertTrue(hasattr(runtime, 'inflight'), 'full invocation quiescence tracking is missing')
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        self.peer.approved = True
        entered, release = asyncio.Event(), asyncio.Event()
        async def hold(message):
            if message['params']['kind'] == 'execute':
                entered.set()
                await release.wait()
        self.peer.hook = hold
        work = asyncio.create_task(self.client.call_tool('manage_animation', fixtures.READ))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            self.assertEqual([i.name for i in runtime.inflight.values()], ['manage_animation'])
            self.assertTrue(all(i.active for i in runtime.inflight.values()))
        finally:
            release.set()
            await asyncio.wait_for(work, 3)
        self.assertEqual(runtime.inflight, {})

    async def test_RL002_material_invocation_tracks_through_readback(self):
        runtime = self.server._candidate_runtime
        manifest = {'task_id': 'material-task', 'source': 'Assets/Original.mat',
                    'candidate': 'Assets/Candidate.mat', 'operations': ['copy'],
                    'references': [], 'ttl_seconds': 60}
        pending = await self.client.call_tool('material_prepare', manifest)
        self.peer.approved = True
        seen = []
        async def observe(message):
            if message['params']['kind'] == 'execute':
                seen.extend(i.name for i in runtime.inflight.values())
        self.peer.hook = observe
        await self.client.call_tool('material_execute', {'task_id': 'material-task',
            'plan_id': pending.data['data']['plan_id'], 'action': 'copy', 'arguments': {}})
        self.assertEqual(seen, ['material_execute'])
        self.assertEqual(runtime.inflight, {})

    async def test_RL003_local_freeze_denies_dispatch_without_consuming_original_plans(self):
        runtime = self.server._candidate_runtime
        self.assertTrue(callable(getattr(runtime, 'freeze_for_reload', None)), 'bounded reload barrier is missing')
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        self.peer.approved = True
        original = dict(runtime.plans)
        ticket = await runtime.freeze_for_reload(window=30)
        before = len(self.peer.events)
        blocked = await self.client.call_tool('manage_animation', fixtures.READ, raise_on_error=False)
        self.assertTrue(blocked.is_error)
        blocked = await self.client.call_tool('agent_prepare', fixtures.PREPARE, raise_on_error=False)
        self.assertTrue(blocked.is_error)
        status = await self.client.call_tool('agent_status', {})
        self.assertEqual(status.data['data']['status'], 'planned_reload_frozen')
        self.assertFalse(status.data['data']['ready'])
        self.assertEqual(len(self.peer.events), before)
        self.assertEqual(runtime.plans, original)
        self.assertTrue(await runtime.release_reload_barrier(ticket))
        self.assertTrue((await self.client.call_tool('manage_animation', fixtures.READ)).data['success'])
        self.assertEqual(runtime.plans, original)
        self.assertFalse(await runtime.release_reload_barrier(ticket))

    async def test_RL004_disconnect_immediately_discards_barrier_and_never_restores(self):
        runtime = self.server._candidate_runtime
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        ticket = await runtime.freeze_for_reload(window=30)
        runtime.connection_closed(fixtures.CONNECTION)
        self.assertIsNone(runtime._reload_barrier, 'disconnect retained the handoff ticket')
        self.assertEqual(runtime.plans, {})
        self.assertFalse(await runtime.release_reload_barrier(ticket))

    async def test_RL005_sdk_close_immediately_discards_barrier(self):
        runtime = self.server._candidate_runtime
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        ticket = await runtime.freeze_for_reload(window=30)
        client, session = next(iter(runtime.sessions.items()))
        await runtime.close_session(client, session)
        self.assertIsNone(runtime._reload_barrier, 'closed SDK session retained the handoff ticket')
        self.assertEqual(runtime.plans, {})
        self.assertFalse(await runtime.release_reload_barrier(ticket))

    async def test_RL006_pending_lifecycle_stop_prevents_freeze(self):
        from fastmcp.exceptions import ToolError
        runtime = self.server._candidate_runtime
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        original_client, original_session = next(iter(runtime.sessions.items()))
        checked = []
        async with fixtures.Client(self.server) as other:
            await other.call_tool('agent_prepare', {**fixtures.PREPARE, 'task_id': 'other-task'})
            async def observe(message):
                if message['params']['kind'] == 'stop':
                    self.assertFalse(runtime.inflight)
                    self.assertTrue(fixtures.PluginHub._pending)
                    with self.assertRaisesRegex(ToolError, 'reload_not_quiescent'):
                        await runtime.freeze_for_reload(window=30)
                    checked.append(True)
            self.peer.hook = observe
            try:
                await runtime.close_session(original_client, original_session)
                self.assertIsNone(runtime._reload_barrier, 'outstanding native stop admitted a freeze')
                self.assertEqual(checked, [True], 'native send swallowed the assertion')
            finally:
                self.peer.hook = None
                runtime.cancel_reload_barrier()
                await other.call_tool('agent_stop', {'task_id': 'other-task'}, raise_on_error=False)

    async def test_RL007_exact_stop_cancels_barrier_but_wrong_task_does_not(self):
        runtime = self.server._candidate_runtime
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        ticket = await runtime.freeze_for_reload(window=30)
        wrong = await self.client.call_tool('agent_stop', {'task_id': 'wrong-task'}, raise_on_error=False)
        self.assertTrue(wrong.is_error)
        self.assertTrue(runtime.reload_is_frozen())
        stopped = await self.client.call_tool('agent_stop', {'task_id': fixtures.PREPARE['task_id']})
        self.assertTrue(stopped.data['success'])
        self.assertIsNone(runtime._reload_barrier, 'explicit stop retained the barrier')
        self.assertFalse(await runtime.release_reload_barrier(ticket))

    async def test_RL008_material_stop_cancels_barrier_before_native_send(self):
        runtime = self.server._candidate_runtime
        pending = await self.client.call_tool('material_prepare', {
            'task_id': 'material-task', 'source': 'Assets/Original.mat',
            'candidate': 'Assets/Candidate.mat', 'operations': ['copy'],
            'references': [], 'ttl_seconds': 60})
        ticket = await runtime.freeze_for_reload(window=30)
        observed = []
        async def observe(message):
            if message['params']['kind'] == 'stop':
                observed.append(runtime._reload_barrier is None)
        self.peer.hook = observe
        await self.client.call_tool('material_stop', {'task_id': 'material-task',
            'plan_id': pending.data['data']['plan_id']})
        self.assertEqual(observed, [True])
        self.assertFalse(await runtime.release_reload_barrier(ticket))

    async def test_RL009_window_expiry_and_retries_never_renew_authority(self):
        from unittest.mock import patch
        from fastmcp.exceptions import ToolError
        runtime = self.server._candidate_runtime
        await self.client.call_tool('agent_prepare', {**fixtures.PREPARE, 'ttl_seconds': 5})
        original = next(iter(runtime.plans.values()))
        for value in (True, 0, -1, 61, float('nan'), float('inf'), '30'):
            with self.assertRaisesRegex(ToolError, 'invalid_reload_window'):
                await runtime.freeze_for_reload(window=value)
        ticket = await runtime.freeze_for_reload(window=30)
        self.assertEqual(runtime._reload_barrier['deadline'], original.expires_at)
        with self.assertRaisesRegex(ToolError, 'reload_not_quiescent'):
            await runtime.freeze_for_reload(window=30)
        with patch('candidate_runtime.time.monotonic', return_value=original.expires_at):
            self.assertFalse(runtime.reload_is_frozen())
        self.assertFalse(await runtime.release_reload_barrier(ticket))
        self.assertEqual(runtime.plans, {})

    async def test_RL010_identity_changes_and_replacements_cannot_restore_saved_plans(self):
        from dataclasses import replace
        runtime = self.server._candidate_runtime
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        client, original = next(iter(runtime.plans.items()))
        identity = runtime.session_identities[client]
        ticket = await runtime.freeze_for_reload(window=30)
        runtime.session_identities[client] = 'changed-identity'
        self.assertFalse(await runtime.release_reload_barrier(ticket))
        self.assertEqual(runtime.plans, {})
        runtime.session_identities[client] = identity
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        ticket = await runtime.freeze_for_reload(window=30)
        newer = replace(runtime.plans[client], plan_id='newer-plan')
        runtime.plans[client] = newer  # Deliberate local concurrency/fault injection.
        self.assertFalse(await runtime.release_reload_barrier(ticket))
        self.assertIs(runtime.plans[client], newer)
        self.assertIsNot(newer, original)

    async def test_RL011_material_is_frozen_and_ticket_is_local_only(self):
        runtime = self.server._candidate_runtime
        manifest = {'task_id': 'material-task', 'source': 'Assets/Original.mat',
                    'candidate': 'Assets/Candidate.mat', 'operations': ['copy'],
                    'references': [], 'ttl_seconds': 60}
        pending = await self.client.call_tool('material_prepare', manifest)
        self.peer.approved = True
        ticket = await runtime.freeze_for_reload(window=30)
        before = len(self.peer.events)
        for name, args in (('material_prepare', manifest), ('material_execute', {
            'task_id': 'material-task', 'plan_id': pending.data['data']['plan_id'],
            'action': 'copy', 'arguments': {}})):
            self.assertTrue((await self.client.call_tool(name, args, raise_on_error=False)).is_error)
        self.assertEqual(len(self.peer.events), before)
        self.assertFalse(await runtime.release_reload_barrier(object()))
        self.assertTrue(runtime.reload_is_frozen())
        names = {tool.name for tool in await self.client.list_tools()}
        self.assertTrue(names.isdisjoint({'freeze_for_reload', 'release_reload_barrier',
            'approve', 'resume', 'agent_resume', 'agent_approve'}))
        self.assertTrue(await runtime.release_reload_barrier(ticket))
        self.assertTrue((await self.client.call_tool('material_execute', {
            'task_id': 'material-task', 'plan_id': pending.data['data']['plan_id'],
            'action': 'copy', 'arguments': {}})).data['success'])

    async def test_RL012_registry_await_rechecks_inflight_at_freeze_commit(self):
        from unittest.mock import patch
        from fastmcp.exceptions import ToolError
        runtime = self.server._candidate_runtime
        await self.client.call_tool('agent_prepare', fixtures.PREPARE)
        self.peer.approved = True
        entered, release = asyncio.Event(), asyncio.Event()
        read_entered, read_release = asyncio.Event(), asyncio.Event()
        original_connection = runtime.connection
        async def lookup():
            result = await original_connection()
            entered.set()
            await release.wait()
            return result
        async def hold(message):
            if message['params']['kind'] == 'execute':
                read_entered.set()
                await read_release.wait()
        self.peer.hook = hold
        work = None
        with patch.object(runtime, 'connection', side_effect=lookup):
            freeze = asyncio.create_task(runtime.freeze_for_reload(window=30))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                # Use the real SDK read path; it too awaits the controlled lookup.
                work = asyncio.create_task(self.client.call_tool('manage_animation', fixtures.READ))
                async with asyncio.timeout(3):
                    while not runtime.inflight:
                        await asyncio.sleep(0)
                release.set()
                with self.assertRaisesRegex(ToolError, 'reload_not_quiescent'):
                    await asyncio.wait_for(freeze, 3)
                await asyncio.wait_for(read_entered.wait(), 3)
            finally:
                release.set(); read_release.set()
                if not freeze.done(): freeze.cancel()
                await asyncio.gather(freeze, return_exceptions=True)
                if work is not None: await asyncio.wait_for(work, 3)
        self.assertIsNone(runtime._reload_barrier)
        self.assertEqual(runtime.inflight, {})

    async def _assert_postread_cleanup_blocks_freeze(self, material):
        from unittest.mock import patch
        from fastmcp.exceptions import ToolError
        runtime = self.server._candidate_runtime
        if material:
            prepared = await self.client.call_tool('material_prepare', {
                'task_id': 'material-task', 'source': 'Assets/Original.mat',
                'candidate': 'Assets/Candidate.mat', 'operations': ['copy'],
                'references': [], 'ttl_seconds': 60})
            name, args = 'material_execute', {'task_id': 'material-task',
                'plan_id': prepared.data['data']['plan_id'], 'action': 'copy', 'arguments': {}}
        else:
            await self.client.call_tool('agent_prepare', fixtures.PREPARE)
            name, args = 'manage_animation', fixtures.READ
        self.peer.approved = True
        self.peer.execute_response = {'success': False, 'error': 'fixture_readback_failed'}
        entered, release = asyncio.Event(), asyncio.Event()
        original_stop = runtime.notify_stop
        async def hold_cleanup(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original_stop(*args, **kwargs)
        with patch.object(runtime, 'notify_stop', side_effect=hold_cleanup):
            work = asyncio.create_task(self.client.call_tool(name, args, raise_on_error=False))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                # Native reply has completed, but middleware finally is still active.
                self.assertFalse(fixtures.PluginHub._pending)
                self.assertEqual([i.name for i in runtime.inflight.values()], [name])
                self.assertTrue(all(i.active for i in runtime.inflight.values()))
                with self.assertRaisesRegex(ToolError, 'reload_not_quiescent'):
                    await runtime.freeze_for_reload(window=30)
                self.assertFalse(work.done())
            finally:
                release.set()
                result = await asyncio.wait_for(work, 3)
        self.assertTrue(result.is_error or result.data.get('success') is False)
        self.assertEqual(runtime.inflight, {})
        self.assertTrue(runtime.lifecycle_results[-1]['unity_confirmed'])

    async def test_RL013_read_finally_notify_stop_remains_inflight(self):
        await self._assert_postread_cleanup_blocks_freeze(material=False)

    async def test_RL014_material_finally_notify_stop_remains_inflight(self):
        await self._assert_postread_cleanup_blocks_freeze(material=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
