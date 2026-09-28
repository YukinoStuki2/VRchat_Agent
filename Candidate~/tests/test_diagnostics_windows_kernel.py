"""Run ONLY on an actual Windows kernel, with synthetic local fixed-drive fixtures.

No emulator/ABI fake results count as passing these tests. No Unity needed.
"""
import ctypes as c
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'diagnostics'))
import snapshot
import windows_handles as windows

CLEANUP = []


@unittest.skipUnless(os.name == 'nt', 'requires actual Windows kernel; NOT VERIFIED on Linux')
class WindowsKernelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='diagnostics-kernel-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home / 'source'
        self.source.mkdir()
        (self.source / 'nested').mkdir()
        self.file = self.source / 'nested' / 'Editor.log'
        self.file.write_text('token=synthetic-secret\nfixture error 中文\n', encoding='utf-8')
        self.addCleanup(self.verify_removed)
        self.handles = set()
        opened, closed = windows.Win32.open, windows.Win32.close
        def track_open(api, *args, **kwargs):
            handle = opened(api, *args, **kwargs)
            self.handles.add(handle)
            return handle
        def track_close(api, handle):
            closed(api, handle)
            self.handles.remove(handle)
        for method, replacement in (('open', track_open), ('close', track_close)):
            instrument = patch.object(windows.Win32, method, replacement)
            instrument.start()
            self.addCleanup(instrument.stop)

    def verify_removed(self):
        self.temp.cleanup()
        self.assertFalse(self.home.exists())
        self.assertEqual(self.handles, set(), 'owned Windows HANDLEs remain open')
        CLEANUP.append({'id': self.id(), 'fixture_removed': not self.home.exists(),
                        'outstanding_handles': len(self.handles)})

    def test_WK001_real_handle_utf8_redaction_frozen_snapshot_and_cleanup(self):
        with snapshot.capture(str(self.source), ['nested/Editor.log'], task_id='kernel-fixture', temp_parent=self.home) as snap:
            text = (snap.root / 'nested/Editor.log').read_text(encoding='utf-8')
            self.assertNotIn('synthetic-secret', text)
            self.assertIn('中文', text)
            self.file.write_text('changed after capture', encoding='utf-8')
            self.assertEqual((snap.root / 'nested/Editor.log').read_text(encoding='utf-8'), text)
            owned = snap.root.parent.parent
        self.assertFalse(owned.exists())
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ['source'])

    def test_WK002_hardlink_and_junction_rejected(self):
        outside = self.home / 'outside'
        outside.mkdir()
        external = outside / 'outside.log'
        external.write_text('outside synthetic')
        hard = self.source / 'hard.log'
        os.link(external, hard)
        with self.assertRaises((ValueError, OSError)):
            snapshot.read_selected(str(self.source), 'hard.log')
        junction = self.source / 'junction'
        try:
            result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(junction), str(outside)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, 'synthetic junction creation failed')
            with self.assertRaises((ValueError, OSError)):
                snapshot.read_selected(str(self.source), 'junction/outside.log')
            with self.assertRaises((ValueError, OSError)):
                snapshot.read_selected(str(junction), 'outside.log')
        finally:
            if junction.exists():
                os.rmdir(junction)
        self.assertEqual(external.read_text(), 'outside synthetic')

    def test_WK003_ancestor_and_file_locked_through_native_read(self):
        original = windows.Win32.read
        observations = []
        def while_locked(api, handle, limit):
            for source, destination in ((self.source, self.home / 'renamed'),
                                        (self.file.parent, self.source / 'renamed-nested'),
                                        (self.file, self.source / 'renamed.log')):
                with self.assertRaises(OSError):
                    source.rename(destination)
                observations.append('rename-denied')
            with self.assertRaises(OSError):
                self.file.write_text('must not replace')
            observations.append('write-denied')
            return original(api, handle, limit)
        with patch.object(windows.Win32, 'read', while_locked):
            data = snapshot.read_selected(str(self.source), 'nested/Editor.log')
        self.assertIn(b'fixture error', data)
        self.assertEqual(len(observations), 4)
        self.file.write_text('after release')
        self.source.rename(self.home / 'released')

    def test_WK004_symlink_leaf_rejected(self):
        link = self.source / 'link.log'
        try:
            link.symlink_to(self.file)
        except OSError as error:
            if error.winerror == 1314:
                self.skipTest('Windows symlink privilege unavailable; NOT PASSED')
            raise
        try:
            with self.assertRaises((ValueError, OSError)):
                snapshot.read_selected(str(self.source), 'link.log')
        finally:
            link.unlink(missing_ok=True)

    def test_WK005_private_acl_is_protected_owner_and_system_only(self):
        adv = c.WinDLL('advapi32', use_last_error=True)
        kernel = c.WinDLL('kernel32', use_last_error=True)
        get = adv.GetNamedSecurityInfoW
        get.argtypes = [c.c_wchar_p, c.c_int32, c.c_uint32, c.c_void_p, c.c_void_p,
                        c.c_void_p, c.c_void_p, c.POINTER(c.c_void_p)]
        get.restype = c.c_uint32
        convert = adv.ConvertSecurityDescriptorToStringSecurityDescriptorW
        convert.argtypes = [c.c_void_p, c.c_uint32, c.c_uint32, c.POINTER(c.c_void_p), c.c_void_p]
        convert.restype = c.c_int32
        kernel.LocalFree.argtypes = [c.c_void_p]
        kernel.LocalFree.restype = c.c_void_p
        with snapshot.capture(str(self.source), ['nested/Editor.log'], task_id='kernel-acl', temp_parent=self.home) as snap:
            for path, protected in ((snap.root.parent.parent, True), (snap.root / 'nested/Editor.log', False)):
                descriptor, text = c.c_void_p(), c.c_void_p()
                self.assertEqual(get(str(path), 1, 4, None, None, None, None, c.byref(descriptor)), 0)
                try:
                    self.assertTrue(convert(descriptor, 1, 4, c.byref(text), None))
                    sddl = c.wstring_at(text)
                    if protected:
                        self.assertIn('D:P', sddl)
                    aces = __import__('re').findall(r'\(([^)]+)\)', sddl)
                    self.assertEqual(len(aces), 2, sddl)
                    self.assertEqual({ace.split(';')[-1] for ace in aces}, {'OW', 'SY'}, sddl)
                finally:
                    if text:
                        kernel.LocalFree(text)
                    kernel.LocalFree(descriptor)

    def test_WK006_preexisting_writer_blocks_export(self):
        with self.file.open('a', encoding='utf-8') as writer:
            writer.write('writer open')
            writer.flush()
            with self.assertRaises(OSError):
                snapshot.read_selected(str(self.source), 'nested/Editor.log')

    def test_WK007_cross_root_device_ads_and_alias_refused(self):
        outside = self.home / 'outside.log'
        outside.write_text('unselected synthetic outside')
        for root, name in ((str(self.source), '../outside.log'),
                           (str(self.source), str(outside)),
                           (str(self.source), 'nested/Editor.log:stream'),
                           (str(self.source), 'NUL.log'),
                           (str(self.source) + '\\..\\source', 'nested/Editor.log'),
                           ('\\\\localhost\\C$', 'outside.log'),
                           ('\\\\?\\' + str(self.source), 'nested/Editor.log')):
            with self.subTest(root=root, name=name):
                with self.assertRaises((ValueError, OSError)):
                    snapshot.read_selected(root, name)
        self.assertEqual(outside.read_text(), 'unselected synthetic outside')


if __name__ == '__main__':
    unittest.main(verbosity=2)
