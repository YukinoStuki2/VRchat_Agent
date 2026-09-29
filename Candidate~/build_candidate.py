"""Local installable-candidate packer. Never updates the live VPM repository.

Reuse the project's deterministic ZIP implementation. A review proof is an
operator-produced build input, not authentication or an agent approval API.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import re

_BASE = Path(__file__).resolve().parents[1] / 'VPM~/build_repository.py'
_spec = importlib.util.spec_from_file_location('existing_vpm_builder', _BASE)
assert _spec is not None and _spec.loader is not None
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
PACKAGE_ID = 'com.yukino.vrchat-agent'
VERSION = '0.2.0-preview.1'
GATES = ('implementation_complete', 'local_checks_passed',
         'independent_source_reviews_passed', 'windows_kernel_checks_passed')


def build(package, proof, asset_base):
    if (type(proof) is not dict or any(proof.get(k) is not True for k in GATES)
            or proof.get('unity_verified') is not False
            or proof.get('remaining_implementation_gaps') != []):
        raise ValueError('incomplete candidate verification')
    package = Path(package)
    files = {}
    for name, expected in proof.get('source_sha256', {}).items():
        data = base.read_regular(package, name)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('reviewed source drift: ' + name)
        files[name] = data
    required = {'package.json', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'}
    if not required <= files.keys() or not any(n.endswith('.cs') for n in files):
        raise ValueError('incomplete package source')
    guids = set()
    for name in files:
        if name.endswith('.meta'):
            declarations = [line for line in files[name].decode('utf-8').splitlines() if line.startswith('guid:')]
            if len(declarations) != 1 or re.fullmatch(r'guid: [0-9a-f]{32}', declarations[0]) is None:
                raise ValueError('invalid meta GUID')
            guid = declarations[0][6:]
            if guid in guids:
                raise ValueError('duplicate meta GUID')
            guids.add(guid)
            continue
        required_meta = {name + '.meta'}
        required_meta.update(str(parent) + '.meta' for parent in Path(name).parents if str(parent) != '.')
        if not required_meta <= files.keys():
            raise ValueError('missing reviewed meta')
    manifest = json.loads(files['package.json'])
    if manifest.get('name') != PACKAGE_ID or manifest.get('version') != VERSION:
        raise ValueError('wrong package identity')
    if any(k.startswith('legacy') for k in manifest):
        raise ValueError('implicit deletion forbidden')
    filename = PACKAGE_ID + '-' + VERSION + '.zip'
    manifest['url'] = asset_base + filename
    files['package.json'] = base.json_bytes(manifest)
    archive = base.zip_bytes(files)
    return filename, archive, dict(manifest, zipSHA256=hashlib.sha256(archive).hexdigest())
