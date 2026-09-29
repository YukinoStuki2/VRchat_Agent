"""Two finite review probes; synthetic fixtures and the real pinned Node backend.

Characterization only: no production edits, no fabricated RED. Subcases are not
separate tests. The stdio factory instrumentation calls the actual factory.
"""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastmcp import Client
from fastmcp.server.middleware import Middleware
from mcp.client.session import ClientSession
from tests import test_diagnostics_mcp as existing

snapshot = existing.snapshot
from server import create_server


class DiagnosticsReviewTests(unittest.IsolatedAsyncioTestCase):
    # Reuse process observation, not the three inherited acceptance test methods.
    asyncSetUp = existing.DiagnosticsMCPTests.asyncSetUp

    async def verify_process_cleanup(self):
        await existing.DiagnosticsMCPTests.verify_process_cleanup(self)
        print('DIAGNOSTICS_REVIEW_PROCESS_DETAIL=' + json.dumps({
            'case': self.id(), 'processes': [
                {'pid': p.pid, 'returncode': p.returncode,
                 'proc_absent': not Path(f'/proc/{p.pid}').exists()}
                for p in self.processes]}))

    async def test_DR001_raw_sdk_hidden_writers_never_reach_backend(self):
        with tempfile.TemporaryDirectory(prefix='diag-review-writers-') as name:
            source = Path(name) / 'source'
            source.mkdir()
            original = 'synthetic review source\n'
            (source / 'Editor.log').write_text(original)
            with snapshot.capture(source, ['Editor.log'], task_id='review-writers', temp_parent=name) as snap:
                server = create_server(snap)
                async with Client(server, roots=[source.as_uri()]) as client:
                    visible = {tool.name for tool in await client.list_tools()}
                    self.assertEqual(visible, {'read_text_file', 'list_directory', 'get_file_info', 'agent_diagnostics_status'})
                    frontend = client.session
                    original_call = ClientSession.call_tool
                    upstream_calls = []

                    async def tracked_call(session, name, arguments=None, *args, **kwargs):
                        if session is not frontend:
                            upstream_calls.append(name)
                        return await original_call(session, name, arguments, *args, **kwargs)

                    denied_names = []
                    calls = [
                        ('write_file', {'path': str(snap.root / 'new.txt'), 'content': 'unauthorized synthetic write'}),
                        ('edit_file', {'path': str(snap.root / 'Editor.log'), 'edits': [{'oldText': original.strip(), 'newText': 'unauthorized synthetic edit'}], 'dryRun': False}),
                        ('move_file', {'source': str(snap.root / 'Editor.log'), 'destination': str(snap.root / 'moved.log')}),
                        ('create_directory', {'path': str(snap.root / 'new-directory')}),
                    ]
                    with patch.object(ClientSession, 'call_tool', tracked_call):
                        # Positive control: instrumentation sees a real permitted
                        # call reach the actual stdio session, not just the frontend.
                        read = await frontend.call_tool('read_text_file', {'path': str(snap.root / 'Editor.log')})
                        self.assertFalse(read.isError)
                        self.assertIn(original.strip(), str(read.content))
                        self.assertEqual(upstream_calls, ['read_text_file'])
                        upstream_calls.clear()
                        for tool_name, arguments in calls:
                            with self.subTest(tool=tool_name):
                                self.assertNotIn(tool_name, visible)
                                # Raw SDK bypasses FastMCP Client's convenience
                                # discovery/validation; denial must be server-side.
                                result = await frontend.call_tool(tool_name, arguments)
                                self.assertTrue(result.isError, str(result))
                                self.assertEqual(upstream_calls, [], 'hidden writer reached the backend')
                                self.assertEqual((snap.root / 'Editor.log').read_text(), original)
                                self.assertEqual(sorted(p.name for p in snap.root.iterdir()), ['Editor.log'])
                                self.assertEqual((source / 'Editor.log').read_text(), original)
                                denied_names.append(tool_name)
                    print('DIAGNOSTICS_REVIEW_OBSERVATION=' + json.dumps({
                        'case': self.id(), 'raw_sdk_denied': denied_names,
                        'upstream_write_calls': upstream_calls,
                        'allowed_read_positive_control': True,
                        'source_and_snapshot_unchanged': True}))
                container = snap.root.parent
            self.assertFalse(container.exists())
            self.assertFalse(snap.valid())
        self.assertFalse(Path(name).exists())

    async def test_DR002_clock_expiry_blocks_inflight_result_and_later_requests(self):
        entered, release = asyncio.Event(), asyncio.Event()

        class HoldNativeRead(Middleware):
            async def on_call_tool(self, context, call_next):
                result = await call_next(context)
                if context.message.name == 'read_text_file':
                    entered.set()
                    await release.wait()
                return result

        with tempfile.TemporaryDirectory(prefix='diag-review-expiry-') as name:
            source = Path(name) / 'source'
            source.mkdir()
            payload = 'synthetic expired payload must not escape'
            (source / 'Editor.log').write_text(payload)
            with snapshot.capture(source, ['Editor.log'], task_id='review-expiry', temp_parent=name) as captured:
                # Shorten only this synthetic lease using the public dataclass;
                # keep the real monotonic clock, filesystem and backend process.
                # This does not claim a 300-second wall-clock soak was performed.
                self.assertLessEqual(captured.expires_at - time.monotonic(), 300)
                self.assertGreater(captured.expires_at - time.monotonic(), 295)
                snap = replace(captured, expires_at=time.monotonic() + 5)
                server = create_server(snap)
                server.add_middleware(HoldNativeRead())
                async with Client(server) as client:
                    self.assertEqual(self.processes, [], 'initialize created a backend')
                    await client.list_tools()
                    task = asyncio.create_task(client.session.call_tool(
                        'read_text_file', {'path': str(snap.root / 'Editor.log')}))
                    try:
                        await asyncio.wait_for(entered.wait(), 5)
                        self.assertTrue(snap.valid(), 'lease expired before native read reached barrier')
                        await asyncio.sleep(max(0, snap.expires_at - time.monotonic()) + 0.05)
                        self.assertTrue(snap._active.is_set(), 'this probe must use expiry, not revoke')
                        self.assertFalse(snap.valid())
                        release.set()
                        result = await asyncio.wait_for(task, 5)
                        self.assertTrue(result.isError)
                        self.assertIn('local_snapshot_expired_or_closed', str(result))
                        self.assertNotIn(payload, str(result))
                        process_count = len(self.processes)
                        denied = await client.session.call_tool('read_text_file', {'path': str(snap.root / 'Editor.log')})
                        self.assertTrue(denied.isError)
                        self.assertIn('local_snapshot_expired_or_closed', str(denied))
                        self.assertNotIn(payload, str(denied))
                        with self.assertRaises(Exception) as catalog_denied:
                            await client.list_tools()
                        self.assertIn('local_snapshot_expired_or_closed', str(catalog_denied.exception))
                        async with Client(server) as fresh:
                            await fresh.ping()
                            with self.assertRaises(Exception) as fresh_denied:
                                await fresh.list_tools()
                            self.assertIn('local_snapshot_expired_or_closed', str(fresh_denied.exception))
                        self.assertEqual(len(self.processes), process_count, 'expired requests spawned backend')
                        with self.assertRaisesRegex(ValueError, 'snapshot_or_pinned_backend_unavailable'):
                            create_server(snap)
                        # Expiry revokes serving, but physical deletion belongs
                        # to capture context exit, not a background expiry timer.
                        self.assertTrue(snap.root.exists())
                        print('DIAGNOSTICS_REVIEW_OBSERVATION=' + json.dumps({
                            'case': self.id(), 'clock': 'real monotonic; synthetic deadline shortened to 5 seconds',
                            'inflight_payload_denied': True, 'later_request_denied_before_backend': True,
                            'expired_new_session_initialize_ping_local': True,
                            'expired_new_session_catalog_denied': True,
                            'snapshot_present_until_context_exit': True}))
                    finally:
                        release.set()
                        if not task.done():
                            task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                container = snap.root.parent
            self.assertFalse(container.exists())
            self.assertFalse(captured.valid())
            self.assertFalse(snap._active.is_set())
        self.assertFalse(Path(name).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
