"""Local review-file reads. Synthetic fixtures, not real reviewer/Unity approval."""
import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'diagnostics'))
import snapshot


class ReviewFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vragent-review-file-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_RI001_tighter_limit_is_enforced_before_read_without_widening_default(self):
        self.assertIn('limit', inspect.signature(snapshot.read_selected).parameters,
                      'shared locked reader has no per-call smaller bound')
        (self.root / 'review.json').write_bytes(b'12345')
        self.assertEqual(snapshot.read_selected(self.root, 'review.json', limit=5), b'12345')
        with patch.object(snapshot.os, 'fdopen', side_effect=AssertionError('oversize read started')):
            with self.assertRaisesRegex(ValueError, 'limit'):
                snapshot.read_selected(self.root, 'review.json', limit=4)
        for limit in (0, -1, True, 1.5, 1024 * 1024 + 1):
            with self.subTest(limit=limit), patch.object(snapshot.os, 'open', side_effect=AssertionError('bad limit opened file')):
                with self.assertRaises(ValueError):
                    snapshot.read_selected(self.root, 'review.json', limit=limit)
        self.assertEqual(snapshot.read_selected(self.root, 'review.json'), b'12345')

    def test_RI002_private_helper_returns_exact_bytes_without_authority_or_disk_copy(self):
        import json
        import subprocess
        helper = ROOT / 'diagnostics/asset_review.py'
        self.assertTrue(helper.is_file(), 'local review-file capture helper missing')
        payload = '{"reviewer":"合成审核者", "marker":"not an approval"}'.encode('utf-8')
        (self.root / 'review.json').write_bytes(payload)
        before = sorted(x.name for x in self.root.iterdir())
        request = json.dumps({'root': str(self.root), 'name': 'review.json'}).encode('utf-8')
        proc = subprocess.run([sys.executable, '-I', '-B', str(helper)], input=request,
                              capture_output=True, timeout=10, cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, payload)
        self.assertEqual(proc.stderr, b'')
        self.assertEqual(sorted(x.name for x in self.root.iterdir()), before)
        self.assertEqual((self.root / 'review.json').read_bytes(), payload)


    def test_RI003_selected_file_failures_emit_no_contents_or_paths(self):
        import json
        import os
        import subprocess
        helper = ROOT / 'diagnostics/asset_review.py'
        good = b'{"fixture_only":"not real review"}'
        (self.root / 'review.json').write_bytes(good)
        (self.root / 'link.json').symlink_to(self.root / 'review.json')
        os.link(self.root / 'review.json', self.root / 'hard.json')
        (self.root / 'oversize.json').write_bytes(b'a' * 262145)
        (self.root / 'bad-encoding.json').write_bytes(b'\xff')
        (self.root / 'bom.json').write_bytes(b'\xef\xbb\xbf{}')
        (self.root / 'empty.json').write_bytes(b'')
        os.mkfifo(self.root / 'pipe.json')
        cases = [dict(root=str(self.root), name=n) for n in
                 ('link.json', 'hard.json', '../review.json', 'missing.json',
                  'oversize.json', 'bad-encoding.json', 'bom.json', 'empty.json',
                  'pipe.json', 'anything.cs')]
        cases += [{'root': str(self.root), 'name': 'review.json', 'approve': True},
                  {'root': None, 'name': 'review.json'}, ['invalid']]
        requests = [json.dumps(x).encode() for x in cases]
        requests += [b'{"root":"first","root":"second","name":"review.json"}',
                     b'{}' * 5000, b'\xff']
        for request in requests:
            with self.subTest(request_length=len(request)):
                proc = subprocess.run([sys.executable, '-I', '-B', str(helper)], input=request,
                                      capture_output=True, timeout=5)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, b'')
                self.assertEqual(proc.stderr, b'local_review_file_refused\n')
        (self.root / 'hard.json').unlink()
        import asset_review
        self.assertEqual(asset_review.read_local_record(str(self.root), 'review.json'), good)

    def test_RI004_replacement_and_busy_writer_fail_closed_on_real_linux_reader(self):
        import asset_review
        import os
        payload = b'{"fixture_only":true}'
        (self.root / 'review.json').write_bytes(payload)
        self.assertEqual(asset_review.read_local_record(str(self.root), 'review.json'), payload)
        with (self.root / 'review.json').open('r+b'):
            with self.assertRaises(OSError):
                asset_review.read_local_record(str(self.root), 'review.json')
        opened = snapshot.os.fdopen
        def replaced(fd, *args, **kwargs):
            stream = opened(fd, *args, **kwargs)
            (self.root / 'review.json').rename(self.root / 'previous.json')
            (self.root / 'review.json').write_bytes(payload)
            return stream
        with patch.object(snapshot.os, 'fdopen', side_effect=replaced):
            with self.assertRaisesRegex(ValueError, 'replaced|changed'):
                asset_review.read_local_record(str(self.root), 'review.json')
        self.assertEqual(asset_review.read_local_record(str(self.root), 'review.json'), payload)
        (self.root / 'nested').mkdir()
        (self.root / 'nested/review.json').write_bytes(payload)
        def ancestor_replaced(fd, *args, **kwargs):
            stream = opened(fd, *args, **kwargs)
            (self.root / 'nested').rename(self.root / 'old-nested')
            (self.root / 'nested').mkdir()
            (self.root / 'nested/review.json').write_bytes(payload)
            return stream
        with patch.object(snapshot.os, 'fdopen', side_effect=ancestor_replaced):
            with self.assertRaisesRegex(ValueError, 'ancestor'):
                asset_review.read_local_record(str(self.root), 'nested/review.json')

    def test_RI006_owned_helper_pins_exact_parent_and_retains_private_capture(self):
        import json
        import os
        import subprocess
        helper = ROOT / 'diagnostics/asset_review.py'
        payload = b'{"fixture":"owned, not reviewed"}'
        (self.root / 'review.json').write_bytes(payload)
        request = json.dumps({'root': str(self.root), 'name': 'review.json'}).encode()
        argv = [sys.executable, '-I', '-B', str(helper), '--owned-parent', str(os.getpid())]
        result = subprocess.run(argv, input=request, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, 'owned capture entry missing or rejected')
        self.assertEqual(result.stdout, payload)
        self.assertEqual(result.stderr, b'')
        for parent in ('1', 'not-pid', str(os.getppid())):
            refused = subprocess.run(argv[:-1]+[parent], input=request, capture_output=True, timeout=5)
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(refused.stdout, b'')
            self.assertEqual(refused.stderr, b'local_review_file_refused\n')

    def test_RI007_owned_helper_exits_at_deadline_with_unfinished_private_request(self):
        import os
        import subprocess
        helper = ROOT / 'diagnostics/asset_review.py'
        proc = subprocess.Popen([sys.executable, '-I', '-B', str(helper), '--owned-parent', str(os.getpid())],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write(b'{'); proc.stdin.flush()
            try:
                proc.wait(timeout=12)
            except subprocess.TimeoutExpired:
                self.fail('owned capture has no finite lifetime while input is unfinished')
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout.read(), b'')
        finally:
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=5)

    def test_RI008_owned_helper_exits_when_held_parent_dies_even_with_open_input(self):
        import ctypes
        import os
        import select
        import signal
        import subprocess
        import time
        libc = ctypes.CDLL(None, use_errno=True)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        readfd, writefd = os.pipe()
        script = "import os,subprocess,sys; p=subprocess.Popen([sys.executable,'-I','-B',sys.argv[1],'--owned-parent',str(os.getpid())],stdin=int(sys.argv[2])); print(p.pid,flush=True); sys.stdin.read()"
        parent = subprocess.Popen([sys.executable, '-I', '-B', '-c', script,
                                   str(ROOT/'diagnostics/asset_review.py'), str(readfd)],
                                  pass_fds=(readfd,), stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.close(readfd)
        child = pin = None
        try:
            assert parent.stdout is not None
            self.assertTrue(select.select([parent.stdout], [], [], 3)[0], 'child identity not returned')
            child = int(parent.stdout.readline())
            pin = os.pidfd_open(child)
            # Wait for the real lifetime watcher, not a blind scheduling sleep.
            limit = time.monotonic()+3
            while time.monotonic()<limit:
                if len(list(Path(f'/proc/{child}/task').iterdir())) >= 2:
                    break
                time.sleep(.01)
            self.assertGreaterEqual(len(list(Path(f'/proc/{child}/task').iterdir())), 2)
            parent.kill(); parent.wait(timeout=3)
            self.assertTrue(select.select([pin], [], [], 3)[0],
                            'capture survived its exact parent while inherited input remained open')
            pid, status = os.waitpid(child, 0)
            self.assertEqual(pid, child)
            self.assertEqual(os.waitstatus_to_exitcode(status), 2)
            self.assertFalse(Path(f'/proc/{child}').exists())
        finally:
            if parent.poll() is None: parent.kill()
            if pin is not None:
                assert child is not None
                if not select.select([pin], [], [], 0)[0]:
                    signal.pidfd_send_signal(pin, signal.SIGKILL)
                try: os.waitpid(child, 0)
                except ChildProcessError: pass
                os.close(pin)
            os.close(writefd)
            parent.communicate(timeout=5)

    def test_RI005_windows_route_passes_tighter_limit_and_retains_handle_guards(self):
        # Real route + existing Win32 adapter with explicit API double, NOT kernel acceptance.
        import asset_review
        import windows_handles
        sys.path.insert(0, str(ROOT / 'tests'))
        from test_diagnostics_windows import HandleAPI
        raw_reader = windows_handles.read_selected
        api = HandleAPI()
        seen = []
        def read(root, components, limit):
            seen.append(limit)
            return raw_reader(root, components, limit, api=api)
        with patch.object(snapshot.sys, 'platform', 'win32'), patch.object(windows_handles, 'read_selected', side_effect=read):
            self.assertEqual(asset_review.read_local_record('C:\\fixture', 'review.json'), b'fixture')
        self.assertEqual(seen, [262144])
        self.assertEqual(api.closed, [path for path, _ in reversed(api.opened)])
        self.assertEqual(len(api.read_handles), 1)
        api = HandleAPI()
        original_info = api.info
        def oversized(handle):
            info = list(original_info(handle))
            if handle.endswith('.json'):
                info[2] = 262145
            return tuple(info)
        api.info = oversized
        with patch.object(snapshot.sys, 'platform', 'win32'), patch.object(windows_handles, 'read_selected', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'limit'):
                asset_review.read_local_record('C:\\fixture', 'review.json')
        self.assertEqual(api.read_handles, [])
        self.assertEqual(api.closed, [path for path, _ in reversed(api.opened)])


if __name__ == '__main__':
    unittest.main()
