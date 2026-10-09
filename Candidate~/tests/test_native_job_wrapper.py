"""Actual native Python job wrapper; transport and OS focus are test doubles.
Characterizes the upstream focus seam plus the gated candidate entry.
No real Unity, window focus changes, external network, or local approval.
"""
import asyncio
import importlib
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_runtime as fixture  # Reuse temporary HOME and fail-closed network audit.
from fastmcp import Client
native = importlib.import_module('services.tools.run_tests')
focus = importlib.import_module('utils.focus_nudge')


def response(status='running', focused=False):
    return {'success': True, 'data': {'job_id': 'fixture-job', 'status': status,
        'mode': 'EditMode', 'last_update_unix_ms': int(time.time()*1000)-60000,
        'progress': {'editor_is_focused': focused}}}


class NativeJobWrapperTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertFalse(native._background_tasks, 'pre-existing background tasks')
        self.instance = self.enterContext(patch.object(native, 'get_unity_instance_from_context',
                                            new=AsyncMock(return_value='fixture-instance')))
        self.send = self.enterContext(patch.object(native.unity_transport, 'send_with_unity_instance',
                                        new=AsyncMock(return_value=response())))
        self.project = self.enterContext(patch.object(native, '_get_unity_project_path',
                                           new=AsyncMock(return_value='/fixture-only/project')))
        self.release = asyncio.Event()
        async def simulated_focus(**kwargs):
            await self.release.wait()
            return True
        self.nudge = self.enterContext(patch.object(native, 'nudge_unity_focus',
                                          new=AsyncMock(side_effect=simulated_focus)))

    async def asyncTearDown(self):
        # Drain exact test-owned tasks even on a failed assertion. Do not merely
        # clear the native set and misreport the still-running coroutine as gone.
        self.release.set()
        tasks = tuple(native._background_tasks)
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), 2)
        await asyncio.sleep(0)
        self.assertFalse(native._background_tasks)

    async def test_NP001_no_wait_still_schedules_background_focus(self):
        result = await native.get_test_job(None, 'fixture-job', wait_timeout=None)
        self.assertTrue(result.success)
        self.assertEqual(self.send.await_count, 1)
        self.project.assert_awaited_once()
        self.assertEqual(len(native._background_tasks), 1)
        await asyncio.sleep(0)
        self.nudge.assert_awaited_once_with(unity_project_path='/fixture-only/project')
        self.assertFalse(next(iter(native._background_tasks)).done())

    async def test_NP002_local_suppression_prevents_all_extra_paths(self):
        original = native.should_nudge
        self.assertIs(original, focus.should_nudge)
        with patch.object(native, 'should_nudge', return_value=False) as disabled:
            result = await native.get_test_job(None, 'fixture-job', wait_timeout=None)
            self.assertTrue(result.success)
            disabled.assert_called_once()
            self.assertIs(focus.should_nudge, original, 'global utility changed')
        self.assertIs(native.should_nudge, original, 'test patch leaked')
        self.project.assert_not_awaited()
        self.nudge.assert_not_called()
        self.assertFalse(native._background_tasks)
        self.send.assert_awaited_once_with(native.async_send_command_with_retry,
            'fixture-instance', 'get_test_job', {'job_id': 'fixture-job'})

    async def test_NP003_completed_job_does_not_schedule_focus(self):
        self.send.return_value=response('succeeded')
        self.assertTrue((await native.get_test_job(None,'fixture-job')).success)
        self.project.assert_not_awaited(); self.nudge.assert_not_called()
        self.assertFalse(native._background_tasks)

    async def test_NP004_focused_running_job_does_not_schedule_focus(self):
        self.send.return_value=response(focused=True)
        self.assertTrue((await native.get_test_job(None,'fixture-job')).success)
        self.project.assert_not_awaited(); self.nudge.assert_not_called()
        self.assertFalse(native._background_tasks)

    async def test_NP005_native_error_remains_failure_without_focus(self):
        self.send.return_value={'success':False,'error':'Unknown job_id.'}
        result=await native.get_test_job(None,'fixture-job')
        self.assertFalse(result.success)
        self.assertEqual(result.error,'Unknown job_id.')
        self.project.assert_not_awaited(); self.nudge.assert_not_called()
        self.assertFalse(native._background_tasks)

    async def test_NP006_visible_candidate_entry_denies_without_authorization(self):
        server=fixture.create_server()
        async with Client(server) as client:
            tool=next(t for t in await client.list_tools() if t.name=='get_test_job')
            self.assertIs(tool.annotations.readOnlyHint,False)
            self.assertIs(tool.annotations.idempotentHint,False)
            # A canonical ID prevents argument validation from hiding a missing grant check.
            result=await client.call_tool('get_test_job',{'job_id':'0123456789abcdef0123456789abcdef'},raise_on_error=False)
            self.assertTrue(result.is_error)
            self.assertIn('plan_not_current',' '.join(x.text for x in result.content if hasattr(x,'text')))
        self.assertEqual(server._candidate_runtime.plans,{})
        self.send.assert_not_awaited(); self.instance.assert_not_awaited()
        self.project.assert_not_awaited(); self.nudge.assert_not_called()
        self.assertFalse(native._background_tasks)


if __name__ == '__main__':
    unittest.main()
