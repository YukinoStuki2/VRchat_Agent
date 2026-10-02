"""Pinned PBS extraction for isolated developer builds; not product approval.

Uses stdlib tarfile.data_filter; never modifies a selected existing interpreter.
"""
import hashlib
import io
from pathlib import Path
import shutil
import tarfile
import importlib.util
import json
import os
import platform
import subprocess
import re
from urllib.parse import urlparse, unquote
from urllib.request import url2pathname

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_bytes())


def clean_environment(home):
    result = {'PATH': os.defpath, 'HOME': str(home), 'USERPROFILE': str(home),
              'TMP': str(home), 'TEMP': str(home), 'LANG': 'C.UTF-8',
              'DOTNET_CLI_HOME': str(home), 'DOTNET_CLI_TELEMETRY_OPTOUT': '1',
              'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1', 'DOTNET_NOLOGO': '1',
              'MSBUILDDISABLENODEREUSE': '1'}
    if os.name == 'nt':
        for key in ('SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT'):
            value = os.environ.get(key)
            if value: result[key] = value
    return result


def identity(executable):
    result = subprocess.run([str(executable), '-I', '-B', '-c',
        'import sys,json,platform,ssl,sqlite3;print(json.dumps(dict(version=platform.python_version(),'
        'implementation=sys.implementation.name,prefix=sys.prefix,base_prefix=sys.base_prefix,'
        'executable=sys.executable,openssl=ssl.OPENSSL_VERSION)))'],
        env=clean_environment(executable.parent), capture_output=True, text=True, timeout=20, check=True)
    return json.loads(result.stdout)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def check_wheels(report, lock, installed, wheelhouse=None):
    canonical = lambda name: re.sub(r'[-_.]+', '-', name).lower()
    entries = list(re.finditer(r'^([A-Za-z0-9_.-]+)==([^\s;]+)', lock, re.M))
    hashes = {}
    for index, match in enumerate(entries):
        block = lock[match.start():entries[index+1].start() if index+1<len(entries) else len(lock)]
        hashes.setdefault((canonical(match[1]), match[2]), set()).update(re.findall(r'--hash=sha256:([0-9a-f]{64})', block))
    expected = {canonical(name): version for name, version in installed.items()}
    selected = {}
    for item in report['install']:
        name, version = canonical(item['metadata']['name']), item['metadata']['version']
        info = item['download_info']; url = urlparse(info['url'])
        digest = info['archive_info']['hashes']['sha256']
        if wheelhouse is None:
            allowed_origin = url.scheme == 'https' and url.netloc == 'files.pythonhosted.org'
        else:
            origin = Path(url2pathname(url.path))
            house = Path(wheelhouse).resolve(strict=True)
            allowed_origin = (url.scheme == 'file' and not url.netloc and not url.query and not url.fragment
                and origin.parent == house and not origin.is_symlink() and origin.is_file()
                and hashlib.sha256(origin.read_bytes()).hexdigest() == digest)
        if (name in selected or expected.get(name) != version or digest not in hashes.get((name,version), ())
            or not allowed_origin
            or not unquote(url.path).endswith('.whl')):
            raise ValueError('selected_wheel_mismatch')
        selected[name] = {'version': version, 'url': info['url'], 'sha256': digest}
    if selected.keys() != expected.keys(): raise ValueError('selected_wheel_set_mismatch')
    return selected


def write_launch_descriptor(package, platform_key, version):
    """Launch-entry integrity only, not a signature or full-runtime approval."""
    executable = {'linux-x86_64': 'python/bin/python3.11', 'windows-x86_64': 'python/python.exe'}[platform_key]
    runtime = Path(package)/'Runtime~'
    paths = (executable, 'launcher/editor_owner.py', 'launcher/direct_python.py')
    files = {}
    for name in paths:
        path = runtime/name
        if path.is_symlink() or not path.is_file(): raise ValueError('launch_file_invalid')
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    with (runtime/'portable-launch.json').open('x', encoding='utf-8') as output:
        json.dump({'schema':1, 'platform':platform_key, 'python_version':version, 'files':files}, output, indent=2)


def build(archive, destination, wheelhouse=None, node_archive=None):
    """Task-owned dev directory only. No ZIP, VPM, config or existing env writes."""
    system = platform.system().lower()
    if platform.machine().lower() not in ('x86_64', 'amd64') or system not in ('linux', 'windows'):
        raise ValueError('unsupported_platform')
    pins = read_json(ROOT/'distribution/python-standalone.lock.json')
    key = system+'-x86_64'; pin = pins['platforms'][key]
    assemble = load('portable_sources', ROOT/'distribution/assemble_source.py')
    payload = assemble.collect(ROOT)
    # Source/notice read-back precedes extraction or executable startup.
    licenses = {}
    for name, digest in {pin['metadata']: pin['metadata_sha256'], **pin['licenses']}.items():
        data = assemble.packer.base.read_regular(ROOT/'distribution', name)
        if hashlib.sha256(data).hexdigest() != digest: raise ValueError('python_notice_drift')
        licenses[name] = data
    destination = Path(destination).absolute()
    destination.mkdir()  # Atomic refusal of all pre-existing paths, including links.
    try:
        evidence = destination/'evidence'; evidence.mkdir()
        extract(Path(archive), destination/'extracted', pin['sha256'])
        package = destination/'package'
        for name, data in payload.items():
            target = package/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        python_root = package/'Runtime~/python'
        (destination/'extracted/python').rename(python_root)
        (destination/'extracted').rmdir()
        executable = package/'Runtime~'/pin['executable']
        observed = identity(executable)
        if observed['version'] != pins['python_version'] or observed['implementation'] != 'cpython':
            raise ValueError('python_identity_mismatch')
        if Path(observed['prefix']) != python_root or Path(observed['base_prefix']) != python_root:
            raise ValueError('python_prefix_mismatch')
        env = clean_environment(destination)
        def run(name, args, timeout=180):
            result = subprocess.run([str(executable), '-I', '-B', *args], env=env,
                capture_output=True, text=True, timeout=timeout)
            (evidence/(name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
            if result.returncode or 'ResourceWarning' in result.stderr:
                raise RuntimeError(name+'_failed: '+result.stderr[-1200:])
        index = ['--index-url', 'https://pypi.org/simple']
        if wheelhouse is not None:
            wheelhouse = Path(wheelhouse).resolve(strict=True)
            if not wheelhouse.is_dir(): raise ValueError('wheelhouse_not_directory')
            index = ['--no-index', '--find-links', wheelhouse.as_uri()]
        run('pip-install', ['-m', 'pip', '--isolated', '--disable-pip-version-check', 'install',
            *index, '--no-cache-dir', '--no-compile',
            '--require-hashes', '--only-binary=:all:', '--report', str(evidence/'pip-report.json'),
            '-r', str(ROOT/'distribution/requirements.lock')], timeout=600)
        run('pip-check', ['-m', 'pip', '--isolated', 'check'])
        run('installed', [str(ROOT/'distribution/verify_dependency_install.py'), str(evidence/'installed.json')])
        run('licenses', [str(ROOT/'distribution/license_inventory.py'), str(evidence/'wheel-notices')])
        selected = check_wheels(read_json(evidence/'pip-report.json'), (ROOT/'distribution/requirements.lock').read_text(encoding='utf-8'), read_json(evidence/'installed.json')['installed'], wheelhouse=wheelhouse)
        for name, data in licenses.items():
            target = package/'Runtime~/python-notices'/name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        shutil.copytree(evidence/'wheel-notices', package/'Runtime~/wheel-notices')
        diagnostic = None
        if node_archive is not None:
            backend = load('portable_diagnostic_backend', ROOT/'distribution/diagnostic_backend.py')
            diagnostic = backend.build(node_archive, package/'Runtime~/diagnostics-backend')
            if diagnostic['missing_notice_packages']:
                raise ValueError('diagnostic_notices_incomplete')
            shutil.copyfile(package/'Runtime~/diagnostics-backend/inventory.json',
                evidence/'diagnostic-backend-inventory.json')
        write_launch_descriptor(package, key, pins['python_version'])
        result = {'scope': 'Local portable development runtime, not product/Unity acceptance',
            'diagnostics_included': diagnostic is not None,
            'platform': key, 'dependency_source': 'offline-wheelhouse' if wheelhouse else 'pypi', 'python_archive_sha256': pin['sha256'], 'python_release': pins['release'],
            'executable': str(executable.relative_to(destination)), 'python_identity': observed,
            'python_notice_records': len(pin['licenses']),
            'requirements_sha256': hashlib.sha256((ROOT/'distribution/requirements.lock').read_bytes()).hexdigest(),
            'selected_wheels': selected, 'source_files': len(payload), 'independent_approval': False, 'full_product_accepted': False}
        (evidence/'build.json').write_text(json.dumps(result, indent=2)+'\n')
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise


def extract(archive: Path, destination: Path, expected_hash: str):
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError('archive_hash')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        members = tar.getmembers()
        names = set()
        for item in members:
            parts = item.name.split('/')
            if (not parts or parts[0] != 'python' or '\\' in item.name
                or any(p in ('', '.', '..') or ':' in p or p.endswith((' ', '.'))
                       or p.split('.')[0].upper() in {'CON','NUL','PRN','AUX',
                           *('COM'+str(n) for n in range(1,10)),
                           *('LPT'+str(n) for n in range(1,10))} for p in parts)):
                raise ValueError('archive_path')
            if item.name in names:
                raise ValueError('archive_duplicate')
            names.add(item.name)
            # Validate every member before allocating the owned destination.
            tarfile.data_filter(item, str(destination))
        destination.mkdir()
        try:
            tar.extractall(destination, members=members, filter='data')
        except BaseException:
            shutil.rmtree(destination)
            raise
