"""Characterize real SDK cancellation separately from server coroutine cancel.
No production changes. Unity peer and paused native routing are explicit fixtures.
Old RR003 evidence is retained, not silently turned green.
"""
import asyncio
from unittest.mock import patch
import unittest

import test_runtime as fixture
from fastmcp.server.dependencies import get_context
from fastmcp.server.middleware import Middleware
from transport.plugin_hub import PluginHub


class CancellationContract(fixture.RuntimeTests):
    async def exercise(self, explicit):
        await self.client.call_tool('agent_prepare', fixture.PREPARE)
        self.peer.approved = True
        entered, release, ended, completed = (asyncio.Event() for _ in range(4))
        request_ids = []
        class ObserveRead(Middleware):
            async def on_call_tool(self, context, call_next):
                try:
                    return await call_next(context)
                finally:
                    if context.message.name == 'manage_animation':
                        completed.set()
        self.server.add_middleware(ObserveRead())
        original = PluginHub.instance_resolver
        async def paused(*args, **kwargs):
            request_ids.append(get_context().request_context.request_id)
            entered.set()
            try:
                await release.wait()
                return await original(*args, **kwargs)
            finally:
                ended.set()
        with patch.object(PluginHub, 'instance_resolver', paused):
            request = asyncio.create_task(self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                if explicit:
                    await self.client.cancel(request_ids[0], reason='fixture explicit protocol cancellation')
                    await asyncio.wait_for(ended.wait(), 3)
                    await asyncio.wait_for(completed.wait(), 3)
                    await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 3)
                else:
                    request.cancel()
                    outcome = await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 3)
                    self.assertIsInstance(outcome[0], asyncio.CancelledError)
                    await self.client.ping()
                    self.assertFalse(ended.is_set(), 'local coroutine cancel unexpectedly cancelled server route')
                    release.set()
                    await asyncio.wait_for(completed.wait(), 3)
            finally:
                release.set()
                if not request.done():
                    request.cancel()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 3)
        executes = sum(e['params']['kind'] == 'execute' for e in self.peer.events)
        again = await self.client.call_tool('manage_animation', fixture.READ, raise_on_error=False)
        if explicit:
            self.assertEqual(executes, 0)
            self.assertTrue(again.is_error or (again.data or {}).get('success') is False)
        else:
            self.assertEqual(executes, 1, 'characterization: already queued read can still finish')
            self.assertTrue(again.data['success'], 'characterization: local cancel alone is not remote revocation')

    async def test_CC001_local_coroutine_cancel_is_not_mcp_revocation(self):
        await self.exercise(False)

    async def test_CC002_explicit_protocol_cancel_revokes_without_send(self):
        await self.exercise(True)


if __name__ == '__main__':
    # Do not double-count inherited baseline cases.
    suite = unittest.TestSuite(CancellationContract(name) for name in (
        'test_CC001_local_coroutine_cancel_is_not_mcp_revocation',
        'test_CC002_explicit_protocol_cancel_revokes_without_send'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
