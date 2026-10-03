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
        home = Path(runtime_environment['USERPROFILE'])
        result['APPDATA'] = str(home/'AppData/Roaming')
        result['LOCALAPPDATA'] = str(home/'AppData/Local')
    return result


def compile_fixture(command, runtime_environment, report, timeout=90):
    try:
        result = subprocess.run(command, env=compile_environment(runtime_environment),
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        text = lambda value: value.decode('utf-8', errors='backslashreplace') if isinstance(value, bytes) else (value or '')
        report['csharp_build'] = {'code': None, 'timed_out': True, 'timeout_seconds': timeout,
            'stdout': text(exc.stdout), 'stderr': text(exc.stderr)}
        raise
    report['csharp_build'] = {'code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
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


def regression_arguments(suite):
    # The real console case remains mandatory on Windows; Linux cannot execute it.
    if suite == 'test_private_process_pipes.py' and sys.platform == 'linux':
        return [
            'PrivatePipes.test_PP001_owned_child_roundtrip_preserves_private_pipe_ownership',
            'PrivatePipes.test_PP002_reader_is_bounded_and_cancellable',
            'PrivatePipes.test_PP003_visible_console_is_explicit_and_never_mixed_with_stdio']
    return []


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--dotnet',required=True,type=Path)
    parser.add_argument('--wheelhouse', type=Path)
    parser.add_argument('--node-archive',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    spec=importlib.util.spec_from_file_location('portable',ROOT/'distribution/portable_python.py')
    assert spec is not None and spec.loader is not None
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert hasattr(module,'build'),'portable runtime assembly not implemented'
    freeze=[ROOT/name for name in json.loads((ROOT/'distribution/source-inputs.json').read_text())['files']]
    freeze += list((ROOT/'tests').glob('*.py'))+list((ROOT/'distribution').rglob('*'))+list((ROOT/'tests/unity-core').glob('*.cs'))+list((ROOT/'tests/unity-core').glob('*.csproj'))+[Path(__file__), ROOT.parent/'VPM~/build_repository.py', ROOT/'build_candidate.py']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in freeze if p.is_file() and '__pycache__' not in p.parts}
    def inventory(folder):
        return {str(p.relative_to(folder)): ('link:'+os.readlink(p) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
    report={'scope':'Parent isolated portable CPython, locks and C# process/SDK; synthetic Unity wire, not Unity/product approval','passed':False}
    with recorded_directory(report, args.output) as work:
        built=module.build(args.archive,work/'initial',wheelhouse=args.wheelhouse,node_archive=args.node_archive)
        relocated=work/'relocated';(work/'initial').rename(relocated)
        executable=relocated/built['executable']
        before=inventory(relocated/'package')
        report['build']=built
        # Prove relocation, not merely execution at the initial build path.
        report['relocated_identity']=module.identity(executable)
        assert report['relocated_identity']['prefix']==str(executable.parent if os.name=='nt' else executable.parent.parent)
        report['relocation_verified']=True
        env=module.clean_environment(work)
        if args.node_archive is not None:
            diagnostic_inventory=relocated/'evidence/diagnostic-backend-inventory.json'
            assert diagnostic_inventory.is_file(),'diagnostic_provenance_not_retained'
            report['diagnostic_inventory']=json.loads(diagnostic_inventory.read_bytes())
            assert not report['diagnostic_inventory']['missing_notice_packages']
            diagnostic_output=work/'diagnostic-check.json'
            probe=('import importlib.util,json;from pathlib import Path;'
                's=importlib.util.spec_from_file_location("diagnostic_check",'+repr(str(ROOT/'tests/verify_diagnostic_backend.py'))+');'
                'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);r={};'
                'm.verify_payload(Path('+repr(str(relocated/'package/Runtime~'))+'),Path('+repr(str(work.resolve()))+'),r);'
                'Path('+repr(str(diagnostic_output))+').write_text(json.dumps(r),encoding="utf-8")')
            diagnostic_run=subprocess.run([str(executable),'-I','-B','-W','always::ResourceWarning','-c',probe],
                env=env,capture_output=True,text=True,timeout=60)
            report['diagnostic']={'exit_code':diagnostic_run.returncode,'stdout':diagnostic_run.stdout,'stderr':diagnostic_run.stderr}
            assert diagnostic_run.returncode==0 and 'ResourceWarning:' not in diagnostic_run.stderr
            report['diagnostic']['result']=json.loads(diagnostic_output.read_bytes())
            assert report['diagnostic']['result']['native_read_write_denial_revoke_passed'] and report['diagnostic']['result']['tamper_rejected']
        read_probe=('import sys,asyncio;sys.path[:0]='+repr([str(relocated/'package/Runtime~'/p) for p in
            ('runtime','native/src','dependencies/mcp-1.29.1')])+'\n'
            'from candidate_runtime import create_server\nfrom fastmcp import Client\n'
            'async def check():\n'
            ' async with Client(create_server("relocated-console-fixture")) as client:\n'
            '  tools={t.name for t in await client.list_tools()};assert "read_console" in tools\n'
            '  for action in ("get","clear"):\n'
            '   r=await client.call_tool("read_console",{"action":action,"format":"json","page_size":2},raise_on_error=False);assert r.is_error\n'
            'asyncio.run(check());print("PASS relocated-console-discovery-default-deny")')
        probe=subprocess.run([str(executable),'-I','-B','-W','always::ResourceWarning','-c',read_probe],
            env=env,capture_output=True,text=True,timeout=30)
        report['console_payload']={'exit_code':probe.returncode,'stdout':probe.stdout,'stderr':probe.stderr}
        assert probe.returncode==0 and 'PASS relocated-console-discovery-default-deny' in probe.stdout and 'ResourceWarning:' not in probe.stderr
        out=work/'dotnet';csproj=ROOT/'tests/unity-core/EditorBootstrapCases.csproj'
        command=[str(args.dotnet),'build',str(csproj),'-c','Release','--disable-build-servers','-p:UseSharedCompilation=false','-p:NuGetAudit=false','-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),'-p:BaseIntermediateOutputPath='+str(work/'obj')+os.sep,'-o',str(out)]
        build=compile_fixture(command,env,report)
        assert build.returncode==0,build.stdout+build.stderr
        selection=subprocess.run([str(args.dotnet),str(out/'EditorBootstrapCases.dll'),'--selection-tests'],env=env,capture_output=True,text=True,timeout=20)
        report['selection']={'code':selection.returncode,'stdout':selection.stdout,'stderr':selection.stderr}
        assert selection.returncode==0 and all('PASS PS00'+str(i) in selection.stdout for i in range(1,5)),selection.stdout+selection.stderr
        async def execute_csharp():
            tracker=None
            if sys.platform=='linux':
                from owned_descendants import Descendants
                tracker=Descendants()
            done=asyncio.Event()
            proc=await asyncio.create_subprocess_exec(str(args.dotnet),str(out/'EditorBootstrapCases.dll'),str(relocated/'package'),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
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
        report['csharp']={'code':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'entry_mode':'default-package-relative'}
        assert run.returncode==0 and 'PASS ECP001' in run.stdout and 'PASS ECP002' in run.stdout,run.stdout+run.stderr
        report['regressions']=[]
        suites=['test_run_identity.py','test_bootstrap_runtime.py','test_owned_launcher.py','test_editor_owner.py','test_private_process_pipes.py','test_editor_delivery.py','test_tls_windows.py' if os.name=='nt' else 'test_tls_context.py']
        for suite in suites:
            result=subprocess.run([str(executable),'-I','-B','-W','always::ResourceWarning',str(ROOT/'tests'/suite),*regression_arguments(suite),'-v'],env=env,capture_output=True,text=True,timeout=120)
            report['regressions'].append({'suite':suite,'selected_methods':regression_arguments(suite) or 'all', 'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
            assert result.returncode==0 and 'ResourceWarning' not in result.stderr and 'skipped=' not in result.stderr,result.stderr
        if os.name == 'nt' and args.node_archive is not None:
            diagnostic_console = subprocess.run([str(executable), '-I', '-B', '-W', 'always::ResourceWarning',
                str(ROOT/'tests/test_diagnostics_windows_cli.py'), str(relocated/'package/Runtime~')],
                env=env, capture_output=True, text=True, timeout=120)
            report['windows_diagnostic_console'] = {'code': diagnostic_console.returncode,
                'stdout': diagnostic_console.stdout, 'stderr': diagnostic_console.stderr,
                'scope': 'real Windows console + fixture operator; no native client/human claim'}
            assert diagnostic_console.returncode == 0 and 'ResourceWarning:' not in diagnostic_console.stderr
            receipts = [json.loads(line.split('=', 1)[1]) for line in diagnostic_console.stdout.splitlines()
                if line.startswith('WINDOWS_DIAGNOSTIC_CONSOLE=')]
            assert len(receipts) == 1 and len(receipts[0]) == 3
            assert {row['case'].split('.test_')[1].split('_')[0] for row in receipts[0]} == {'DW001', 'DW002', 'DW003'}
            assert all(row['normal_exit'] and row['job_empty_before_cleanup'] and row['temporary_root_absent']
                and row['source_unchanged'] and row['human_approval_verified'] is False for row in receipts[0])
            report['windows_diagnostic_console']['receipts'] = receipts[0]
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
