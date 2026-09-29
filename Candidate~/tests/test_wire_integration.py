"""SDK/HTTP/native-WebSocket -> compiled C# gate. Unity/evidence/user are fixtures."""
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
DOTNET = '/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet'
DLL = ROOT / 'tests/unity-core/bin/Release/net8.0/WirePeer.dll'


class CrossLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_WI001_sdk_csharp_pending_local_fixture_approve_read_stop(self):
        self.assertTrue(DLL.is_file(), 'compile WirePeer.csproj first; never silently substitute peer')
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            port = reserved.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='vragent-wire-') as home, tempfile.TemporaryFile() as log:
            env = {'PATH': '/usr/bin:/bin', 'HOME': home, 'LANG': 'C.UTF-8', 'DISABLE_TELEMETRY': 'true',
                   'DOTNET_CLI_TELEMETRY_OPTOUT': '1'}
            server = await asyncio.create_subprocess_exec(sys.executable, '-B', str(ROOT / 'tests/runtime_fixture_entry.py'),
                '--project', 'fixture-project', '--port', str(port), env=env, stdout=log, stderr=log)
            core = None
            events = []
            try:
                url = f'http://127.0.0.1:{port}'
                async with httpx.AsyncClient(trust_env=False, timeout=.3) as probe:
                    deadline = time.monotonic() + 8
                    while True:
                        try:
                            if (await probe.get(url + '/missing')).status_code == 404:
                                break
                        except httpx.HTTPError:
                            pass
                        if server.returncode is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            self.fail('CLI readiness: ' + log.read(5000).decode(errors='replace'))
                        await asyncio.sleep(.05)
                core = await asyncio.create_subprocess_exec(DOTNET, str(DLL), env=env,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=log)
                mutex = asyncio.Lock()
                async def exchange(message):
                    async with mutex:
                        core.stdin.write((json.dumps(message) + '\n').encode())
                        await core.stdin.drain()
                        response = await asyncio.wait_for(core.stdout.readline(), 3)
                        self.assertTrue(response, 'C# peer terminated without response')
                        return json.loads(response)
                async with websockets.connect(f'ws://127.0.0.1:{port}/hub/plugin', proxy=None) as ws:
                    self.assertEqual(json.loads(await ws.recv())['type'], 'welcome')
                    await ws.send(json.dumps({'type': 'register', 'project_name': 'NOT-UNITY-CSharpFixture',
                        'project_hash': 'fixture-project', 'unity_version': 'FIXTURE'}))
                    registration = json.loads(await ws.recv())
                    self.assertEqual(registration['type'], 'registered')
                    self.assertTrue((await exchange({'fixture_connection': registration['session_id']}))['fixture_ready'])
                    async def respond():
                        async for raw in ws:
                            message = json.loads(raw)
                            if message['type'] == 'ping':
                                await ws.send(json.dumps({'type': 'pong', 'session_id': registration['session_id']}))
                            else:
                                events.append(message)
                                result = await exchange({'request': message['params']})
                                await ws.send(json.dumps({'type': 'command_result', 'id': message['id'], 'result': result}))
                    responder = asyncio.create_task(respond())
                    try:
                        async with Client(url + '/mcp') as client:
                            status = await client.call_tool('agent_status', {})
                            self.assertTrue(status.data['success'])
                            plan = {'task_id': 'task-fixture', 'operations': [{'command': 'manage_material', 'action': 'get_material_info'}],
                                    'targets': ['Assets/Read.mat'], 'ttl_seconds': 60}
                            pending = await client.call_tool('agent_prepare', plan)
                            self.assertEqual(pending.data['data']['status'], 'pending')
                            self.assertEqual(len(pending.data['data']['digest']), 64)
                            read = {'action': 'get_material_info', 'material_path': 'Assets/Read.mat'}
                            denied = await client.call_tool('manage_material', read, raise_on_error=False)
                            self.assertFalse(denied.data['success'])
                            pending = await client.call_tool('agent_prepare', plan)
                            # Explicit test-only local event, not MCP or product auto-approval.
                            self.assertTrue((await exchange({'fixture_local_approve': True}))['fixture_approved'])
                            result = await client.call_tool('manage_material', read)
                            self.assertTrue(result.data['success'])
                            self.assertEqual(result.data['data']['call'], 1)
                            self.assertEqual(result.data['data']['path'], 'Assets/Read.mat')
                            stopped = await client.call_tool('agent_stop', {'task_id': 'task-fixture'})
                            self.assertEqual(stopped.data['data']['status'], 'stopped')
                            before = len(events)
                            refused = await client.call_tool('manage_material', read, raise_on_error=False)
                            self.assertTrue(refused.is_error)
                            self.assertEqual(len(events), before)
                        self.assertTrue(all(e['name'] == 'vrchat_agent_dispatch' for e in events))
                    finally:
                        responder.cancel()
                        await asyncio.gather(responder, return_exceptions=True)
            finally:
                cleanup_errors = []
                if core is not None and core.returncode is None:
                    core.stdin.close()
                if server.returncode is None:
                    server.terminate()
                for process, allowed in ((core, (0,)), (server, (0, -15))):
                    if process is None:
                        continue
                    try:
                        await asyncio.wait_for(process.wait(), 8)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                        cleanup_errors.append('fallback kill required')
                    if process.returncode not in allowed or Path(f'/proc/{process.pid}').exists():
                        cleanup_errors.append('unclean process exit')
                with socket.socket() as check:
                    check.settimeout(.2)
                    self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0)
                self.assertEqual(cleanup_errors, [])
        self.assertFalse(Path(home).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
