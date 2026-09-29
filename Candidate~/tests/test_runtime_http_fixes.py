"""Real local HTTP/WS request-boundary regressions; no browser exploit claim."""
import asyncio
from contextlib import asynccontextmanager

from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest

import httpx


ROOT = Path(__file__).resolve().parents[1]
PROJECT = '0123456789abcdef0123456789abcdef'


@asynccontextmanager
async def local_cli(test):
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='runtime-fix-http-') as home, tempfile.TemporaryFile() as output:
        process = await asyncio.create_subprocess_exec(sys.executable, '-B', str(ROOT / 'tests/runtime_fixture_entry.py'),
            '--project', PROJECT, '--port', str(port),
            env={'PATH': '/usr/bin:/bin', 'HOME': home, 'LANG': 'C.UTF-8', 'DISABLE_TELEMETRY': 'true'},
            stdout=output, stderr=output)
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=1) as http:
                url = f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 8
                while True:
                    try:
                        response = await http.get(url + '/does-not-exist')
                        if response.status_code == 429:
                            raise AssertionError('429: stop, no retry')
                        if response.status_code == 404:
                            break
                    except httpx.HTTPError:
                        pass
                    if process.returncode is not None or time.monotonic() >= deadline:
                        output.seek(0)
                        test.fail('CLI readiness failure: ' + output.read(5000).decode(errors='replace'))
                    await asyncio.sleep(.05)
                yield http, url, port
        finally:
            if process.returncode is None:
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 8)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                test.fail('cleanup required forced kill')
            test.assertFalse(Path(f'/proc/{process.pid}').exists())
            with socket.socket() as check:
                check.settimeout(.2)
                test.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0)
            test.assertIn(process.returncode, (0, -15))
    test.assertFalse(Path(home).exists())


class RuntimeHTTPFixTests(unittest.IsolatedAsyncioTestCase):
    async def test_RF009_http_and_ws_exact_host_and_no_browser_origin(self):
        # The RED test exercised /hub while the native route was still absent.
        await self.exercise_request_policy('/hub')

    async def test_RF011_native_path_shares_http_ws_request_policy(self):
        # Post-fix characterization of the same guard on the newly corrected path.
        await self.exercise_request_policy('/hub/plugin')

    async def exercise_request_policy(self, ws_path):
        async with local_cli(self) as (http, url, port):
            accepted_hosts = [f'127.0.0.1:{port}', f'localhost:{port}']
            rejected_hosts = ['untrusted.invalid', f'127.0.0.1.evil.invalid:{port}',
                f'localhost.evil.invalid:{port}', '127.0.0.1', f'127.0.0.1:{port + 1}',
                f'user@127.0.0.1:{port}', f'127.0.0.1:{port},evil.invalid']
            origins = ['https://untrusted.invalid', 'null', url, f'http://localhost:{port}', '']
            init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'runtime-fix-fixture', 'version': '1'}}}
            for host, origin, allowed in ([(h, None, True) for h in accepted_hosts]
                    + [(h, None, False) for h in rejected_hosts]
                    + [(accepted_hosts[0], o, False) for o in origins]):
                with self.subTest(host=host, origin=origin):
                    headers = {'Host': host, 'Accept': 'application/json, text/event-stream'}
                    if origin is not None:
                        headers['Origin'] = origin
                    response = await http.post(url + '/mcp', headers=headers, json=init)
                    self.assertNotEqual(response.status_code, 429, '429: stop')
                    sid = response.headers.get('mcp-session-id')
                    if sid:
                        deleted = await http.delete(url + '/mcp', headers={'mcp-session-id': sid})
                        self.assertIn(deleted.status_code, (200, 204))
                    self.assertEqual(response.status_code == 200, allowed)
                    self.assertEqual(sid is not None, allowed)
                    # Raw HTTP upgrade permits exactly one explicit Host header.
                    reader, writer = await asyncio.open_connection('127.0.0.1', port)
                    try:
                        lines = [f'GET {ws_path} HTTP/1.1', f'Host: {host}', 'Upgrade: websocket',
                            'Connection: Upgrade', 'Sec-WebSocket-Key: AAECAwQFBgcICQoLDA0ODw==',
                            'Sec-WebSocket-Version: 13']
                        if origin is not None:
                            lines.append('Origin: ' + origin)
                        writer.write(('\r\n'.join(lines) + '\r\n\r\n').encode('ascii'))
                        await writer.drain()
                        status = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 3)
                        self.assertEqual(b' 101 ' in status.split(b'\r\n')[0], allowed)
                    finally:
                        writer.close()
                        await writer.wait_closed()


if __name__ == '__main__':
    unittest.main(verbosity=2)
