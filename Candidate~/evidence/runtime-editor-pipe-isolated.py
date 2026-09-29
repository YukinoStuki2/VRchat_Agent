"""One server/test per process; real existing tests, no source changes."""
import ast
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON = '/home/ubuntu/.cache/uv/archive-v0/7z4PORN2YM2xSubx/bin/python'
OUT = ROOT / 'evidence/runtime-editor-pipe-isolated-final-result.json'
if OUT.exists():
    raise SystemExit('Refusing to overwrite prior evidence')
files = sorted((ROOT / 'tests').glob('test_runtime*.py')) + [ROOT/'tests'/name for name in ('test_bootstrap_runtime.py','test_owned_launcher.py','test_run_identity.py','test_tls_context.py','test_editor_owner.py')]
cases = []
for path in files:
    tree = ast.parse(path.read_text())
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef):
            for method in cls.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith('test_'):
                    cases.append((str(path.relative_to(ROOT)), cls.name + '.' + method.name))
tracked = sorted(set(files + [ROOT/'tests/runtime_fixture_entry.py'] + [p for base in ('runtime', 'launcher', 'native/src', 'dependencies/mcp-1.29.1')
    for p in (ROOT / base).rglob('*.py') if '__pycache__' not in p.parts]))
def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
before = hashes()
rows = []

def run(item):
    number, (file, method) = item
    label = f'editor-pipe-isolated-{number:03d}'
    argv = [PYTHON, '-B', str(ROOT / 'tests/verify_runtime.py'), label, file, '-', method]
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'LANG': 'C.UTF-8'}
    result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=85)
    checked = ROOT / 'evidence' / ('runtime-checked-' + label + '.json')
    raw = ROOT / 'evidence' / ('runtime-fix-' + label + '.json')
    evidence = json.loads(checked.read_text()) if checked.exists() else {}
    detail = json.loads(raw.read_text()) if raw.exists() else {}
    ids = evidence.get('test_ids', [])
    passed = result.returncode == 0 and evidence.get('passed') is True and len(ids) == 1
    return {'file': file, 'method': method, 'passed': passed, 'exit': result.returncode,
        'evidence': checked.name, 'raw_evidence': raw.name, 'test_ids': ids,
        'cleanup': detail.get('cleanup'), 'error_tail': result.stdout[-1600:] + result.stderr[-1600:] if not passed else ''}

# LC006 is not skipped: verify_unity must separately fresh-build and execute it.
separate = [('tests/test_runtime_lifecycle.py',
    'WireLifecycleTests.test_LC006_sdk_exit_removes_plan_in_compiled_csharp_gate')]
assert all(item in cases for item in separate), 'Missing declared separate test'
cases = [item for item in cases if item not in separate]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for row in pool.map(run, enumerate(cases, 1)):
        rows.append(row)
        with OUT.open('w') as f:
            json.dump({'complete': False, 'expected_count': len(cases), 'rows': rows}, f, indent=2)
        print(json.dumps({k: row[k] for k in ('method', 'passed', 'exit')}), flush=True)
after = hashes()
report = {'complete': True, 'scope': 'Parent existing runtime regression, isolated per method; not independent or Unity acceptance',
    'separate_fresh_build_tests': separate,
    'expected_count': len(cases), 'executed_count': len(rows),
    'unique_count': len({(r['file'], r['method']) for r in rows}),
    'passed_count': sum(r['passed'] for r in rows), 'rows': rows,
    'source_sha256_before': before, 'source_sha256_after': after,
    'sources_unchanged': before == after,
    'passed': bool(rows) and len(rows) == len(cases) and all(r['passed'] for r in rows) and before == after}
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('rows','source_sha256_before','source_sha256_after')}), flush=True)
raise SystemExit(0 if report['passed'] else 1)
