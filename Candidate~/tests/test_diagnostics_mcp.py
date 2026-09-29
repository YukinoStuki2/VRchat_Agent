"""Real official filesystem stdio backend; only synthetic source files."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

from fastmcp import Client

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'diagnostics'))
import snapshot


class DiagnosticsMCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import patch
        import mcp.client.stdio as stdio
        self.processes = []
        create = stdio._create_platform_compatible_process
        async def record(*args, **kwargs):
            process = await create(*args, **kwargs)
            self.processes.append(process)
            return process
        instrument = patch.object(stdio, '_create_platform_compatible_process', side_effect=record)
        instrument.start()
        self.addCleanup(instrument.stop)
        self.addAsyncCleanup(self.verify_process_cleanup)

    async def verify_process_cleanup(self):
        for process in self.processes:
            self.assertEqual(process.returncode, 0, f'backend {process.pid} required forced termination')
            self.assertFalse(Path(f'/proc/{process.pid}').exists())
            with self.assertRaises(ProcessLookupError):
                os.killpg(process.pid, 0)
        print('DIAGNOSTICS_PROCESS_CLEANUP=' + __import__('json').dumps({
            'case': self.id(), 'processes': [p.pid for p in self.processes],
            'all_exit_zero': True, 'all_process_groups_absent': True}))

    async def test_DM001_fixed_snapshot_native_stdio_and_local_revoke(self):
        self.assertTrue((BASE / 'diagnostics/server.py').is_file(), 'diagnostic server factory missing')
        from server import create_server
        with tempfile.TemporaryDirectory(prefix='diag-mcp-') as name:
            source = Path(name) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('fixture compiler error\n')
            (source / 'private.txt').write_text('unselected fixture')
            with snapshot.capture(source, ['Editor.log'], task_id='diag-task', temp_parent=name) as snap:
                server = create_server(snap)
                async with Client(server, roots=[source.as_uri()]) as client:
                    tools = {t.name for t in await client.list_tools()}
                    self.assertEqual(tools, {'read_text_file', 'list_directory', 'get_file_info', 'agent_diagnostics_status'})
                    self.assertEqual(await client.list_resources(), [])
                    self.assertEqual(await client.list_prompts(), [])
                    status = await client.call_tool('agent_diagnostics_status', {})
                    self.assertEqual(status.data['task_id'], 'diag-task')
                    self.assertEqual(status.data['selected'], ['Editor.log'])
                    (source / 'Editor.log').write_text('changed after export')
                    read = await client.call_tool('read_text_file', {'path': str(snap.root / 'Editor.log')})
                    self.assertIn('fixture compiler error', str(read.content))
                    self.assertNotIn('changed after export', str(read.content))
                    for path in (source / 'private.txt', snap.root / '../sibling.txt'):
                        result = await client.call_tool('read_text_file', {'path': str(path)}, raise_on_error=False)
                        self.assertTrue(result.is_error)
                    denied = await client.call_tool('write_file', {'path': str(snap.root / 'new.txt'), 'content': 'x'}, raise_on_error=False)
                    self.assertTrue(denied.is_error)
                    async with Client(server) as second:
                        denied = await second.call_tool('agent_diagnostics_status', {}, raise_on_error=False)
                        self.assertTrue(denied.is_error, 'second SDK session inherited diagnostic grant')
                root = snap.root
            self.assertFalse(root.parent.exists())
            async with Client(server) as fresh:
                result = await fresh.call_tool('agent_diagnostics_status', {}, raise_on_error=False)
                self.assertTrue(result.is_error, 'closed local export remained usable')
        self.assertFalse(Path(name).exists())


    async def test_DM002_initialization_is_local_and_all_catalog_calls_are_bound(self):
        from unittest.mock import patch
        import mcp.client.stdio as stdio
        from server import create_server
        processes = []
        create = stdio._create_platform_compatible_process
        async def record_process(*args, **kwargs):
            process = await create(*args, **kwargs)
            processes.append(process)
            return process
        with tempfile.TemporaryDirectory(prefix='diag-catalog-') as name:
            source = Path(name) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('fixture')
            with snapshot.capture(source, ['Editor.log'], task_id='fixture', temp_parent=name) as snap:
                server = create_server(snap)
                with patch.object(stdio, '_create_platform_compatible_process', side_effect=record_process):
                    async with Client(server) as first:
                        self.assertEqual(processes, [], 'initialize spawned backend before local lease checks')
                        await first.call_tool('agent_diagnostics_status', {})
                        # SDK may list tools to validate the first call; count that
                        # completed permitted discovery separately from initialize.
                        before_second = len(processes)
                        async with Client(server) as second:
                            self.assertEqual(len(processes), before_second, 'second initialize spawned backend')
                            with self.assertRaises(Exception) as denied:
                                await second.list_tools()
                            self.assertIn('snapshot_bound_to_other_session', str(denied.exception))
                        self.assertEqual(len(processes), before_second, 'denied catalog spawned backend')
                    for process in processes:
                        self.assertEqual(process.returncode, 0, 'backend required forced termination')
                        self.assertFalse(Path(f'/proc/{process.pid}').exists())


    async def test_DM003_revoke_while_native_read_returns_blocks_result(self):
        from server import create_server
        from fastmcp.server.middleware import Middleware
        entered, release = asyncio.Event(), asyncio.Event()
        class HoldRead(Middleware):
            async def on_call_tool(self, context, call_next):
                result = await call_next(context)
                if context.message.name == 'read_text_file':
                    entered.set()
                    await release.wait()
                return result
        with tempfile.TemporaryDirectory(prefix='diag-revoke-') as name:
            source = Path(name) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('fixture payload must not escape')
            with snapshot.capture(source, ['Editor.log'], task_id='fixture', temp_parent=name) as snap:
                server = create_server(snap)
                server.add_middleware(HoldRead())
                async with Client(server) as client:
                    await client.list_tools()
                    task = asyncio.create_task(client.call_tool('read_text_file',
                        {'path': str(snap.root / 'Editor.log')}, raise_on_error=False))
                    try:
                        await asyncio.wait_for(entered.wait(), 5)
                        snap._active.clear()  # Same local revoke primitive used by capture exit.
                        release.set()
                        result = await asyncio.wait_for(task, 5)
                        self.assertTrue(result.is_error)
                        self.assertNotIn('fixture payload must not escape', str(result))
                        before = len(self.processes)
                        with self.assertRaises(Exception) as denied:
                            await client.list_tools()
                        self.assertIn('local_snapshot_expired_or_closed', str(denied.exception))
                        self.assertEqual(len(self.processes), before)
                    finally:
                        release.set()
                        if not task.done():
                            task.cancel()
                        await asyncio.gather(task, return_exceptions=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
