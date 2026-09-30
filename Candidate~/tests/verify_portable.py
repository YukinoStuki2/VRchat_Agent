"""Real PBS + locked wheels + copied Candidate source; not Unity acceptance."""
from pathlib import Path
import argparse
from contextlib import contextmanager
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def compile_environment(runtime_environment):
    result = dict(runtime_environment)
    if sys.platform == 'win32':
        for key in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramData'):
            value = os.environ.get(key)
            if value:
                result[key] = value
    return result


@contextmanager
def recorded_directory(report, output):
    work = None
    try:
        with tempfile.TemporaryDirectory(prefix='candidate-portable-') as td:
            work = Path(td)
            report['temporary_root'] = str(work)
            yield work
    finally:
        report['temporary_root_absent'] = work is not None and not work.exists()
        if not report['temporary_root_absent']:
            report['passed'] = False
        output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--dotnet',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    spec=importlib.util.spec_from_file_location('portable',ROOT/'distribution/portable_python.py')
    assert spec is not None and spec.loader is not None
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert hasattr(module,'build'),'portable runtime assembly not implemented'
    freeze=[ROOT/name for name in json.loads((ROOT/'distribution/source-inputs.json').read_text())['files']]
    freeze += list((ROOT/'tests').glob('*.py'))+list((ROOT/'distribution').rglob('*'))+list((ROOT/'tests/unity-core').glob('*.cs'))+[Path(__file__), ROOT.parent/'VPM~/build_repository.py', ROOT/'build_candidate.py']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in freeze if p.is_file() and '__pycache__' not in p.parts}
    def inventory(folder):
        return {str(p.relative_to(folder)): ('link:'+os.readlink(p) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
    report={'scope':'Parent isolated portable CPython, locks and C# process/SDK; synthetic Unity wire, not Unity/product approval','passed':False}
    with recorded_directory(report, args.output) as work:
        built=module.build(args.archive,work/'initial')
        relocated=work/'relocated';(work/'initial').rename(relocated)
        executable=relocated/built['executable']
        before=inventory(relocated/'package')
        report['build']=built
        # Prove relocation, not merely execution at the initial build path.
        report['relocated_identity']=module.identity(executable)
        assert report['relocated_identity']['prefix']==str(executable.parent if os.name=='nt' else executable.parent.parent)
        report['relocation_verified']=True
        env=module.clean_environment(work)
        out=work/'dotnet';csproj=ROOT/'tests/unity-core/EditorBootstrapCases.csproj'
        command=[str(args.dotnet),'build',str(csproj),'-c','Release','--disable-build-servers','-p:UseSharedCompilation=false','-p:NuGetAudit=false','-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),'-p:BaseIntermediateOutputPath='+str(work/'obj')+os.sep,'-o',str(out)]
        build=subprocess.run(command,env=compile_environment(env),capture_output=True,text=True,timeout=90)
        report['csharp_build']={'code':build.returncode,'stdout':build.stdout,'stderr':build.stderr}
        assert build.returncode==0,build.stdout+build.stderr
        async def execute_csharp():
            tracker=None
            if sys.platform=='linux':
                from owned_descendants import Descendants
                tracker=Descendants()
            done=asyncio.Event()
            proc=await asyncio.create_subprocess_exec(str(args.dotnet),str(out/'EditorBootstrapCases.dll'),str(executable),str(relocated/'package/Runtime~/launcher/editor_owner.py'),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            watch=asyncio.create_task(tracker.watch(proc.pid,done)) if tracker else None
            try:
                stdout,stderr=await asyncio.wait_for(proc.communicate(),90)
            except TimeoutError:
                proc.kill();stdout,stderr=await proc.communicate()
            finally:
                done.set()
                if watch:await watch
            if tracker:
                report['descendants']=await tracker.finish()
                assert report['descendants']['clean']
            return subprocess.CompletedProcess([],proc.returncode,stdout.decode(),stderr.decode())
        sys.path.insert(0,str(ROOT/'tests'))
        run=asyncio.run(execute_csharp())
        report['csharp']={'code':run.returncode,'stdout':run.stdout,'stderr':run.stderr}
        assert run.returncode==0 and 'PASS ECP001' in run.stdout and 'PASS ECP002' in run.stdout,run.stdout+run.stderr
        report['regressions']=[]
        suites=['test_run_identity.py','test_bootstrap_runtime.py','test_owned_launcher.py','test_editor_owner.py','test_tls_windows.py' if os.name=='nt' else 'test_tls_context.py']
        for suite in suites:
            result=subprocess.run([str(executable),'-I','-B','-W','always::ResourceWarning',str(ROOT/'tests'/suite)],env=env,capture_output=True,text=True,timeout=120)
            report['regressions'].append({'suite':suite,'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
            assert result.returncode==0 and 'ResourceWarning' not in result.stderr and 'skipped=' not in result.stderr,result.stderr
        # Keep real pip/installed/notice records, not only counts.
        for item in (relocated/'evidence').iterdir():
            destination=args.output.parent/(args.output.stem+'-'+item.name)
            if destination.exists():raise FileExistsError(destination)
            if item.is_dir():shutil.copytree(item,destination)
            else:shutil.copy2(item,destination)
        report['payload_unchanged']=(inventory(relocated/'package')==before)
        report['payload_inventory']=before
        report['source_sha256']=hashes
        report['source_unchanged']=all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
        assert report['payload_unchanged'] and report['source_unchanged']
        report['passed']=True
    print(json.dumps({'passed':report['passed'],'temporary_root_absent':report['temporary_root_absent'],'evidence':str(args.output)}))

if __name__=='__main__':main()
