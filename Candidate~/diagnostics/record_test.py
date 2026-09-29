"""Local test-evidence runner, not part of the MCP runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parents[1]
label, *tests = sys.argv[1:]
command = [sys.executable, '-B', '-m', 'unittest', '-v', *tests]
inputs = {str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in [*BASE.glob('diagnostics/*.py'), *BASE.glob('tests/test_diagnostics*.py')]}
start = time.monotonic()
with tempfile.TemporaryDirectory(prefix='diagnostics-run-') as home:
    env = {'PATH': '/usr/bin:/bin', 'HOME': home, 'TMPDIR': home, 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1'}
    run = subprocess.run(command, cwd=BASE, env=env, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=180)
    output = run.stdout.replace(home, '<isolated-home>')
record = {'label': label, 'command': command, 'cwd': str(BASE), 'environment':
          {'isolated_HOME_TMPDIR': True, 'cleared_inherited_env': True},
          'exit_code': run.returncode, 'elapsed_seconds': time.monotonic()-start,
          'input_sha256': inputs, 'output': output, 'runner_home_removed': not Path(home).exists()}
file = BASE / 'evidence' / ('diagnostics-' + label + '.json')
file.parent.mkdir(exist_ok=True)
file.write_text(json.dumps(record, indent=2) + '\n')
print(output)
print('evidence:', file)
sys.exit(run.returncode)
