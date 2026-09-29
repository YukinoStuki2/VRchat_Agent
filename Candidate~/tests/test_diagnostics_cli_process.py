"""Linux PTY integration: simulated operator, real CLI/SDK/Node, no listener."""
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

BASE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'linux', 'real Linux PTY integration only')
class CLIPTYTests(unittest.TestCase):
    def exercise(self, stop):
        import fcntl
        import pty
        import termios
        with tempfile.TemporaryDirectory(prefix='dc-pty-') as home:
            source = Path(home) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('token=synthetic-only\ncompiler fixture error\n')
            master, slave = pty.openpty()
            process = None
            observer = None
            finished = threading.Event()
            seen = set()
            def setup_terminal():
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            def observe():
                while not finished.wait(0.003):
                    for pid in [process.pid, *list(seen)]:
                        try:
                            children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
                            seen.update(int(p) for p in children)
                        except FileNotFoundError:
                            pass
            def wait_bytes(fd, marker, timeout=15):
                output = b''
                end = time.monotonic() + timeout
                while marker not in output:
                    self.assertGreater(end, time.monotonic(), 'bounded PTY/stdio timeout')
                    ready, _, _ = select.select([fd], [], [], max(0, end-time.monotonic()))
                    self.assertTrue(ready, 'no PTY/stdio response')
                    block = os.read(fd, 1 if marker == b'\n' else 65536)
                    self.assertTrue(block, 'unexpected CLI EOF')
                    output += block
                return output
            def rpc(identifier, method, params):
                value = {'jsonrpc': '2.0', 'method': method, 'params': params}
                if identifier is not None:
                    value['id'] = identifier
                process.stdin.write((json.dumps(value) + '\n').encode())
                process.stdin.flush()
                if identifier is not None:
                    result = json.loads(wait_bytes(process.stdout.fileno(), b'\n'))
                    self.assertEqual(result.get('id'), identifier)
                    self.assertNotIn('error', result)
                    return result['result']
            try:
                process = subprocess.Popen([sys.executable, '-B', str(BASE / 'diagnostics/cli.py'),
                    'serve', '--root', str(source), '--file', 'Editor.log', '--task', 'fixture-pty'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    bufsize=0, pass_fds=(slave,), preexec_fn=setup_terminal,
                    env={'PATH': '/usr/bin:/bin', 'HOME': home, 'TMPDIR': home,
                         'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'})
                observer = threading.Thread(target=observe)
                observer.start()
                preview = wait_bytes(master, '其他输入取消：'.encode()).decode()
                self.assertIn('[REDACTED]', preview)
                self.assertNotIn('synthetic-only', preview)
                self.assertFalse(select.select([process.stdout], [], [], 0)[0], 'preview leaked onto MCP stdout')
                digest = re.search(r'APPROVE ([a-f0-9]{64})', preview).group(1)
                os.write(master, ('APPROVE ' + digest + '\n').encode())
                rpc(1, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                     'clientInfo': {'name': 'synthetic-pty-test', 'version': '1'}})
                rpc(None, 'notifications/initialized', {})
                tools = rpc(2, 'tools/list', {})
                self.assertEqual({t['name'] for t in tools['tools']},
                    {'read_text_file', 'list_directory', 'get_file_info', 'agent_diagnostics_status'})
                status = rpc(3, 'tools/call', {'name': 'agent_diagnostics_status', 'arguments': {}})
                info = status['structuredContent']
                root = Path(info['root'])
                result = rpc(4, 'tools/call', {'name': 'read_text_file', 'arguments': {'path': str(root / 'Editor.log')}})
                self.assertNotIn('synthetic-only', str(result))
                self.assertIn('compiler fixture error', str(result))
                self.assertEqual((source / 'Editor.log').read_text(), 'token=synthetic-only\ncompiler fixture error\n')
                if stop == 'eof':
                    process.stdin.close()
                    process.stdin = None
                else:
                    process.send_signal(stop)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stderr.decode())
                self.assertEqual(stdout, b'')
                self.assertFalse(root.parent.exists(), 'snapshot persisted after session ended')
                self.assertEqual(sorted(p.name for p in Path(home).iterdir()), ['source'])
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
                finished.set()
                if observer:
                    observer.join(timeout=5)
                os.close(master)
                os.close(slave)
                alive = [p for p in seen if Path(f'/proc/{p}').exists()]
                # Exact test-owned descendants only; report failure even after cleanup.
                for pid in alive:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.assertEqual(alive, [], 'owned descendant cleanup required forced kill')
                if process:
                    self.assertFalse(Path(f'/proc/{process.pid}').exists())
                    with self.assertRaises(ProcessLookupError):
                        os.killpg(process.pid, 0)
            print('DIAGNOSTICS_CLI_CLEANUP=' + json.dumps({'case': self.id(),
                'cli_pid': process.pid, 'observed_descendants': sorted(seen),
                'exit_code': process.returncode, 'fixture_removed_after_context': home}))
        self.assertFalse(Path(home).exists())

    def test_DC007_sigterm_during_preview_cleans_unapproved_snapshot(self):
        import fcntl
        import pty
        import termios
        with tempfile.TemporaryDirectory(prefix='dc-preview-stop-') as home:
            source = Path(home) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('synthetic pending preview')
            master, slave = pty.openpty()
            def setup():
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            process = None
            try:
                process = subprocess.Popen([sys.executable, '-B', str(BASE / 'diagnostics/cli.py'),
                    'serve', '--root', str(source), '--file', 'Editor.log', '--task', 'fixture'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    pass_fds=(slave,), preexec_fn=setup,
                    env={'PATH': '/usr/bin:/bin', 'HOME': home, 'TMPDIR': home, 'LANG': 'C.UTF-8'})
                preview = b''
                deadline = time.monotonic() + 10
                while b'APPROVE ' not in preview:
                    self.assertGreater(deadline, time.monotonic())
                    self.assertTrue(select.select([master], [], [], max(0, deadline-time.monotonic()))[0])
                    preview += os.read(master, 65536)
                self.assertTrue(list(Path(home).glob('diagnostics-*')))
                process.send_signal(signal.SIGTERM)
                output, error = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 130, error.decode())
                self.assertEqual(output, b'')
                self.assertEqual(sorted(p.name for p in Path(home).iterdir()), ['source'])
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
                os.close(master)
                os.close(slave)
                if process:
                    self.assertFalse(Path(f'/proc/{process.pid}').exists())
                    with self.assertRaises(ProcessLookupError):
                        os.killpg(process.pid, 0)
        self.assertFalse(Path(home).exists())

    def test_DC006_sigterm_revokes_and_cleans_session(self):
        self.exercise(signal.SIGTERM)

    def test_DC005_real_console_approval_stdio_read_and_eof_cleanup(self):
        self.exercise('eof')


if __name__ == '__main__':
    unittest.main(verbosity=2)
