"""CI driver boundaries only; not runtime or Windows kernel acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def driver():
    spec = importlib.util.spec_from_file_location('portable_verifier', ROOT/'tests/verify_portable.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableVerifierTests(unittest.TestCase):
    def test_VP001_nuget_system_paths_are_build_only(self):
        m = driver()
        self.assertTrue(hasattr(m, 'compile_environment'), 'NuGet environment helper missing')
        runtime = {'HOME': '/owned', 'USERPROFILE': '/owned', 'PATH': '/system'}
        fixed = dict(runtime)
        additions = {'ProgramFiles': 'C:/Program Files', 'ProgramFiles(x86)': 'C:/Program Files (x86)', 'ProgramData': 'C:/ProgramData'}
        with patch.object(m.sys, 'platform', 'win32'), patch.dict(os.environ, {**additions, 'GH_TOKEN':'fixture-secret', 'HTTPS_PROXY':'fixture-proxy'}, clear=True):
            actual = m.compile_environment(runtime)
        self.assertEqual(actual, {**runtime, **additions})
        self.assertEqual(runtime, fixed)
        with patch.object(m.sys, 'platform', 'linux'):
            self.assertEqual(m.compile_environment(runtime), runtime)

    def test_VP002_failure_records_cleanup_and_propagates(self):
        m = driver()
        self.assertTrue(hasattr(m, 'recorded_directory'), 'post-cleanup evidence helper missing')
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'report.json'
            report = {'passed':False, 'failure_marker':'fixture'}
            with self.assertRaisesRegex(RuntimeError, 'original_failure'):
                with m.recorded_directory(report, output) as work:
                    (work/'fixture').write_bytes(b'not-runtime')
                    raise RuntimeError('original_failure')
            observed = json.loads(output.read_bytes())
            self.assertFalse(observed['passed'])
            self.assertEqual(observed['failure_marker'], 'fixture')
            self.assertTrue(observed['temporary_root_absent'])
            self.assertFalse(Path(observed['temporary_root']).exists())

    def test_VP003_success_records_cleanup_after_exit(self):
        m = driver()
        self.assertTrue(hasattr(m, 'recorded_directory'), 'post-cleanup evidence helper missing')
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'report.json'; report = {'passed':False}
            with m.recorded_directory(report, output) as work:
                self.assertTrue(work.is_dir())
                self.assertFalse(output.exists())
                report['passed'] = True
            self.assertTrue(json.loads(output.read_bytes())['temporary_root_absent'])


if __name__ == '__main__': unittest.main(verbosity=2)
