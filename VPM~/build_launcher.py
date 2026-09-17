"""Append a reviewed launcher preview without rebuilding historical packages."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

spec=importlib.util.spec_from_file_location('vpm_base',Path(__file__).with_name('build_repository.py'))
assert spec is not None and spec.loader is not None
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
ID='com.yukino.vrchat-agent-launcher'
VERSION='0.1.0-preview.1'
TAG='launcher-v0.1.0-preview.1'
PREFIX='Packages~/'+ID

def build(root):
    root=Path(root).resolve()
    proof=json.loads(base.read_regular(root,'LAUNCHER_VERIFICATION.json'))
    if proof.get('local_checks_passed') is not True or proof.get('independent_source_reviews_passed') is not True or proof.get('unity_verified') is not False:
        raise ValueError('Launcher preview verification gates missing')
    files={}
    for name,digest in proof.get('source_sha256',{}).items():
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name:
            raise ValueError('Unsafe package path')
        if not (name.startswith('Editor/') or name in {'package.json','README.md','LICENSE','THIRD_PARTY_NOTICES.md'} or name.endswith('.meta')):
            raise ValueError('Unexpected package file')
        if any(p in {'.git','__pycache__'} for p in rel.parts) or rel.suffix in {'.pyc','.pfx','.pem','.key'}:
            raise ValueError('Forbidden package content')
        data=base.read_regular(root,PREFIX+'/'+name)
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Reviewed source drift: '+name)
        files[name]=data
    required={'package.json','README.md','LICENSE','THIRD_PARTY_NOTICES.md','Editor/Runtime~/bridge.py','Editor/Runtime~/launcher_supervisor.py','Editor/Runtime~/windows_processes.py'}
    if not required<=files.keys() or not any(n.endswith('.cs') for n in files):raise ValueError('Incomplete launcher')
    manifest=json.loads(files['package.json'])
    if manifest.get('name')!=ID or manifest.get('version')!=VERSION:raise ValueError('Wrong package identity')
    if manifest.get('vpmDependencies')!={'com.yukino.vrchat-readonly-mcp':'0.1.2','com.yukino.vrchat-managed-editing':'0.1.0-preview.2'}:raise ValueError('Wrong VPM dependency')
    if any(k.startswith('legacy') for k in manifest):raise ValueError('Implicit deletion forbidden')
    filename=ID+'-'+VERSION+'.zip'
    manifest.update(url=base.REPO+TAG+'/VPM~/packages/'+filename)
    files['package.json']=base.json_bytes(manifest)
    data=base.zip_bytes(files)
    entry=dict(manifest,zipSHA256=hashlib.sha256(data).hexdigest())
    delta=dict(base.REPO_IDENTITY,packages={ID:{'versions':{VERSION:entry}}})
    existing=json.loads(base.read_regular(root,'index.json'))
    return {filename:data},base.merge_index(existing,delta)

def emit(root):
    root=Path(root).absolute();base.check_output_path(root)
    artifacts,index=build(root)
    targets={root/'VPM~/packages'/n:b for n,b in artifacts.items()}
    index_path=root/'index.json';base.check_output_path(index_path)
    for path,data in targets.items():
        base.check_output_path(path)
        if path.exists() and path.read_bytes()!=data:raise ValueError('Immutable ZIP conflict')
    for path,data in targets.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            with path.open('xb') as f:f.write(data)
    data=base.json_bytes(index)
    if json.loads(index_path.read_bytes())!=index:
        with tempfile.NamedTemporaryFile(dir=root,prefix='.launcher-index-',delete=False) as f:
            temp=Path(f.name)
            try:f.write(data);f.flush();os.fsync(f.fileno())
            except BaseException:temp.unlink(missing_ok=True);raise
        try:os.replace(temp,index_path)
        finally:temp.unlink(missing_ok=True)
    return {p.name:hashlib.sha256(b).hexdigest() for p,b in targets.items()}

if __name__=='__main__':
    print(json.dumps(emit(Path(__file__).resolve().parents[1]),indent=2))
