"""Synthetic-only snapshot acceptance checks; no real project data."""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'diagnostics'))
try:
    import snapshot
except ModuleNotFoundError:
    snapshot = None


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(prefix='diagnostics-test-')
        self.addCleanup(self.fixture.cleanup)
        self.base = Path(self.fixture.name)
        self.root = self.base / 'project'
        self.root.mkdir()
        self.temp = self.base / 'private'
        self.temp.mkdir(mode=0o700)
        (self.root / 'Editor').mkdir()
        (self.root / 'Editor/Test.cs').write_text('// synthetic code\n')
        (self.root / 'Editor.log').write_text('synthetic log\n')
        (self.root / 'unselected.txt').write_text('not selected')

    def export(self, files=('Editor/Test.cs', 'Editor.log'), **kwargs):
        self.assertIsNotNone(snapshot, 'secure local snapshot entry is not implemented')
        return snapshot.capture(self.root, files, task_id='fixture-task', temp_parent=self.temp, **kwargs)

    def test_selected_text_is_private_frozen_and_owned_cleanup(self):
        with self.export() as result:
            root = result.root
            self.assertEqual((root / 'Editor/Test.cs').read_text(), '// synthetic code\n')
            self.assertEqual((root / 'Editor.log').read_text(), 'synthetic log\n')
            self.assertFalse((root / 'unselected.txt').exists())
            self.assertEqual(stat.S_IMODE(root.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o500)
            self.assertEqual(stat.S_IMODE((root / 'Editor.log').stat().st_mode), 0o400)
            self.assertEqual((root / 'Editor.log').stat().st_nlink, 1)
            (self.root / 'Editor.log').write_text('changed original')
            self.assertEqual((root / 'Editor.log').read_text(), 'synthetic log\n')
        self.assertFalse(root.parent.exists())
        self.assertTrue(self.root.exists())
        self.assertEqual(list(self.temp.iterdir()), [])


    def test_reject_links_and_outside_paths_before_read(self):
        outside = self.base / 'outside.txt'
        outside.write_text('outside synthetic')
        (self.root / 'link.txt').symlink_to(outside)
        os.link(outside, self.root / 'hard.txt')
        for name in ('link.txt', 'hard.txt', '../outside.txt', str(outside)):
            with self.subTest(name=name):
                with self.assertRaises((ValueError, OSError)):
                    with self.export((name,)):
                        self.fail('outside/linked source was exported')
                self.assertEqual(list(self.temp.iterdir()), [])


    def test_bounds_text_and_sensitive_selection(self):
        (self.root / 'large.log').write_bytes(b'a' * (1024 * 1024 + 1))
        (self.root / '.env').write_text('TOKEN=fixture-sensitive')
        (self.root / 'binary.txt').write_bytes(b'abc\x00def')
        cases = [('large.log',), ('.env',), ('binary.txt',), (), ('Editor.log', 'Editor.log')]
        for names in cases:
            with self.subTest(names=names):
                with self.assertRaises((ValueError, OSError)):
                    with self.export(names):
                        self.fail('unsafe/unbounded selection accepted')
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_common_secret_assignments_redacted(self):
        (self.root / 'Editor.log').write_text('Authorization: Bearer fixture-abcd\napi_key=fixture-secret\nhttps://name:password@example.invalid/x?token=fixture-token\nnormal compiler error\n')
        with self.export(('Editor.log',)) as result:
            text = (result.root / 'Editor.log').read_text()
            for secret in ('fixture-abcd', 'fixture-secret', 'password', 'fixture-token'):
                self.assertNotIn(secret, text)
            self.assertIn('normal compiler error', text)
            self.assertIn('[REDACTED]', text)


    def test_changed_during_read_and_replaced_directory_are_denied(self):
        from unittest.mock import patch
        opened = os.fdopen
        for replace in (False, True):
            with self.subTest(replace=replace):
                def changed(fd, *args, **kwargs):
                    stream = opened(fd, *args, **kwargs)
                    if replace:
                        (self.root / 'Editor').rename(self.root / 'OldEditor')
                        (self.root / 'Editor').mkdir()
                        (self.root / 'Editor/Test.cs').write_text('// replacement')
                    else:
                        (self.root / 'Editor/Test.cs').write_text('// concurrent edit')
                    return stream
                with patch.object(snapshot.os, 'fdopen', side_effect=changed):
                    with self.assertRaises((ValueError, OSError)):
                        with self.export(('Editor/Test.cs',)):
                            self.fail('concurrent change accepted')
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_count_total_fifo_ancestor_symlink_and_platform_bounds(self):
        from unittest.mock import patch
        os.mkfifo(self.root / 'pipe.log')
        (self.base / 'alias').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            with self.export(('pipe.log',)):
                self.fail('FIFO accepted')
        with self.assertRaises(OSError):
            with snapshot.capture(self.base / 'alias', ('Editor.log',), task_id='fixture', temp_parent=self.temp):
                self.fail('ancestor link accepted')
        with patch.object(snapshot.sys, 'platform', 'win32'):
            with self.assertRaises(OSError):
                with self.export():
                    self.fail('untested Windows boundary accepted')
        for count, size in ((65, 1), (9, 1024 * 1024)):
            names = [f'limit-{i}.log' for i in range(count)]
            for name in names:
                (self.root / name).write_bytes(b'x' * size)
            with self.assertRaises(ValueError):
                with self.export(names):
                    self.fail('aggregate limit accepted')
        self.assertEqual(list(self.temp.iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
