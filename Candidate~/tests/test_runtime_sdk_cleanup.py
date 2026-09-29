"""Real HTTP/SDK resource ownership tests; no Unity/config/installed-file edits.
Observe stream allocation/closure without closing anything on the SDK's behalf.
"""
import asyncio
import gc
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest.mock import patch

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from fastmcp import Client, FastMCP
import uvicorn


class SDKCleanupTests(unittest.TestCase):
    def test_SC001_completed_http_sessions_close_all_memory_streams(self):
        self.isolated_http_case('complete')

    def test_SC003_abandoned_post_stream_is_closed_without_losing_session(self):
        self.isolated_http_case('abandon')

    def isolated_http_case(self, mode):
        # SSE's AppStatus is process-global. Each production sidecar owns one
        # server lifetime; exercise that, not two servers after global shutdown.
        import mcp
        code = ('import asyncio,runpy; n=runpy.run_path(' + repr(__file__) + ')\n'
                'async def run():\n'
                ' async with asyncio.timeout(12):\n'
                '  await n["SDKCleanupTests"]().exercise(' + repr(mode) + ')\n'
                'asyncio.run(run())\n')
        with tempfile.TemporaryDirectory(prefix='sdk-http-case-') as home:
            result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True,
                text=True, timeout=18, env={'PATH':'/usr/bin:/bin','HOME':home,
                'LANG':'C.UTF-8','FASTMCP_CHECK_FOR_UPDATES':'off',
                'PYTHONPATH':str(Path(mcp.__file__).resolve().parents[1]),
                'PYTHONWARNINGS':'always::ResourceWarning'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('ResourceWarning:', result.stderr)
        self.assertFalse(Path(home).exists())

    async def exercise(self, mode):
        streams = []
        originals = {cls: cls.__post_init__ for cls in
                     (MemoryObjectReceiveStream, MemoryObjectSendStream)}

        def observed_init(obj):
            originals[type(obj)](obj)
            streams.append(obj)

        mcp = FastMCP('sdk-cleanup-fixture')
        entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        @mcp.tool
        def fixture_read() -> dict:
            return {'fixture_only': True}

        @mcp.tool
        async def fixture_block() -> dict:
            entered.set()
            try:
                await release.wait()
                return {'fixture_only': True}
            finally:
                finished.set()

        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter('always', ResourceWarning)
            with patch.object(MemoryObjectReceiveStream, '__post_init__', observed_init), \
                 patch.object(MemoryObjectSendStream, '__post_init__', observed_init):
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1', 0))
                    port = listener.getsockname()[1]
                    server = uvicorn.Server(uvicorn.Config(mcp.http_app(path='/mcp'),
                        log_level='error', access_log=False, timeout_graceful_shutdown=3))
                    task = asyncio.create_task(server.serve(sockets=[listener]))
                    try:
                        async with asyncio.timeout(5):
                            while not server.started:
                                if task.done():
                                    await task
                                    self.fail('server exited before readiness')
                                await asyncio.sleep(.01)
                        for _ in range(3):
                            async with Client(f'http://127.0.0.1:{port}/mcp') as client:
                                result = await client.call_tool('fixture_read', {})
                                self.assertEqual(result.data, {'fixture_only': True})
                                if mode == 'abandon':
                                    import httpx
                                    entered.clear(); release.clear(); finished.clear()
                                    async with httpx.AsyncClient(trust_env=False, timeout=3) as raw:
                                        headers = {'accept': 'application/json, text/event-stream',
                                            'mcp-session-id': client.transport.get_session_id(),
                                            'mcp-protocol-version': client.initialize_result.protocolVersion}
                                        try:
                                            async with raw.stream('POST', f'http://127.0.0.1:{port}/mcp',
                                                headers=headers, json={'jsonrpc': '2.0', 'id': 'abandoned',
                                                    'method': 'tools/call', 'params': {'name': 'fixture_block'}}) as response:
                                                self.assertEqual(response.status_code, 200)
                                                await asyncio.wait_for(entered.wait(), 3)
                                            # Closing an HTTP stream is NOT a session termination.
                                        finally:
                                            release.set()
                                        await asyncio.wait_for(finished.wait(), 3)
                                    self.assertEqual((await client.call_tool('fixture_read', {})).data,
                                                     {'fixture_only': True})
                    finally:
                        release.set()
                        server.should_exit = True
                        await asyncio.wait_for(task, 6)
                with socket.socket() as check:
                    self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0)
                self.assertTrue(task.done())
                unclosed = [type(s).__name__ for s in streams if not s._closed]
                allocated = len(streams)
                streams.clear()
                gc.collect()
            self.assertGreater(allocated, 0, 'instrumentation saw no real stream')
            self.assertEqual(unclosed, [], 'HTTP/SDK streams were not explicitly closed')
            self.assertEqual([str(w.message) for w in emitted
                              if issubclass(w.category, ResourceWarning)], [])


class SDKSelectionTests(unittest.TestCase):
    def test_SC002_http_application_rejects_unpatched_sdk(self):
        root = Path(__file__).resolve().parents[1]
        code = ('import asyncio,sys; sys.path[:0]=' + repr([str(root/'runtime'), str(root/'native/src')]) + '\n'
                'from candidate_runtime import create_app,create_server\n'
                'async def run():\n'
                ' try: create_app(create_server("fixture-project"))\n'
                ' except RuntimeError as e:\n'
                '  assert str(e)=="candidate_sdk_required",str(e)\n'
                ' else: raise AssertionError("unpatched SDK was silently accepted")\n'
                'asyncio.run(run())\n')
        with tempfile.TemporaryDirectory(prefix='sdk-selection-') as home:
            result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True,
                text=True, timeout=15, env={'PATH':'/usr/bin:/bin','HOME':home,
                'LANG':'C.UTF-8','DISABLE_TELEMETRY':'true','FASTMCP_CHECK_FOR_UPDATES':'off'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(Path(home).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
