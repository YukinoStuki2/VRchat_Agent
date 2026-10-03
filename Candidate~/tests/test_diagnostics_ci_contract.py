"""Portable CI wiring checks; not a substitute for Windows kernel tests."""
import ast
from pathlib import Path
import re
import subprocess
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
WORKFLOW = BASE.parent / '.github/workflows/candidate-kernel.yml'


class DiagnosticsCIContract(unittest.TestCase):
    def test_DCI001_workflow_uses_actual_report_fields(self):
        tree = ast.parse((BASE / 'diagnostics/verify_windows.py').read_text())
        report = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'report'
                              for target in node.targets))
        fields = {key.value for key in report.keys}
        job = WORKFLOW.read_text().split('  diagnostics-kernel:', 1)[1]
        referenced = set(re.findall(r'\$r\.([a-zA-Z_]+)', job))
        self.assertTrue(referenced)
        self.assertEqual(referenced - fields, set(), 'workflow references absent report fields')
        self.assertTrue({'passed', 'windows_kernel_executed', 'test_count', 'passed_ids',
                         'skipped_ids', 'failed_ids', 'isolated_home_removed',
                         'source_hashes_unchanged', 'cleanup'} <= referenced)

    def test_DCI002_capture_warnings_through_process_exit(self):
        job = WORKFLOW.read_text().split('  diagnostics-kernel:', 1)[1]
        self.assertIn('-W always::ResourceWarning', job)
        self.assertIn('2>&1 | Tee-Object', job)
        self.assertIn("-match 'ResourceWarning'", job)
        # Destructor warning at process teardown still appears with exit 0:
        # checking exit code alone is therefore insufficient.
        # Keep warnings reachable at shutdown; no file/handle leak is introduced.
        code = "import warnings\nclass Leaky:\n def __del__(self, warn=warnings.warn):\n  warn('synthetic shutdown warning', ResourceWarning)\nfixture=Leaky()\n"
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-W',
                                 'always::ResourceWarning', '-c', code],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ResourceWarning', result.stdout + result.stderr)


    def test_DCI003_lifetime_gate_tracks_every_crash_case(self):
        tree = ast.parse((BASE / 'tests/test_diagnostics_crash.py').read_text(encoding='utf-8'))
        ids = sorted(re.match(r'test_(DX[0-9]+)_', n.name).group(1) for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name.startswith('test_DX'))
        job = WORKFLOW.read_text(encoding='utf-8').split('Capture-owner termination', 1)[1]
        self.assertIn('Ran ' + str(len(ids)) + ' tests', job)
        for name in ids:
            self.assertIn("'" + name + "'", job)
        portable = (BASE / 'tests/verify_portable.py').read_text(encoding='utf-8')
        self.assertIn('Ran ' + str(len(ids)) + ' tests', portable)

    def test_DCI004_windows_executes_all_cleanup_retry_cases(self):
        tree = ast.parse((BASE / 'tests/test_diagnostics_lifetime_retry.py').read_text(encoding='utf-8'))
        methods = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_DL_R1_')]
        job = WORKFLOW.read_text(encoding='utf-8').split('Capture-owner termination', 1)[1]
        self.assertIn('tests/test_diagnostics_lifetime_retry.py', job)
        self.assertIn('Ran ' + str(len(methods)) + ' tests', job)
        self.assertIn('skipped|FAILED|ResourceWarning', job)
        portable = (BASE / 'tests/verify_portable.py').read_text(encoding='utf-8')
        self.assertIn('test_diagnostics_lifetime_retry.py', portable)
        self.assertIn('windows_kernel_executed', portable)

if __name__ == '__main__':
    unittest.main(verbosity=2)
