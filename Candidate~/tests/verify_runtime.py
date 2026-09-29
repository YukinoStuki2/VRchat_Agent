"""Reuse the bounded regression runner with the explicit candidate SDK overlay.
Usage: pinned-python -B tests/verify_runtime.py LABEL FILE MODE [FILTER ...]
Does not edit installed packages or suppress resource warnings.
"""
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) < 4 or re.fullmatch(r'[a-z0-9-]+', sys.argv[1]) is None:
        raise SystemExit('LABEL FILE MODE [FILTER ...] required')
    label = sys.argv[1]
    target = ROOT / 'evidence' / ('runtime-checked-' + label + '.json')
    if target.exists():
        raise SystemExit('Refusing to overwrite evidence')
    spec = importlib.util.spec_from_file_location('bounded_runner', ROOT/'evidence/runtime-fix-run.py')
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    state = vars(runner)
    state['CHILD'] = ('import sys,warnings; sys.path[:0]=' + repr([
        str(ROOT/'dependencies/mcp-1.29.1'), str(ROOT/'tests')]) + '\n'
        'warnings.simplefilter("always",ResourceWarning)\n') + state['CHILD']
    state['TRACKED'] += [str(p.relative_to(ROOT)) for p in
        (ROOT/'dependencies/mcp-1.29.1').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    state['TRACKED'] += ['tests/verify_runtime.py']
    code = 1
    try:
        state['main']()
    except SystemExit as exc:
        code = exc.code
    source = ROOT/'evidence'/('runtime-fix-' + label + '.json')
    if not source.exists():
        raise SystemExit(code or 1)
    report = json.loads(source.read_text())
    result = report['result'] or {}
    warning_lines = [s for s in report['stderr'].splitlines() if 'ResourceWarning:' in s]
    passed = (code == 0 and report['exit_code'] == 0 and not report['timed_out']
        and result.get('tests', 0) > 0 and not result.get('skipped') and not warning_lines
        and report['hashes_before'] == report['hashes_after'] and all(report['cleanup'].values()))
    checked = {'source_report': source.name, 'passed': passed,
        'test_ids': result.get('ids', []), 'resource_warning_lines': warning_lines,
        'source_unchanged': report['hashes_before'] == report['hashes_after'],
        'independent_approval': False}
    target.write_text(json.dumps(checked, indent=2) + '\n')
    print(json.dumps(checked))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
