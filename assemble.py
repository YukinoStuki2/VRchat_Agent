"""Assemble only frozen, hash-checked bytes for one preview distribution.

No payload execution, installs, downloads, credentials or release writes.
ZIP container bytes may differ across zlib versions; member hashes may not.
"""
from pathlib import Path, PurePosixPath
import hashlib
import importlib.util
import json
import sys
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reused_zip_layout', HERE/'zip_layout.py')
assert spec is not None and spec.loader is not None
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble(runtime, output):
    plan = json.loads((HERE/'distribution-plan.json').read_bytes())
    assert not output.exists(), 'output already exists'
    assert sha(runtime.read_bytes()) == plan['runtime_archive_sha256'], 'runtime hash mismatch'
    overlay = HERE/'source-overlay.zip'
    assert sha(overlay.read_bytes()) == plan['overlay_sha256'], 'overlay hash mismatch'
    plugin = HERE/plan['plugin_filename']
    assert sha(plugin.read_bytes()) == plan['plugin_sha256'], 'plugin hash mismatch'
    prefixes = ('Runtime~/python/', 'Runtime~/python-notices/',
                'Runtime~/wheel-notices/', 'Runtime~/diagnostics-backend/')
    files = {}
    for path, runtime_only in ((runtime, True), (overlay, False)):
        with zipfile.ZipFile(path) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            assert archive.testzip() is None
            for info in archive.infolist():
                name = info.filename
                assert not info.is_dir() and not PurePosixPath(name).is_absolute()
                assert str(PurePosixPath(name)) == name and '..' not in PurePosixPath(name).parts
                assert '\\' not in name
                if runtime_only and not (name.startswith(prefixes) or name == 'Runtime~/portable-launch.json'):
                    continue
                assert name not in files, 'overlapping payload member'
                files[name] = archive.read(name)
    assert {n: sha(b) for n, b in files.items()} == plan['members'], 'payload member mismatch'
    manifest = json.loads(files['package.json'])
    archive = layout.zip_bytes(files)
    entry = dict(manifest, zipSHA256=sha(archive))
    coplay_bytes = (HERE/plan['coplay_filename']).read_bytes()
    assert sha(coplay_bytes) == plan['coplay_sha256'], 'Coplay archive hash mismatch'
    provenance_bytes = (HERE/'coplay-provenance.json').read_bytes()
    assert sha(provenance_bytes) == plan['coplay_provenance_sha256'], 'Coplay provenance hash mismatch'
    provenance = json.loads(provenance_bytes)
    with zipfile.ZipFile(HERE/plan['coplay_filename']) as dependency:
        assert dependency.testzip() is None
        assert len(dependency.namelist()) == len(set(dependency.namelist()))
        assert {n:sha(dependency.read(n)) for n in dependency.namelist()} == provenance['distribution_files']
        coplay = json.loads(dependency.read('package.json'))
    assert coplay['name'] == 'com.coplaydev.unity-mcp' and coplay['version'] == '10.2.0'
    assert manifest['vpmDependencies'] == {coplay['name']: '=10.2.0'}
    previous_bytes = (HERE/'previous-index.json').read_bytes()
    assert sha(previous_bytes) == plan['previous_index_sha256'], 'previous index hash mismatch'
    packages = json.loads(previous_bytes)['packages']
    assert manifest['version'] not in packages[manifest['name']]['versions'], 'refuse replacing version'
    packages[manifest['name']]['versions'][manifest['version']] = entry
    assert coplay['name'] not in packages, 'refuse replacing dependency'
    packages[coplay['name']] = {'versions': {coplay['version']: dict(coplay, zipSHA256=sha(coplay_bytes))}}
    index = dict(plan['repository_identity'], packages=packages)
    assets = {plan['candidate_filename']: archive, plan['plugin_filename']: plugin.read_bytes(),
              plan['coplay_filename']: coplay_bytes, 'coplay-provenance.json': provenance_bytes,
              'index.json': layout.json_bytes(index), 'README.md': (HERE/'README.md').read_bytes()}
    assets['SHA256SUMS.json'] = layout.json_bytes({n: sha(b) for n, b in assets.items()})
    output.mkdir(parents=True)
    for name, data in assets.items():
        assert Path(name).name == name
        with (output/name).open('xb') as handle:
            handle.write(data)
    print(json.dumps({'candidate_sha256': entry['zipSHA256'], 'members': len(files),
                      'candidate_bytes': len(archive), 'assets': sorted(assets)}, ensure_ascii=False))


if __name__ == '__main__':
    assemble(Path(sys.argv[1]).resolve(strict=True), Path(sys.argv[2]))
