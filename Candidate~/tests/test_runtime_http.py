"""Real SDK+WS on test-only anonymous entry. Installed entry tested separately."""
import asyncio
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest

from fastmcp import Client
import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
PROJECT = '0123456789abcdef0123456789abcdef'


class RuntimeHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_RT011_local_cli_real_http_native_socket_and_cleanup(self):
        # Legacy alias coverage only: /hub is NOT the actual Unity native route.
        await self.exercise_http_peer('/hub')

    async def test_RF010_native_hub_plugin_real_http_sdk_and_ws(self):
        # WebSocketTransportClient.BuildWebSocketUri at the pinned source:847.
        try:
            await self.exercise_http_peer('/hub/plugin')
        except websockets.exceptions.InvalidStatus as exc:
            self.fail(f'native /hub/plugin handshake rejected: {exc}')

    async def exercise_http_peer(self, ws_path):
        self.assertTrue((ROOT / 'runtime/__main__.py').is_file(), 'real CLI not implemented')
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            port = reserved.getsockname()[1]
        events = []
        with tempfile.TemporaryDirectory(prefix='vragent-runtime-http-') as home, tempfile.TemporaryFile() as output:
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-B', str(ROOT / 'tests/runtime_fixture_entry.py'), '--project', PROJECT, '--port', str(port),
                env={'PATH': '/usr/bin:/bin', 'HOME': home, 'LANG': 'C.UTF-8', 'DISABLE_TELEMETRY': 'true',
                     'PYTHONWARNINGS': 'always::ResourceWarning', 'FASTMCP_CHECK_FOR_UPDATES': 'off'},
                stdout=output, stderr=output)
            try:
                url = f'http://127.0.0.1:{port}'
                async with httpx.AsyncClient(trust_env=False, timeout=.3) as probe:
                    deadline = time.monotonic() + 8
                    while True:
                        try:
                            response = await probe.get(url + '/does-not-exist')
                            if response.status_code == 404:
                                break
                        except httpx.HTTPError:
                            pass
                        if process.returncode is not None or time.monotonic() >= deadline:
                            output.seek(0)
                            self.fail('CLI readiness failed: ' + output.read(5000).decode(errors='replace'))
                        await asyncio.sleep(.05)
                async with websockets.connect(f'ws://127.0.0.1:{port}{ws_path}', proxy=None) as peer:
                    welcome = json.loads(await peer.recv())
                    self.assertEqual(welcome['type'], 'welcome')
                    await peer.send(json.dumps({'type': 'register', 'project_name': 'NOT-UNITY-FIXTURE',
                        'project_hash': PROJECT, 'unity_version': 'FIXTURE'}))
                    registered = json.loads(await peer.recv())
                    self.assertEqual(registered['type'], 'registered')

                    async def respond():
                        async for raw in peer:
                            message = json.loads(raw)
                            if message['type'] == 'ping':
                                await peer.send(json.dumps({'type': 'pong', 'session_id': registered['session_id']}))
                                continue
                            events.append(message)
                            await peer.send(json.dumps({'type': 'command_result', 'id': message['id'],
                                'result': {'status': 'success', 'result': {
                                    'success': True, 'data': {'fixture_only': True}}}}))
                    responder = asyncio.create_task(respond())
                    try:
                        async with Client(url + '/mcp') as client:
                            self.assertEqual({t.name for t in await client.list_tools()}, {
                                'agent_status', 'agent_catalog', 'agent_prepare', 'agent_stop', 'manage_animation', 'manage_material', 'read_console', 'manage_scene',
                                'material_prepare', 'material_execute', 'material_status', 'material_stop'})
                            status = await client.call_tool('agent_status', {})
                            self.assertTrue(status.data['data']['fixture_only'])
                            denied = await client.call_tool('manage_animation', {
                                'action': 'controller_get_info', 'controller_path': 'Assets/Fixture.controller'},
                                raise_on_error=False)
                            self.assertTrue(denied.is_error)
                        self.assertEqual(len(events), 1)
                        self.assertEqual(events[0]['name'], 'vrchat_agent_dispatch')
                        self.assertEqual(events[0]['params']['connection_id'], registered['session_id'])
                    finally:
                        responder.cancel()
                        await asyncio.gather(responder, return_exceptions=True)
            finally:
                if process.returncode is None:
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 8)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    self.fail('cleanup required fallback kill')
                self.assertFalse(Path(f'/proc/{process.pid}').exists(), 'residual owned process')
                with socket.socket() as check:
                    check.settimeout(.2)
                    self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0, 'residual listener')
                self.assertIn(process.returncode, (0, -15), 'unclean CLI exit')
                output.seek(0)
                self.assertNotIn('ResourceWarning:', output.read().decode(errors='replace'))
        self.assertFalse(Path(home).exists(), 'fixture home leak')


    def test_RT013_raw_upstream_startup_is_not_a_protected_entry(self):
        import subprocess
        with tempfile.TemporaryDirectory(prefix='vragent-raw-entry-') as home:
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'native/src/main.py'), '--help'],
                env={'PATH': '/usr/bin:/bin', 'HOME': home, 'LANG': 'C.UTF-8', 'DISABLE_TELEMETRY': 'true'},
                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0, 'raw main must be disabled, not offer an unguarded CLI')
        self.assertIn('candidate_entry_required', result.stderr)
        self.assertFalse(Path(home).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
