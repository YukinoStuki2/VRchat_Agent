"""Real Windows console + production diagnostic CLI, simulated operator only.

The test allocates its OWN console and attaches a Job-owned child through a
fixture bootstrap. This is not native Codex launch or a human-approval verdict.
No credentials/user files/network listeners. Linux execution fails explicitly.
"""
import json
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = None
RECEIPTS = []
sys.path.insert(0, str(ROOT))


@unittest.skipUnless(os.name == 'nt', 'real Windows console required; NOT VERIFIED')
class WindowsDiagnosticConsole(unittest.TestCase):
    def exercise(self, mode):
        import win32console as console
        from launcher.candidate_launch import make_owner, child_environment
        from launcher.direct_python import current, environment_hint
        assert BUNDLE is not None, 'explicit relocated runtime required'
        entry = BUNDLE / 'diagnostics/cli.py'
        self.assertTrue(entry.is_file())
        # This entire test runs in a separate, ephemeral CI process.
        try:
            console.FreeConsole()
        except console.error:
            pass
        console.AllocConsole()
        self.addCleanup(console.FreeConsole)
        # STARTF_USESTDHANDLES preserves our CI pipes across AllocConsole.
        # Open the console devices themselves, not redirected standard handles.
        import win32file, win32con
        def console_device(name):
            handle = win32file.CreateFile(name, win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE, None, win32con.OPEN_EXISTING, 0, None)
            try:
                result = console.PyConsoleScreenBufferType(handle)
            finally:
                handle.Close()  # The wrapper duplicates it; never leak the original.
            self.addCleanup(result.Close)
            return result
        screen = console_device('CONOUT$')
        input_buffer = console_device('CONIN$')
        origin = console.PyCOORDType(0, 0)
        screen.SetConsoleScreenBufferSize(console.PyCOORDType(240, 300))
        screen.FillConsoleOutputCharacter(' ', 240 * 300, origin)
        screen.SetConsoleCursorPosition(origin)
        input_buffer.FlushConsoleInputBuffer()
        owner = make_owner(os.getpid())
        channels = []
        worker = None
        stderr = []
        lines = queue.Queue()
        stdout = []
        child = None
        root = None
        normal_exit = False
        with tempfile.TemporaryDirectory(prefix='diag-console-') as td:
            home = Path(td).resolve(strict=True)  # Canonicalize this owned CI fixture only.
            source = home / 'source'
            source.mkdir()
            original = 'token=synthetic-only\ncompiler fixture error 中文\n'
            (source / 'Editor.log').write_text(original, encoding='utf-8')
            def wait_for(check, message, seconds=15):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    value = check()
                    if value:
                        return value
                    time.sleep(.02)
                self.fail(message + '; child exit=' + str(child.poll() if child else None) + '; stderr=' + '\n'.join(stderr))
            def drain(fd):
                with os.fdopen(fd, 'rb') as stream:
                    for line in stream:
                        stdout.append(line)
                        lines.put(line)
            def send(data):
                self.assertEqual(os.write(writein, data), len(data))
            def rpc(identifier, method, params):
                document = {'jsonrpc': '2.0', 'method': method, 'params': params}
                if identifier is not None:
                    document['id'] = identifier
                send((json.dumps(document) + '\n').encode())
                if identifier is not None:
                    result = json.loads(lines.get(timeout=15))
                    self.assertEqual(result.get('id'), identifier)
                    self.assertNotIn('error', result)
                    return result['result']
            def type_local(text):
                events = []
                for char in text + '\r':
                    event = console.PyINPUT_RECORDType(console.KEY_EVENT)
                    event.KeyDown = True
                    event.RepeatCount = 1
                    event.Char = char
                    event.VirtualKeyCode = 13 if char == '\r' else ord(char.upper())
                    events.append(event)
                self.assertEqual(input_buffer.WriteConsoleInput(events), len(events))
            try:
                readin, writein = os.pipe()
                readout, writeout = os.pipe()
                channels.extend((readin, writein, writeout))
                worker = threading.Thread(target=drain, args=(readout,))
                worker.start()
                attach = ('import win32console,json,sys;'
                    'print("CONSOLE_FIXTURE_BEFORE="+json.dumps(win32console.GetConsoleProcessList()),file=sys.stderr,flush=True);')
                if mode != 'detached':
                    attach += 'win32console.AttachConsole(' + str(os.getpid()) + ');'
                attach += 'print("CONSOLE_FIXTURE_BOOTSTRAP_READY",file=sys.stderr,flush=True);'
                bootstrap = (attach + 'import sys,runpy;sys.path.insert(0,' + repr(str(entry.parent)) + ');'
                    'sys.argv=' + repr([str(entry), 'serve', '--root', str(source), '--file', 'Editor.log', '--task', 'windows-console-fixture']) + ';'
                    'runpy.run_path(' + repr(str(entry)) + ',run_name="__main__")')
                env = child_environment()
                env.update({key: str(home) for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'TMPDIR')})
                env.update(environment_hint())
                child = owner.spawn([current()['executable'], '-I', '-B', '-W', 'always::ResourceWarning', '-c', bootstrap],
                    env, stderr.append, stdio=(readin, writeout))
                for fd in (readin, writeout):
                    os.close(fd)
                    channels.remove(fd)
                if mode == 'detached':
                    # Even a well-formed approval line on MCP stdin cannot open a console.
                    try:
                        send(b'APPROVE ' + b'0' * 64 + b'\n')
                    except BrokenPipeError:
                        pass
                else:
                    def preview_ready():
                        text = screen.ReadConsoleOutputCharacter(240 * 300, origin)
                        match = re.search(r'APPROVE ([a-f0-9]{64})', text)
                        return (text, match.group(1)) if match else None
                    preview, digest = wait_for(preview_ready, 'local preview not rendered')
                    self.assertIn('[REDACTED]', preview)
                    self.assertNotIn('synthetic-only', preview)
                    self.assertTrue(lines.empty(), 'preview leaked onto MCP stdout')
                    if mode == 'deny':
                        send(('APPROVE ' + digest + '\n').encode())
                        type_local('CANCEL')
                    else:
                        type_local('APPROVE ' + digest)
                        rpc(1, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                            'clientInfo': {'name': 'windows-console-fixture', 'version': '1'}})
                        rpc(None, 'notifications/initialized', {})
                        self.assertEqual({t['name'] for t in rpc(2, 'tools/list', {})['tools']},
                            {'read_text_file', 'list_directory', 'get_file_info', 'agent_diagnostics_status'})
                        status = rpc(3, 'tools/call', {'name': 'agent_diagnostics_status', 'arguments': {}})
                        root = Path(status['structuredContent']['root'])
                        response = rpc(4, 'tools/call', {'name': 'read_text_file', 'arguments': {'path': str(root / 'Editor.log')}})
                        self.assertNotIn('synthetic-only', str(response))
                        self.assertIn('compiler fixture error', str(response))
                        self.assertNotEqual(response.get('isError'), True)
                os.close(writein)
                channels.remove(writein)
                wait_for(lambda: child.poll() is not None, 'diagnostic CLI did not exit')
                self.assertEqual(child.poll(), {'detached': 2, 'deny': 3, 'approve': 0}[mode], '\n'.join(stderr))
                wait_for(lambda: owner.api.job_empty(owner.job), 'diagnostic descendants remain')
                normal_exit = True
                if root is not None:
                    self.assertFalse(root.parent.parent.exists(), 'private snapshot ACL container remains')
                self.assertEqual((source / 'Editor.log').read_text(encoding='utf-8'), original)
                self.assertEqual(sorted(p.name for p in home.iterdir()), ['source'])
            finally:
                clean = owner.close()
                for fd in channels:
                    os.close(fd)
                if worker:
                    worker.join(5)
                self.assertTrue(clean, 'owned Job cleanup failed')
                self.assertFalse(worker and worker.is_alive(), 'stdio reader remains')
            self.assertNotIn('ResourceWarning:', '\n'.join(stderr))
            if mode != 'approve':
                self.assertEqual(stdout, [])
            if mode == 'detached':
                self.assertIn('local_console_unavailable', '\n'.join(stderr))
        self.assertFalse(Path(td).exists())
        RECEIPTS.append({'case': self.id(), 'mode': mode, 'normal_exit': normal_exit,
            'job_empty_before_cleanup': True, 'temporary_root_absent': True,
            'source_unchanged': True, 'human_approval_verified': False})

    def test_DW001_detached_stdin_cannot_approve(self):
        self.exercise('detached')

    def test_DW002_mcp_stdin_cannot_override_local_denial(self):
        self.exercise('deny')

    def test_DW003_local_console_approval_native_stdio_read_and_eof(self):
        self.exercise('approve')


if __name__ == '__main__':
    if os.name != 'nt':
        raise SystemExit('real Windows required; no Linux substitute')
    if len(sys.argv) != 2:
        raise SystemExit('explicit relocated Runtime~ directory required')
    BUNDLE = Path(sys.argv.pop()).resolve(strict=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WindowsDiagnosticConsole))
    print('WINDOWS_DIAGNOSTIC_CONSOLE=' + json.dumps(RECEIPTS), flush=True)
    raise SystemExit(not result.wasSuccessful() or bool(result.skipped) or result.testsRun != 3 or len(RECEIPTS) != 3)
