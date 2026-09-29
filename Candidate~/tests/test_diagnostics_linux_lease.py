"""Real Linux kernel lease checks, synthetic files only."""
import mmap
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE/'diagnostics'))
import snapshot


@unittest.skipUnless(sys.platform == 'linux', 'real Linux kernel required')
class LinuxLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='diagnostics-lease-')
        self.root = Path(self.temp.name)
        self.file = self.root/'code.cs'
        self.file.write_bytes(b'// synthetic code\n')
        self.before_fds = set(os.listdir('/proc/self/fd'))
        self.handler = signal.getsignal(signal.SIGIO)
        self.mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.assertEqual(signal.getsignal(signal.SIGIO), self.handler)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, []), self.mask)
        self.assertEqual(set(os.listdir('/proc/self/fd')), self.before_fds)
        self.temp.cleanup()
        self.assertFalse(self.root.exists())

    def test_DL001_preexisting_writer_denied_not_stat_accepted(self):
        self.assertEqual(snapshot.read_selected(self.root, 'code.cs'), b'// synthetic code\n')
        with self.file.open('r+b'):
            with self.assertRaises((ValueError, OSError)):
                snapshot.read_selected(self.root, 'code.cs')
        self.assertEqual(snapshot.read_selected(self.root, 'code.cs'), b'// synthetic code\n')


    def test_DL002_writable_mmap_outlives_fd_and_is_denied(self):
        with self.file.open('r+b') as stream:
            mapped = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_WRITE)
        try:
            with self.assertRaises((ValueError, OSError)):
                snapshot.read_selected(self.root, 'code.cs')
        finally:
            mapped.close()
        self.assertEqual(snapshot.read_selected(self.root, 'code.cs'), self.file.read_bytes())

    def test_DL003_external_writer_break_denies_capture_and_releases(self):
        import subprocess
        opened = os.fdopen
        processes = []
        def attempted(fd, *args, **kwargs):
            stream = opened(fd, *args, **kwargs)
            try:
                proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c',
                    "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'// concurrent edit')",
                    str(self.file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                processes.append(proc)
                stdout, stderr = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, stderr)
                self.assertEqual(stdout, b'')
                return stream
            except BaseException:
                stream.close()
                raise
        try:
            with patch.object(snapshot.os, 'fdopen', side_effect=attempted):
                with self.assertRaises((ValueError, OSError)):
                    snapshot.read_selected(self.root, 'code.cs')
        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3)
                if proc.stdout: proc.stdout.close()
                if proc.stderr: proc.stderr.close()
                self.assertFalse(Path('/proc', str(proc.pid)).exists())
        self.assertEqual(len(processes), 1)
        self.assertEqual(snapshot.read_selected(self.root, 'code.cs'), b'// concurrent edit')

    def test_DL004_host_signal_policy_and_worker_thread_not_overridden(self):
        handler = lambda signum, frame: None
        signal.signal(signal.SIGIO, handler)
        try:
            with self.assertRaises(OSError):
                snapshot.read_selected(self.root, 'code.cs')
            self.assertIs(signal.getsignal(signal.SIGIO), handler)
        finally:
            signal.signal(signal.SIGIO, self.handler)
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGIO})
        try:
            with self.assertRaises(OSError):
                snapshot.read_selected(self.root, 'code.cs')
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        errors = []
        def worker():
            try: snapshot.read_selected(self.root, 'code.cs')
            except OSError: errors.append(True)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [True])

    def test_DL005_unavailable_lease_does_not_fall_back_to_stats(self):
        import fcntl
        import errno
        real = fcntl.fcntl
        def unavailable(fd, command, arg=0):
            if command == fcntl.F_SETLEASE and arg == fcntl.F_RDLCK:
                raise OSError(errno.EOPNOTSUPP, 'synthetic unavailable lease')
            return real(fd, command, arg)
        with patch.object(fcntl, 'fcntl', side_effect=unavailable):
            with self.assertRaises(OSError):
                snapshot.read_selected(self.root, 'code.cs')
        self.assertEqual(snapshot.read_selected(self.root, 'code.cs'), self.file.read_bytes())

    def test_DL006_thirty_same_length_edits_never_escape(self):
        opened = os.fdopen
        for _ in range(30):
            self.file.write_bytes(b'// synthetic code\n')
            def changed(fd, *args, **kwargs):
                stream = opened(fd, *args, **kwargs)
                self.file.write_bytes(b'// concurrent edit')
                return stream
            with patch.object(snapshot.os, 'fdopen', side_effect=changed):
                with self.assertRaises((ValueError, OSError)):
                    snapshot.read_selected(self.root, 'code.cs')
        self.assertEqual(snapshot.read_selected(self.root, 'code.cs'), b'// concurrent edit')


if __name__ == '__main__':
    unittest.main(verbosity=2)
