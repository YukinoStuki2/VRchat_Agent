"""Portable Win32 adapter contract probes, NOT Windows kernel evidence."""
import importlib
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'diagnostics'))


class HandleAPI:
    """Linux cannot invoke Win32: deterministic ABI seam, no kernel claims."""
    def __init__(self):
        self.opened = []
        self.closed = []
        self.read_handles = []

    def local_drive(self, drive):
        return True

    def open(self, path, *, directory):
        self.opened.append((path, directory))
        return path

    def close(self, handle):
        self.closed.append(handle)

    def info(self, handle):
        directory = next(d for p, d in self.opened if p == handle)
        return (0x10 if directory else 0, 1, 0 if directory else 7, 11, hash(handle), 13, 17)

    def final_path(self, handle):
        return '\\\\?\\' + handle

    def disk(self, handle):
        return True

    def read(self, handle, limit):
        self.read_handles.append(handle)
        if len(self.closed):
            raise AssertionError('ancestor handles released before read')
        return b'fixture'


class WindowsBoundaryTests(unittest.TestCase):
    def module(self):
        self.assertTrue((BASE / 'diagnostics/windows_handles.py').is_file(),
                        'Win32 locked handle reader missing')
        return importlib.import_module('windows_handles')

    def test_DW001_reads_same_handle_with_all_ancestors_pinned(self):
        api = HandleAPI()
        data = self.module().read_selected('C:\\fixture', ['Editor', 'Test.cs'], 1024, api=api)
        paths = ['C:\\', 'C:\\fixture', 'C:\\fixture\\Editor', 'C:\\fixture\\Editor\\Test.cs']
        self.assertEqual(data, b'fixture')
        self.assertEqual(api.opened, [(p, i < 3) for i, p in enumerate(paths)])
        self.assertEqual(api.read_handles, [paths[-1]])
        self.assertEqual(api.closed, list(reversed(paths)))

    def test_DW002_reparse_hardlink_alias_and_changed_handle_denied(self):
        module = self.module()
        for defect in ('reparse-ancestor', 'reparse-file', 'hardlink', 'alias',
                       'nondisk', 'directory-file', 'oversize', 'changed', 'grew'):
            with self.subTest(defect=defect):
                api = HandleAPI()
                original_info = api.info
                def info(h):
                    result = list(original_info(h))
                    leaf = h.endswith('Test.cs')
                    if defect == 'reparse-ancestor' and h == 'C:\\fixture':
                        result[0] |= 0x400
                    if defect == 'reparse-file' and leaf:
                        result[0] |= 0x400
                    if defect == 'hardlink' and leaf:
                        result[1] = 2
                    if defect == 'directory-file' and leaf:
                        result[0] |= 0x10
                    if defect == 'oversize' and leaf:
                        result[2] = 1025
                    if defect == 'changed' and api.read_handles and leaf:
                        result[6] += 1
                    return tuple(result)
                api.info = info
                if defect == 'alias':
                    api.final_path = lambda h: '\\\\?\\C:\\elsewhere'
                if defect == 'nondisk':
                    api.disk = lambda h: False
                if defect == 'grew':
                    api.read = lambda h, n: b'x' * (n + 1)
                with self.assertRaisesRegex(ValueError, 'unsafe|changed|limit'):
                    module.read_selected('C:\\fixture', ['Editor', 'Test.cs'], 1024, api=api)
                if defect not in ('changed', 'grew'):
                    self.assertEqual(api.read_handles, [])
                self.assertEqual(api.closed, [p for p, _ in reversed(api.opened)])

    def test_DW003_alias_device_ads_and_remote_drive_rejected_before_open(self):
        module = self.module()
        cases = [(root, ['Test.cs']) for root in
                 ('relative', 'C:relative', '\\\\host\\share', '\\\\?\\C:\\fixture',
                  'C:/fixture', 'C:\\fixture\\..\\other', 'C:\\fixture.', 'C:\\\\fixture')]
        cases += [('C:\\fixture', [name]) for name in
                  ('..', '.', 'NUL.txt', 'COM1.log', 'LPT².txt', 'log.txt:ads',
                   'log.txt.', 'folder\\log.txt', 'bad\x1b.txt', 'bad?.txt')]
        for root, parts in cases:
            with self.subTest(root=root, parts=parts):
                api = HandleAPI()
                with self.assertRaises(ValueError):
                    module.read_selected(root, parts, 1024, api=api)
                self.assertEqual(api.opened, [])
        api = HandleAPI()
        api.local_drive = lambda drive: False
        with self.assertRaisesRegex(ValueError, 'local'):
            module.read_selected('Z:\\fixture', ['Test.cs'], 1024, api=api)
        self.assertEqual(api.opened, [])

    def test_DW004_native_adapter_abi_flags_bounded_read_and_close(self):
        import ctypes as c
        from types import SimpleNamespace
        module = self.module()
        self.assertTrue(hasattr(module, 'Win32'), 'native ctypes adapter missing')
        calls = []
        class Function:
            def __init__(self, fn):
                self.fn = fn
            def __call__(self, *args):
                return self.fn(*args)
        def create(*args):
            calls.append(args)
            return 71
        def read(handle, buffer, limit, count, overlapped):
            self.assertEqual(handle, 71)
            value = b'fixture' if not getattr(read, 'done', False) else b''
            read.done = True
            c.memmove(buffer, value, len(value))
            count._obj.value = len(value)
            return 1
        def information(handle, output):
            info = output._obj
            info.dwFileAttributes = 0
            info.nNumberOfLinks = 1
            info.nFileSizeLow = 7
            info.dwVolumeSerialNumber = 11
            info.nFileIndexLow = 12
            info.ftLastWriteTime.dwLowDateTime = 13
            return 1
        def basic(handle, kind, output, size):
            output._obj.ChangeTime = 17
            return 1
        final = '\\\\?\\C:\\fixture\\Test.cs'
        def final_path(handle, buffer, length, flags):
            if length:
                buffer.value = final
                return len(final)
            return len(final) + 1
        lib = SimpleNamespace(**{name: Function(fn) for name, fn in {
            'CreateFileW': create, 'CloseHandle': lambda h: calls.append(('close', h)) or 1,
            'GetFileType': lambda h: 1, 'GetDriveTypeW': lambda d: 3,
            'GetFileInformationByHandle': information,
            'GetFileInformationByHandleEx': basic, 'ReadFile': read,
            'GetFinalPathNameByHandleW': final_path}.items()})
        api = module.Win32(library=lib)
        for directory in (True, False):
            handle = api.open('C:\\fixture', directory=directory)
            args = calls[-1]
            self.assertEqual(args[0], '\\\\?\\C:\\fixture')
            self.assertEqual(args[1], 0x80 if directory else 0x80000000)
            self.assertEqual(args[2], 1, 'must deny SHARE_WRITE and SHARE_DELETE')
            self.assertEqual(args[4], 3, 'OPEN_EXISTING only')
            self.assertEqual(args[5], 0x02200000, 'OPEN_REPARSE_POINT and BACKUP_SEMANTICS')
            self.assertEqual(handle, 71)
        self.assertTrue(api.local_drive('C:\\'))
        self.assertTrue(api.disk(71))
        self.assertEqual(api.info(71), (0, 1, 7, 11, 12, 13, 17))
        self.assertEqual(api.final_path(71), final)
        self.assertEqual(api.read(71, 8), b'fixture')
        api.close(71)
        self.assertEqual(calls[-1], ('close', 71))
        self.assertEqual(c.sizeof(module.FileInfo), 52)
        self.assertEqual(c.sizeof(module.BasicInfo), 40)
        lib.CreateFileW.fn = lambda *args: c.c_void_p(-1).value
        with self.assertRaises(OSError):
            api.open('C:\\fixture', directory=False)

    def test_DW005_snapshot_routes_windows_through_handle_reader(self):
        from unittest.mock import patch
        import snapshot
        module = self.module()
        api = HandleAPI()
        with patch.object(snapshot.sys, 'platform', 'win32'), patch.object(module, 'Win32', return_value=api):
            self.assertEqual(snapshot.read_selected('C:\\fixture', 'Editor/Test.cs'), b'fixture')
        self.assertEqual(api.read_handles, ['C:\\fixture\\Editor\\Test.cs'])
        self.assertEqual(api.closed, [p for p, _ in reversed(api.opened)])

    def test_DW006_windows_selection_cannot_overwrite_case_alias(self):
        from unittest.mock import patch
        import snapshot
        import tempfile
        api = HandleAPI()
        api.read = lambda handle, limit: b'fixture'
        with tempfile.TemporaryDirectory(prefix='dw-selection-') as temp:
            with patch.object(snapshot.sys, 'platform', 'win32'), patch.object(self.module(), 'Win32', return_value=api):
                with self.assertRaisesRegex(ValueError, 'duplicate'):
                    with snapshot.capture('C:\\fixture', ['A.log', 'a.log'], task_id='fixture', temp_parent=temp):
                        self.fail('case alias accepted')
            self.assertEqual(list(Path(temp).iterdir()), [])
            self.assertEqual(api.opened, [])

    def test_DW007_private_directory_is_created_with_protected_acl(self):
        import ctypes as c
        from types import SimpleNamespace
        module = self.module()
        self.assertTrue(hasattr(module, 'create_private_directory'), 'Windows private ACL creation missing')
        events = []
        class Function:
            def __init__(self, fn):
                self.fn = fn
            def __call__(self, *args):
                return self.fn(*args)
        def descriptor(sddl, revision, out, size):
            events.append(('sddl', sddl, revision))
            out._obj.value = 55
            return 1
        def mkdir(path, attrs):
            events.append(('create', path, attrs._obj.lpSecurityDescriptor, attrs._obj.bInheritHandle))
            return 1
        security = SimpleNamespace(ConvertStringSecurityDescriptorToSecurityDescriptorW=Function(descriptor))
        kernel = SimpleNamespace(CreateDirectoryW=Function(mkdir), LocalFree=Function(lambda p: events.append(('free', p.value)) or None))
        module.create_private_directory('C:\\fixture', kernel=kernel, security=security)
        self.assertEqual(events, [('sddl', 'D:P(A;OICI;FA;;;OW)(A;OICI;FA;;;SY)', 1),
                                  ('create', 'C:\\fixture', 55, 0), ('free', 55)])
        kernel.CreateDirectoryW.fn = lambda *args: 0
        with self.assertRaises(OSError):
            module.create_private_directory('C:\\fixture', kernel=kernel, security=security)
        self.assertEqual(events[-1], ('free', 55), 'descriptor leaked on failure')

    def test_DW008_capture_uses_private_acl_container_and_cleans_on_failure(self):
        from unittest.mock import patch
        import snapshot
        import tempfile
        from contextlib import contextmanager
        import lifetime
        import time
        # HANDLE/ACL routing double only; real guarded_container launches a
        # separate platform-matched keeper, which cannot be mocked via sys.platform.
        @contextmanager
        def in_process_keeper(parent):
            with snapshot.private_container(parent) as private:
                yield private, time.monotonic() + 300, lambda: True, lambda: None
        made = []
        def mkdir(path):
            made.append(Path(path))
            Path(path).mkdir(mode=0o700)
        with tempfile.TemporaryDirectory(prefix='dw-private-') as temp:
            with patch.object(snapshot.sys, 'platform', 'win32'), patch.object(lifetime, 'guarded_container', side_effect=in_process_keeper), patch.object(self.module(), 'create_private_directory', side_effect=mkdir), patch.object(self.module(), 'Win32', side_effect=HandleAPI):
                with snapshot.capture('C:\\fixture', ['Test.cs'], task_id='fixture', temp_parent=temp) as snap:
                    self.assertEqual(len(made), 1, 'no explicit Windows private ACL container')
                    self.assertTrue(snap.root.is_relative_to(made[0]))
                    self.assertEqual((snap.root / 'Test.cs').read_bytes(), b'fixture')
                self.assertFalse(made[0].exists())
                with self.assertRaisesRegex(RuntimeError, 'fixture-failure'):
                    with snapshot.capture('C:\\fixture', ['Test.cs'], task_id='fixture', temp_parent=temp):
                        raise RuntimeError('fixture-failure')
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_DW009_windows_backend_uses_native_node_not_posix_shell(self):
        from unittest.mock import patch
        import server
        import tempfile
        self.assertTrue(hasattr(server, 'backend_transport'), 'Windows stdio launcher missing')
        with tempfile.TemporaryDirectory(prefix='dw-transport-') as temp:
            root = Path(temp) / 'snapshot'
            root.mkdir()
            with patch.object(server.sys, 'platform', 'win32'), patch.object(server, 'bundled_node', return_value=Path('C:\\nodejs\\node.exe')):
                transport = server.backend_transport(root)
            self.assertEqual(transport.command, 'C:\\nodejs\\node.exe')
            self.assertEqual(transport.args, [str(server.ENTRY), str(root)])
            self.assertEqual(transport.env['TEMP'], str(root.parent))
            self.assertNotIn('NODE_OPTIONS', transport.env)
            self.assertFalse(transport.keep_alive)

    @unittest.skipIf(sys.platform == 'win32', 'Linux must not fabricate kernel success')
    def test_DW010_windows_runner_emits_explicit_unverified_json_off_windows(self):
        import json
        import subprocess
        import tempfile
        script = BASE / 'diagnostics/verify_windows.py'
        self.assertTrue(script.exists(), 'Windows CI JSON runner missing')
        with tempfile.TemporaryDirectory(prefix='dw-runner-') as home:
            output = Path(home) / 'result.json'
            result = subprocess.run([sys.executable, '-B', str(script), '--output', str(output)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 2, result.stderr)
            report = json.loads(output.read_text())
            self.assertFalse(report['windows_kernel_executed'])
            self.assertFalse(report['passed'])
            self.assertEqual(report['passed_ids'], [])
            self.assertEqual(len(report['skipped_ids']), 7)
            self.assertEqual(report['expected_ids'], report['skipped_ids'])
            self.assertTrue(report['isolated_home_removed'])
            self.assertTrue(report['source_hashes_unchanged'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
