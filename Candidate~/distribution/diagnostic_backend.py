"""Pinned standalone diagnostic payload builder, not VPM or product approval.
Build-only npm ci restores exact integrity-locked packages without lifecycle scripts.
The shipped runtime uses only bundled Node and never invokes npm or downloads.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def _path(name, prefix):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name.rstrip('/') or
            path.parts[0] != prefix or '\\' in name or
            any(p in ('', '.', '..') or ':' in p or p.endswith((' ', '.'))
                for p in path.parts)):
        raise ValueError('node_archive_path')
    return path


def build(archive, destination):
    system = platform.system().lower()
    if system not in ('windows', 'linux') or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise ValueError('unsupported_platform')
    key = system + '-x86_64'
    pins = json.loads((ROOT/'distribution/diagnostics-backend.lock.json').read_bytes())
    pin = pins['platforms'][key]
    archive = Path(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != pin['sha256']:
        raise ValueError('node_archive_hash')
    source = ROOT/'dependencies/filesystem-0.6.3'
    # Reuse the package assembler's existing regular-file/path boundary.
    spec = importlib.util.spec_from_file_location('diagnostic_portable_helpers',ROOT/'distribution/portable_python.py')
    assert spec is not None and spec.loader is not None
    portable = importlib.util.module_from_spec(spec); spec.loader.exec_module(portable)
    assemble = portable.load('diagnostic_source_helpers', ROOT/'distribution/assemble_source.py')
    inputs = {}
    for name, digest in pins['inputs'].items():
        data = assemble.packer.base.read_regular(source, name)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('filesystem_source_drift')
        inputs[name] = data
    destination = Path(destination).absolute()
    destination.mkdir()  # Refuse any existing directory/file/link.
    try:
        with tempfile.TemporaryDirectory(prefix='build-',dir=destination) as temporary:
            work = Path(temporary)
            extraction = work/'node'; extraction.mkdir()
            names = set()
            if system == 'linux':
                with tarfile.open(archive, mode='r:xz') as bundle:
                    for member in bundle.getmembers():
                        path = str(_path(member.name, pin['prefix']))
                        if path.casefold() in names: raise ValueError('node_archive_alias')
                        names.add(path.casefold())
                        tarfile.data_filter(member, str(extraction))
                    bundle.extractall(extraction,filter='data')
            else:
                with zipfile.ZipFile(archive) as bundle:
                    for member in bundle.infolist():
                        path = str(_path(member.filename, pin['prefix']))
                        if path.casefold() in names or stat.S_ISLNK(member.external_attr >> 16):
                            raise ValueError('node_archive_alias_or_link')
                        names.add(path.casefold())
                    bundle.extractall(extraction)
            extracted = extraction/pin['prefix']
            node = extracted/('node.exe' if system=='windows' else 'bin/node')
            npm = extracted/('node_modules/npm/bin/npm-cli.js' if system=='windows' else 'lib/node_modules/npm/bin/npm-cli.js')
            env = portable.clean_environment(work)
            env['PATH'] = str(node.parent) + os.pathsep + os.defpath
            env['NPM_CONFIG_USERCONFIG'] = str(work/'npm-userconfig')
            env['NPM_CONFIG_GLOBALCONFIG'] = str(work/'npm-globalconfig')
            env['NPM_CONFIG_CACHE'] = str(work/'npm-cache')
            for name in ('npm-userconfig','npm-globalconfig'): (work/name).write_text('',encoding='utf-8')
            version = subprocess.run([str(node),'--version'],env=env,capture_output=True,text=True,timeout=15,check=True)
            if version.stdout.strip() != 'v'+pins['node_version']:
                raise ValueError('node_version_mismatch')
            install = work/'install'; install.mkdir()
            for name in ('package.json','package-lock.json'): (install/name).write_bytes(inputs[name])
            run = subprocess.run([str(node),str(npm),'ci','--ignore-scripts','--no-audit','--no-fund','--no-progress'],
                env=env,cwd=install,capture_output=True,text=True,timeout=180)
            if run.returncode: raise RuntimeError('pinned_npm_ci_failed')
            if (install/'package-lock.json').read_bytes()!=inputs['package-lock.json']:
                raise ValueError('npm_lock_changed')
            tree = subprocess.run([str(node),str(npm),'ls','--all','--json'],env=env,cwd=install,
                capture_output=True,text=True,timeout=25)
            if tree.returncode: raise RuntimeError('installed_npm_graph_invalid')
            lock = json.loads(inputs['package-lock.json'])
            notices = []
            for relative, package in lock['packages'].items():
                if not relative: continue
                if not relative.startswith('node_modules/') or '..' in PurePosixPath(relative).parts:
                    raise ValueError('npm_lock_path')
                directory = install/relative
                actual = json.loads((directory/'package.json').read_bytes())
                if actual['version'] != package['version']: raise ValueError('npm_version_mismatch')
                license_files = [p for p in directory.iterdir() if p.is_file() and
                    p.name.lower().split('.')[0] in ('license','licence','copying','notice','copyright')]
                notices.append({'package':relative,'version':actual['version'],
                    'declared_license':actual.get('license'),
                    'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in license_files}})
            filesystem = destination/'filesystem'; filesystem.mkdir()
            for name in ('package.json','package-lock.json','LICENSE','path-identity.patch'):
                (filesystem/name).write_bytes(inputs[name])
            for name,data in inputs.items():
                if name.startswith('src/filesystem/'):
                    target=filesystem/Path(name).relative_to('src/filesystem')
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            # Preserve the runtime package's ESM declaration; root lock stays provenance-only.
            (filesystem/'package.json').write_bytes(inputs['src/filesystem/package.json'])
            shutil.copytree(install/'node_modules',filesystem/'node_modules',ignore=shutil.ignore_patterns('.bin'),symlinks=True)
            for item in (filesystem/'node_modules').rglob('*'):
                if item.is_symlink(): raise ValueError('npm_payload_link')
            output_node = destination/'node';output_node.mkdir()
            shutil.copy2(node,output_node/node.name)
            shutil.copyfile(extracted/'LICENSE',output_node/'LICENSE')
        files = {p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(destination.rglob('*')) if p.is_file()}
        report = {'schema':1,'platform':key,'node_version':pins['node_version'],
            'node_archive_sha256':pin['sha256'],'upstream_commit':pins['upstream_commit'],
            'source_inputs':pins['inputs'],'npm_package_count':len(notices),'notices':notices,
            'missing_notice_packages':[n['package'] for n in notices if not n['files']],
            'node_executable':'node/'+('node.exe' if system=='windows' else 'node'),
            'entry':'filesystem/dist/index.js','files':files,'product_approved':False}
        (destination/'inventory.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(destination)
        raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('node_archive');parser.add_argument('destination')
    args=parser.parse_args()
    report=build(args.node_archive,args.destination)
    print(json.dumps({k:v for k,v in report.items() if k not in ('files','notices','source_inputs')}))
