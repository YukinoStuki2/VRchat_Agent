"""DL-R1: expiry cleanup retains a bounded owner after reader sharing locks."""
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
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
if len(sys.argv) > 2 and sys.argv[1] == '--runtime-root':
    BASE = Path(sys.argv[2]).resolve(strict=True)
    del sys.argv[1:3]
sys.path.insert(0, str(BASE / 'diagnostics'))
import lifetime


class LifetimeRetryTests(unittest.TestCase):
    def _keeper(self, private, injection=''):
        code = ('import sys;sys.path.insert(0,' + repr(str(BASE / 'diagnostics')) + ')\n'
                'import lifetime, tempfile, time\n'
                'lifetime.TTL=0.3\n' + injection + '\n'
                'raise SystemExit(lifetime._worker())\n')
        process = subprocess.Popen([getattr(sys, '_base_executable', sys.executable),
            '-I', '-B', '-W', 'always::ResourceWarning', '-c', code],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ready = queue.Queue()
        reader = threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True)
        reader.start()
        def finish():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
            reader.join(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()
            self.assertFalse(reader.is_alive())
        self.addCleanup(finish)
        process.stdin.write(json.dumps({'temp_parent': str(private)}).encode() + b'\n')
        process.stdin.flush()
        line = ready.get(timeout=10)
        self.assertTrue(line, 'keeper did not publish readiness')
        record = json.loads(line)
        return process, Path(record['root']), record['deadline']

    def test_DL_R1_transient_lock_retries_while_host_pipe_open(self):
        # Fault injection occurs only in the child fixture, never product config.
        injection = '''
original = tempfile.TemporaryDirectory._rmtree
attempts = 0
def locked_once(path, *args, **kwargs):
    global attempts
    attempts += 1
    if attempts == 1:
        raise PermissionError('synthetic reader sharing lock')
    return original(path, *args, **kwargs)
tempfile.TemporaryDirectory._rmtree = locked_once
'''
        with tempfile.TemporaryDirectory(prefix='lifetime-retry-fixture-') as temp:
            private = Path(temp).resolve()
            process, root, deadline = self._keeper(private, injection)
            (root / 'copy.txt').write_text('synthetic unapproved copy')
            process.stdin.write(b'R'); process.stdin.flush()
            # wait() deliberately leaves stdin open: EOF cannot rescue cleanup.
            process.wait(timeout=8)
            self.assertFalse(process.stdin.closed)
            self.assertFalse(root.exists(), 'keeper abandoned copy after transient sharing lock')
            self.assertEqual(list(private.iterdir()), [])
            self.assertEqual(process.returncode, 0, process.stderr.read().decode())
        self.assertFalse(Path(temp).exists())

    def test_DL_R1_permanent_lock_has_bounded_failure(self):
        injection = '''
lifetime.CLEANUP_RETRY_SECONDS = 0.2
def locked(path, *args, **kwargs):
    raise PermissionError('synthetic permanent sharing lock')
tempfile.TemporaryDirectory._rmtree = locked
'''
        with tempfile.TemporaryDirectory(prefix='lifetime-retry-budget-') as temp:
            process, root, deadline = self._keeper(Path(temp).resolve(), injection)
            process.stdin.write(b'R'); process.stdin.flush()
            process.wait(timeout=3)
            self.assertFalse(process.stdin.closed)
            self.assertTrue(root.exists())
            self.assertNotEqual(process.returncode, 0)
            error = process.stderr.read()
            self.assertIn(b'snapshot_guard_cleanup_failed', error)
            self.assertNotIn(b'ResourceWarning', error)
        self.assertFalse(Path(temp).exists())

    def test_DL_R1_retry_rejects_replaced_directory_and_parent(self):
        for replace_parent in (False, True):
            with self.subTest(parent=replace_parent), tempfile.TemporaryDirectory(prefix='lifetime-retry-replace-') as temp:
                home = Path(temp).resolve(); parent = home / 'parent'; parent.mkdir()
                root = parent / 'root'; root.mkdir()
                record = ([(root, lifetime._stamp(root))],
                          [(p, lifetime._stamp(p)) for p in root.parents])
                attempts = []
                def replace(path, *args, **kwargs):
                    attempts.append(path)
                    victim = parent if replace_parent else root
                    victim.rename(home / 'moved')
                    victim.mkdir()
                    if replace_parent:
                        root.mkdir()
                    (root / 'foreign.txt').write_text('must survive')
                    raise PermissionError('sharing lock then substitution')
                with patch.object(tempfile.TemporaryDirectory, '_rmtree', side_effect=replace):
                    with self.assertRaisesRegex(ValueError, 'guard_directory_replaced'):
                        lifetime._cleanup_owned(record)
                self.assertEqual(len(attempts), 1)
                self.assertEqual((root / 'foreign.txt').read_text(), 'must survive')

    def test_DL_R1_retry_rejects_linked_parent(self):
        with tempfile.TemporaryDirectory(prefix='lifetime-retry-link-') as temp:
            home = Path(temp).resolve(); parent = home / 'parent'; parent.mkdir()
            root = parent / 'root'; root.mkdir()
            outside = home / 'outside'; outside.mkdir()
            (outside / 'root').mkdir()
            sentinel = outside / 'root/foreign.txt'; sentinel.write_text('must survive')
            record = ([(root, lifetime._stamp(root))],
                      [(p, lifetime._stamp(p)) for p in root.parents])
            def replace(path, *args, **kwargs):
                parent.rename(home / 'moved')
                if os.name == 'nt':
                    subprocess.run(['cmd', '/c', 'mklink', '/J', str(parent), str(outside)],
                                   check=True, capture_output=True)
                else:
                    parent.symlink_to(outside, target_is_directory=True)
                raise PermissionError('sharing lock then parent link')
            try:
                with patch.object(tempfile.TemporaryDirectory, '_rmtree', side_effect=replace):
                    with self.assertRaisesRegex(ValueError, 'guard_directory_invalid'):
                        lifetime._cleanup_owned(record)
                self.assertEqual(sentinel.read_text(), 'must survive')
            finally:
                if parent.is_symlink():
                    parent.unlink()
                elif os.name == 'nt' and parent.exists():
                    parent.rmdir()  # Remove our junction, never its target.

    def test_DL_R1_outer_retry_after_root_already_deleted(self):
        with tempfile.TemporaryDirectory(prefix='lifetime-retry-outer-') as temp:
            home = Path(temp).resolve(); outer = home / 'acl'; outer.mkdir()
            root = outer / 'capture'; root.mkdir()
            (root / 'copy.txt').write_text('synthetic')
            record = ([(p, lifetime._stamp(p)) for p in (root, outer)],
                      [(p, lifetime._stamp(p)) for p in outer.parents])
            real_rmdir = Path.rmdir
            blocked = []
            def locked_once(path):
                if path == outer and not blocked:
                    self.assertFalse(root.exists())
                    blocked.append(True)
                    raise PermissionError('outer reader HANDLE')
                return real_rmdir(path)
            with patch.object(Path, 'rmdir', locked_once):
                lifetime._cleanup_owned(record)
            self.assertEqual(blocked, [True])
            self.assertFalse(outer.exists())
            lifetime._cleanup_owned(record)  # Both targets already absent.

    @unittest.skipUnless(sys.platform == 'win32', 'Windows kernel sharing HANDLEs required')
    def test_DL_R1_windows_reader_handles_cross_deadline(self):
        import windows_handles
        entered = threading.Event(); release = threading.Event(); result = []
        class Reader(windows_handles.Win32):
            def read(self, handle, limit):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('fixture reader not released')
                return super().read(handle, limit)
        with tempfile.TemporaryDirectory(prefix='lifetime-retry-win-reader-') as temp:
            private = Path(temp).resolve()
            process, root, deadline = self._keeper(private)
            (root / 'copy.txt').write_bytes(b'synthetic unapproved copy')
            def read():
                try:
                    result.append(windows_handles.read_selected(str(root), ['copy.txt'], 1024, api=Reader()))
                except Exception as error:
                    result.append(error)
            reader = threading.Thread(target=read)
            reader.start()
            try:
                self.assertTrue(entered.wait(3), repr(result))
                process.stdin.write(b'R'); process.stdin.flush()
                time.sleep(max(0, deadline - time.monotonic()) + 0.15)
                self.assertTrue(root.exists())
                self.assertIsNone(process.poll(), 'keeper abandoned locked snapshot')
            finally:
                release.set(); reader.join(timeout=5)
            self.assertFalse(reader.is_alive())
            self.assertEqual(result, [b'synthetic unapproved copy'])
            process.wait(timeout=7)
            self.assertFalse(process.stdin.closed)
            self.assertEqual(process.returncode, 0, process.stderr.read().decode())
            self.assertEqual(list(private.iterdir()), [])
        self.assertFalse(Path(temp).exists())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows kernel sharing HANDLEs required')
    def test_DL_R1_windows_outer_handle_cross_deadline(self):
        from windows_handles import Win32
        with tempfile.TemporaryDirectory(prefix='lifetime-retry-win-outer-') as temp:
            private = Path(temp).resolve()
            process, root, deadline = self._keeper(private)
            (root / 'copy.txt').write_bytes(b'synthetic')
            api = Win32(); handle = api.open(str(root.parent), directory=True)
            try:
                process.stdin.write(b'R'); process.stdin.flush()
                time.sleep(max(0, deadline - time.monotonic()) + 0.15)
                self.assertFalse(root.exists(), 'inner root should be deletable')
                self.assertTrue(root.parent.exists())
                self.assertIsNone(process.poll(), 'keeper abandoned locked ACL container')
            finally:
                api.close(handle)
            process.wait(timeout=7)
            self.assertFalse(process.stdin.closed)
            self.assertEqual(process.returncode, 0, process.stderr.read().decode())
            self.assertEqual(list(private.iterdir()), [])
        self.assertFalse(Path(temp).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
