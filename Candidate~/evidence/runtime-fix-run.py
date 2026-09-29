"""Bounded local-only regression runner; preserves immutable per-run evidence.
Usage: python -B evidence/runtime-fix-run.py LABEL FILE MODE FILTER [FILTER...]
MODE '-' for normal unittest files; sdk/http for the immutable review repro.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
TRACKED = ['runtime/candidate_runtime.py', 'runtime/__main__.py',
           'native/src/transport/plugin_hub.py', 'native/src/main.py',
           'tests/test_runtime.py', 'tests/test_runtime_http.py',
           'evidence/runtime-review.json', 'evidence/runtime-review-repro.py',
           'evidence/runtime-review-runs.json', 'evidence/runtime-review-verification.json']
CHILD = '''import json, runpy, sys, unittest
path, mode, *filters = sys.argv[1:]
sys.argv = [path] + ([] if mode == '-' else [mode])
namespace = runpy.run_path(path, run_name='runtime_fix_tests')
suite = unittest.TestSuite()
ids = []
for value in namespace.values():
    if isinstance(value, type) and issubclass(value, unittest.TestCase):
        for test in unittest.defaultTestLoader.loadTestsFromTestCase(value):
            if not filters or any(f in test.id() for f in filters):
                suite.addTest(test)
                ids.append(test.id())
result = unittest.TextTestRunner(verbosity=2).run(suite)
print('FIX_RESULT=' + json.dumps({'ids': ids, 'tests': result.testsRun,
 'failures': [t.id() for t, _ in result.failures],
 'errors': [t.id() for t, _ in result.errors],
 'skipped': [(t.id(), reason) for t, reason in result.skipped]}), flush=True)
sys.exit(0 if result.wasSuccessful() and result.testsRun else 1)
'''


def hashes(paths):
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in sorted(set(paths)) if (ROOT / p).is_file()}


def main():
    label, file, mode, *filters = sys.argv[1:]
    destination = ROOT / 'evidence' / ('runtime-fix-' + label + '.json')
    if destination.exists():
        raise SystemExit('evidence already exists; choose a new label')
    tracked = TRACKED + [file, 'evidence/runtime-fix-run.py']
    before = hashes(tracked)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='runtime-fix-run-') as home:
        env = {'PATH': '/usr/bin:/bin', 'HOME': home, 'LANG': 'C.UTF-8',
               'DISABLE_TELEMETRY': 'true', 'FASTMCP_CHECK_FOR_UPDATES': 'off'}
        command = [sys.executable, '-B', '-c', CHILD, str(ROOT / file), mode, *filters]
        proc = subprocess.Popen(command, cwd=ROOT, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate(timeout=5)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
        group_remaining = False
        try:
            os.killpg(proc.pid, 0)
            group_remaining = True
        except ProcessLookupError:
            pass
    result = None
    for line in stdout.splitlines():
        if line.startswith('FIX_RESULT='):
            result = json.loads(line.removeprefix('FIX_RESULT='))
    evidence = {'label': label, 'runner_argv': sys.argv, 'command': command,
                'env': env, 'exit_code': proc.returncode, 'timed_out': timed_out,
                'duration_seconds': time.monotonic() - start,
                'result': result, 'stdout': stdout, 'stderr': stderr,
                'hashes_before': before, 'hashes_after': hashes(tracked),
                'cleanup': {'runner_pid_absent': not Path(f'/proc/{proc.pid}').exists(),
                            'process_group_absent': not group_remaining,
                            'temporary_home_absent': not Path(home).exists()}}
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: evidence[k] for k in ('label', 'exit_code', 'timed_out', 'result', 'cleanup')}, indent=2))
    print(stdout)
    print(stderr)
    if group_remaining:
        os.killpg(proc.pid, signal.SIGKILL)
        raise SystemExit('residual process group; forced cleanup, not a passing run')
    raise SystemExit(proc.returncode if not timed_out else 124)


if __name__ == '__main__':
    main()
