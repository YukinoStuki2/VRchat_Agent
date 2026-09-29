"""Collect exact active-lock LICENSE/NOTICE bytes, never infer from SPDX alone.

Installed RECORD hashes are verified; they do not replace selected wheel hashes
or CPython redistribution review. No network and no installation/config writes.
"""
import base64
import hashlib
import importlib.util
from importlib import metadata
import json
from pathlib import Path
import re
import sys
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

verify = load('locked_install', ROOT / 'distribution/verify_dependency_install.py')
base = load('package_files', ROOT.parent / 'VPM~/build_repository.py')


def collect(supplements=None):
    installation = verify.inspect_installation()
    if supplements is None:
        supplements = json.loads(base.read_regular(ROOT, 'distribution/license-supplements.json'))
    rows, output = [], {}
    for name, version in sorted(installation['installed'].items()):
        distribution = metadata.distribution(name)
        normalized = canonicalize_name(name)
        fields = dict(distribution.metadata.items())
        row = {'name': normalized, 'version': version,
               'license_expression': fields.get('License-Expression'),
               'license_metadata': fields.get('License'),
               'license_files': []}
        for file in distribution.files or []:
            if file.suffix.lower() in {'.py', '.pyi', '.pyc'}:
                continue
            if not (re.match(r'^(licen[cs]e|copying|notice)(?:[._-].*)?$', file.name, re.I) or
                    any(p.lower() == 'licenses' for p in file.parts)):
                continue
            data = base.read_regular(Path(str(distribution.locate_file(''))), str(file))
            if len(data) > 2 * 1024 * 1024 or not data.strip():
                raise ValueError('license_size_invalid: ' + normalized)
            if file.hash is None:
                raise ValueError('license_record_hash_missing: ' + normalized)
            actual = base64.urlsafe_b64encode(hashlib.new(file.hash.mode, data).digest()).rstrip(b'=').decode()
            if actual != file.hash.value:
                raise ValueError('license_record_drift: ' + normalized)
            destination = normalized + '/' + version + '/' + file.as_posix()
            output[destination] = data
            row['license_files'].append({'original_path': file.as_posix(), 'bundle_path': destination,
                'sha256': hashlib.sha256(data).hexdigest(), 'record_verified': True, 'source': 'installed-wheel'})
        recorded = {item['original_path'].split('.dist-info/', 1)[1]
                    for item in row['license_files'] if '.dist-info/' in item['original_path']}
        for declared in distribution.metadata.get_all('License-File', []):
            if declared not in recorded and 'licenses/' + declared not in recorded:
                raise ValueError('declared_license_missing: ' + normalized)
        if normalized in supplements:
            addition = supplements[normalized]
            if (addition['version'] != version or addition['license_expression'] != row['license_expression'] or
                    re.fullmatch(r'[0-9a-f]{40}', addition['upstream_commit']) is None):
                raise ValueError('license_supplement_identity_mismatch: ' + normalized)
            for name, expected in addition['files'].items():
                data = base.read_regular(ROOT / 'distribution/license-supplements', name)
                if hashlib.sha256(data).hexdigest() != expected or not data.strip():
                    raise ValueError('license_supplement_drift: ' + normalized)
                destination = normalized + '/' + version + '/upstream/' + name
                if destination in output: raise ValueError('duplicate_license_destination')
                output[destination] = data
                row['license_files'].append({'original_path': name, 'bundle_path': destination,
                    'sha256': expected, 'record_verified': False, 'source': 'pinned-upstream-supplement',
                    'upstream_commit': addition['upstream_commit'], 'source_url': addition['source_url']})
        rows.append(row)
    missing = [r['name'] for r in rows if not r['license_files']]
    report = {'scope': 'Active locked wheel license inventory only; no CPython or product approval',
              'platform': installation['platform'], 'python': installation['python'],
              'requirements_sha256': hashlib.sha256((ROOT / 'distribution/requirements.lock').read_bytes()).hexdigest(),
              'active_lock_count': len(rows), 'dependencies': rows,
              'missing_license_text': missing, 'complete': not missing,
              'selected_wheel_hashes_verified': False, 'cpython_redistribution_verified': False}
    return report, output


if __name__ == '__main__':
    report, files = collect()
    target = Path(sys.argv[1])
    # New task-owned output only; never merge into an existing notices bundle.
    base.check_output_path(target)
    target.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = target / 'texts' / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle: handle.write(data)
    with (target / 'inventory.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'dependencies'}))
    raise SystemExit(0 if report['complete'] else 1)
