"""Windows kernel CI gate, Python 3.11+ stdlib only; never equate skips with pass.

Run: python -B diagnostics/verify_windows.py --output <new-json-file>
Exit 0 = every WK test passed on Windows; 1 = failure; 2 = unavailable/skipped.
No Node/FastMCP dependency: this gate validates HANDLE/ACL/capture, not MCP.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.states = {}

    def startTest(self, test):
        self.states[test.id()] = 'started'
        super().startTest(test)

    def addSuccess(self, test):
        self.states[test.id()] = 'passed'
        super().addSuccess(test)

    def addSkip(self, test, reason):
        self.states[test.id()] = 'skipped'
        super().addSkip(test, reason)

    def addFailure(self, test, err):
        self.states[test.id()] = 'failed'
        super().addFailure(test, err)

    def addError(self, test, err):
        self.states[test.id()] = 'error'
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        if err:
            self.states[test.id()] = 'failed'
        super().addSubTest(test, subtest, err)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='new JSON file (old evidence never overwritten)')
    args = parser.parse_args(argv)
    from tests import test_diagnostics_windows_kernel as cases
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(cases.WindowsKernelTests)
    ids = sorted(test.id() for test in suite)
    files = [BASE / 'diagnostics/windows_handles.py', BASE / 'diagnostics/snapshot.py',
             BASE / 'diagnostics/verify_windows.py', BASE / 'tests/test_diagnostics_windows_kernel.py']
    def hashes():
        return {str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    before = hashes()
    output = io.StringIO()
    old_tempdir = tempfile.tempdir
    # Only the runner's own fresh fixture is canonicalized. CI's TEMP can use
    # an 8.3 alias; production read_selected must continue rejecting aliases.
    with tempfile.TemporaryDirectory(prefix='diagnostics-windows-run-') as owned_home:
        home = str(Path(owned_home).resolve(strict=True))
        env = {key: value for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC')
               if (value := os.environ.get(key))}
        env.update({key: home for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'TMPDIR')})
        env['PATH'] = os.pathsep.join([str(Path(sys.executable).parent),
                                     str(Path(env.get('SYSTEMROOT', '/usr')) / ('System32' if os.name == 'nt' else 'bin'))])
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        try:
            tempfile.tempdir = home
            with patch.dict(os.environ, env, clear=True):
                result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=RecordedResult).run(suite)
        finally:
            tempfile.tempdir = old_tempdir
    states = result.states
    after = hashes()
    passed = (os.name == 'nt' and result.wasSuccessful() and not result.skipped
              and sorted(states) == ids and all(value == 'passed' for value in states.values())
              and len(cases.CLEANUP) == len(ids) and before == after and not Path(home).exists())
    report = {'windows_kernel_executed': os.name == 'nt', 'passed': passed,
              'python': sys.version, 'platform': sys.platform, 'expected_ids': ids,
              'test_count': result.testsRun, 'passed_ids': sorted(k for k, v in states.items() if v == 'passed'),
              'skipped_ids': sorted(k for k, v in states.items() if v == 'skipped'),
              'failed_ids': sorted(k for k, v in states.items() if v not in ('passed', 'skipped')),
              'skip_reasons': [(test.id(), reason) for test, reason in result.skipped],
              'cleanup': cases.CLEANUP, 'isolated_home_removed': not Path(home).exists(),
              'source_sha256': before, 'source_hashes_unchanged': before == after,
              'output': output.getvalue().replace(home, '<isolated-home>')}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': passed, 'windows_kernel_executed': os.name == 'nt',
                      'tests': result.testsRun, 'skipped': len(result.skipped), 'output': str(destination)}))
    return 0 if passed else (2 if os.name != 'nt' or result.skipped else 1)


if __name__ == '__main__':
    raise SystemExit(main())
