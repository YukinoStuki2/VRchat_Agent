"""Isolated launcher-only test runner with immutable per-run evidence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def process_snapshot():
    rows = {}
    if sys.platform != 'linux':
        return rows
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            rows[int(path.name)] = {'parent': int(fields[1]), 'starttime': int(fields[19]),
                                     'pgrp': int(fields[2]), 'state': fields[0]}
        except (OSError, ValueError, IndexError):
            pass
    return rows

def main():
    label = sys.argv[1]
    out = ROOT / 'evidence' / ('launcher-completion-' + label + '.json')
    if out.exists():
        raise SystemExit('Evidence already exists; choose a new label')
    selectors = sys.argv[2:] or ['discover', '-s', str(ROOT / 'tests'), '-p', 'test_launcher_candidate*.py', '-v']
    with tempfile.TemporaryDirectory(prefix='candidate-launcher-tests-') as home:
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'SystemRoot', 'WINDIR', 'LANG')}
        env.update(HOME=home, USERPROFILE=home, TMPDIR=home, TEMP=home, TMP=home,
                   PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT / 'tests'))
        argv = [sys.executable, '-B', '-W', 'error::ResourceWarning', '-m', 'unittest', *selectors]
        started = time.monotonic()
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        observed, done = {}, threading.Event()
        def observe():
            while not done.is_set():
                snapshot = process_snapshot()
                descendants = {process.pid}
                while True:
                    expanded = descendants | {pid for pid, row in snapshot.items() if row['parent'] in descendants}
                    if expanded == descendants:
                        break
                    descendants = expanded
                for pid in descendants & snapshot.keys():
                    observed[(pid, snapshot[pid]['starttime'])] = snapshot[pid]
                done.wait(.02)
        monitor = threading.Thread(target=observe)
        monitor.start()
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
        finally:
            done.set()
            monitor.join()
        after = process_snapshot()
        remaining = [pid for pid, start in observed if pid in after and after[pid]['starttime'] == start]
        report = {'argv': argv, 'exit_code': process.returncode, 'stdout': stdout,
                  'stderr': stderr, 'elapsed_seconds': time.monotonic() - started,
                  'timeout': timed_out, 'observed_processes': [{'pid': pid, **row} for (pid, _), row in sorted(observed.items())],
                  'remaining_observed_pids': remaining, 'cleanup_sampling_interval_seconds': .02,
                  'temporary_home': home, 'input_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted([*(ROOT / 'launcher').glob('*.py'), *(ROOT / 'tests').glob('test_launcher_candidate*.py')])}}
    report['temporary_home_absent'] = not Path(home).exists()
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(stdout + stderr)
    print(json.dumps({'evidence': str(out), 'exit_code': process.returncode, 'remaining_observed_pids': remaining, 'temporary_home_absent': report['temporary_home_absent']}))
    return process.returncode or bool(remaining) or timed_out

if __name__ == '__main__':
    raise SystemExit(main())
