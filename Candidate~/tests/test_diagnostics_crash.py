"""Real interpreter termination with synthetic, unapproved snapshots only.

The safety fixture owns the whole temporary tree. No service/model/real project.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

BASE = Path(__file__).resolve().parents[1]
if len(sys.argv) > 2 and sys.argv[1] == '--runtime-root':
    BASE = Path(sys.argv[2]).resolve(strict=True)
    del sys.argv[1:3]


class CrashSnapshotTests(unittest.TestCase):
    def test_DX005_default_container_uses_callers_temp_directory(self):
        from unittest.mock import patch
        sys.path.insert(0, str(BASE / 'diagnostics'))
        import snapshot, lifetime
        with tempfile.TemporaryDirectory(prefix='diagnostic-default-temp-') as temp:
            home = Path(temp).resolve(); project = home / 'project'; project.mkdir()
            (project / 'Editor.log').write_text('synthetic explicit OS temp')
            private = home / 'private'; private.mkdir(mode=0o700)
            # The caller's OS-selected TEMP must survive the helper's clean environment.
            with patch.object(lifetime.tempfile, 'gettempdir', return_value=str(private)):
                with snapshot.capture(project, ['Editor.log'], task_id='caller-temp') as snap:
                    self.assertTrue(snap.root.is_relative_to(private), 'helper ignored caller-selected OS temp')
            self.assertEqual(list(private.iterdir()), [])

    def test_DX002_expiry_during_capture_cannot_recreate_deleted_root(self):
        from unittest.mock import patch
        sys.path.insert(0, str(BASE / 'diagnostics'))
        import snapshot, lifetime
        real_popen = subprocess.Popen
        real_read = snapshot.read_selected
        keeper_code = ('import sys;sys.path.insert(0,' + repr(str(BASE / 'diagnostics')) + ');'
                       'import lifetime;lifetime.TTL=1;raise SystemExit(lifetime._worker())')
        def short_keeper(argv, **kwargs):
            self.assertEqual(Path(argv[-1]), BASE / 'diagnostics/lifetime.py')
            return real_popen([argv[0], '-I', '-B', '-c', keeper_code], **kwargs)
        def delayed_read(*args, **kwargs):
            data = real_read(*args, **kwargs)
            time.sleep(1.2)
            return data
        with tempfile.TemporaryDirectory(prefix='diagnostic-capture-expiry-') as temp:
            home = Path(temp).resolve()
            project = home / 'project'; project.mkdir()
            (project / 'Editor.log').write_text('synthetic delayed capture')
            private = home / 'private'; private.mkdir(mode=0o700)
            with patch.object(lifetime.subprocess, 'Popen', side_effect=short_keeper), patch.object(snapshot, 'read_selected', side_effect=delayed_read):
                with self.assertRaises(ValueError):
                    with snapshot.capture(project, ['Editor.log'], task_id='expiry-fixture', temp_parent=private):
                        self.fail('expired capture was published')
            self.assertEqual(list(private.iterdir()), [], 'capture recreated plaintext after keeper expiry')

    def test_DX003_keeper_failure_revokes_and_caller_cleans_exact_copy(self):
        from unittest.mock import patch
        sys.path.insert(0, str(BASE / 'diagnostics'))
        import snapshot, lifetime
        real_popen = subprocess.Popen
        keepers = []
        def record(*args, **kwargs):
            process = real_popen(*args, **kwargs); keepers.append(process); return process
        with tempfile.TemporaryDirectory(prefix='diagnostic-keeper-death-') as temp:
            home = Path(temp).resolve(); project = home / 'project'; project.mkdir()
            (project / 'Editor.log').write_text('synthetic helper failure')
            private = home / 'private'; private.mkdir(mode=0o700)
            with patch.object(lifetime.subprocess, 'Popen', side_effect=record):
                with self.assertRaisesRegex(RuntimeError, 'snapshot_guard_cleanup_failed'):
                    with snapshot.capture(project, ['Editor.log'], task_id='helper-death', temp_parent=private) as snap:
                        self.assertTrue(snap.valid()); self.assertEqual(len(keepers), 1)
                        keepers[0].kill(); keepers[0].wait(timeout=10)
                        self.assertFalse(snap.valid())
            self.assertEqual(list(private.iterdir()), [])
            self.assertEqual((project / 'Editor.log').read_text(), 'synthetic helper failure')

    def test_DX004_sealed_unapproved_copy_expires_while_owner_waits(self):
        from unittest.mock import patch
        sys.path.insert(0, str(BASE / 'diagnostics'))
        import snapshot, lifetime
        real_popen = subprocess.Popen
        keeper_code = ('import sys;sys.path.insert(0,' + repr(str(BASE / 'diagnostics')) + ');'
                       'import lifetime;lifetime.TTL=2;raise SystemExit(lifetime._worker())')
        def short_keeper(argv, **kwargs):
            self.assertEqual(Path(argv[-1]), BASE / 'diagnostics/lifetime.py')
            return real_popen([argv[0], '-I', '-B', '-c', keeper_code], **kwargs)
        with tempfile.TemporaryDirectory(prefix='diagnostic-preview-expiry-') as temp:
            home = Path(temp).resolve(); project = home / 'project'; project.mkdir()
            (project / 'Editor.log').write_text('synthetic pending preview')
            private = home / 'private'; private.mkdir(mode=0o700)
            with patch.object(lifetime.subprocess, 'Popen', side_effect=short_keeper):
                with snapshot.capture(project, ['Editor.log'], task_id='preview-wait', temp_parent=private) as snap:
                    self.assertTrue(snap.valid())
                    deadline = time.monotonic() + 8
                    while snap.root.parent.exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertFalse(snap.valid())
                    self.assertFalse(snap.root.parent.exists())
            self.assertEqual(list(private.iterdir()), [])

    def test_DX001_killed_capture_owner_removes_unapproved_copy(self):
        if sys.platform not in ('linux', 'win32'):
            self.skipTest('requires implemented capture platform')
        with tempfile.TemporaryDirectory(prefix='diagnostic-crash-test-') as temp:
            home = Path(temp).resolve()  # Only canonicalize our own Windows TEMP fixture.
            project = home / 'project'
            project.mkdir()
            (project / 'Editor.log').write_text('unapproved synthetic crash evidence\n')
            private = home / 'private'
            private.mkdir(mode=0o700)
            code = (
                'import json,sys;sys.path.insert(0,' + repr(str(BASE / 'diagnostics')) + ')\n'
                'from snapshot import capture\n'
                'import lifetime\n'
                '_launch=lifetime.subprocess.Popen;keepers=[]\n'
                'def tracked(*a,**k):\n'
                ' p=_launch(*a,**k);keepers.append(p);return p\n'
                'lifetime.subprocess.Popen=tracked\n'
                'with capture(' + repr(str(project)) + ',["Editor.log"],task_id="crash-fixture",'
                'temp_parent=' + repr(str(private)) + ') as snap:\n'
                ' print(json.dumps({"root":str(snap.root),"keeper_pid":keepers[0].pid}),flush=True)\n'
                ' sys.stdin.buffer.read(1)\n'
            )
            env = {k: os.environ[k] for k in ('SYSTEMROOT', 'SystemRoot', 'WINDIR') if k in os.environ}
            env.update({k: str(home) for k in ('HOME', 'USERPROFILE', 'TEMP', 'TMP', 'TMPDIR')})
            env['PATH'] = os.defpath
            # stdlib-only child uses the real interpreter, not a Windows venv redirector.
            executable = getattr(sys, '_base_executable', sys.executable)
            process = subprocess.Popen([executable, '-I', '-B', '-W', 'always::ResourceWarning', '-c', code],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            ready = queue.Queue()
            reader = threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True)
            reader.start()
            keeper_handle = None
            try:
                line = ready.get(timeout=15)
                self.assertTrue(line, 'capture failed before readiness')
                data = json.loads(line)
                root = Path(data['root'])
                self.assertTrue(root.is_relative_to(private))
                if sys.platform == 'linux':
                    keeper_handle = os.pidfd_open(data['keeper_pid'])
                else:
                    import ctypes
                    from ctypes import wintypes
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    kernel.OpenProcess.restype = wintypes.HANDLE
                    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                    kernel.WaitForSingleObject.restype = wintypes.DWORD
                    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                    kernel.CloseHandle.restype = wintypes.BOOL
                    keeper_handle = kernel.OpenProcess(0x100000, False, data['keeper_pid'])
                    self.assertTrue(keeper_handle, 'cannot pin keeper process identity')
                self.assertEqual((root / 'Editor.log').read_text(), 'unapproved synthetic crash evidence\n')
                process.kill()  # Actual SIGKILL / TerminateProcess, not an exception/finally test.
                stdout, stderr = process.communicate(timeout=15)
                self.assertNotEqual(process.returncode, 0)
                self.assertNotIn(b'ResourceWarning', stderr)
                deadline = time.monotonic() + 5
                while root.parent.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(root.parent.exists(), 'unapproved plaintext copy survives killed capture owner')
                self.assertEqual(list(private.iterdir()), [])
                self.assertEqual((project / 'Editor.log').read_text(), 'unapproved synthetic crash evidence\n')
                if sys.platform == 'linux':
                    import select
                    self.assertTrue(select.select([keeper_handle], [], [], 5)[0], 'keeper process did not exit')
                else:
                    self.assertEqual(kernel.WaitForSingleObject(keeper_handle, 5000), 0, 'keeper process did not exit')
                print('LIFETIME_CLEANUP=' + json.dumps({'process_pinned_by':'pidfd' if sys.platform=='linux' else 'HANDLE',
                    'keeper_exited':True,'snapshot_root_absent':True}),flush=True)
            finally:
                if keeper_handle is not None:
                    if sys.platform == 'linux': os.close(keeper_handle)
                    elif keeper_handle: kernel.CloseHandle(keeper_handle)
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=15)
                reader.join(timeout=5)
                self.assertFalse(reader.is_alive())
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe is not None:
                        pipe.close()
        self.assertFalse(Path(temp).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
