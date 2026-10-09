"""Exact OS-peer tests in existing owned processes, not Editor reload acceptance.

Usage: pinned-python -I -B tests/verify_peer.py LABEL
Windows uses the production atomic Job birth/cleanup; Linux uses its existing
pidfd/process-group fixture owner. Evidence retains which kernel actually ran.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
SOURCES=['launcher/peer_identity.py','launcher/peer_channel.py','launcher/windows_processes.py',
    'launcher/linux_processes.py','launcher/candidate_launch.py','launcher/direct_python.py',
    'launcher/cli.py','tests/test_peer_identity.py','tests/test_peer_channel.py','tests/verify_peer.py',
    'evidence/runtime-fix-run.py']
SUITES={'test_peer_identity.py':('PI',4),'test_peer_channel.py':('OS',11),'test_reload_control.py':('OC',15)}

SOURCES=sorted(set(SOURCES)|{'distribution/source-inputs.json','tests/test_reload_control.py',
    'tests/test_runtime_handoff.py','tests/test_runtime_unity_auth.py','tests/test_runtime_http.py'}|
    set(json.loads((ROOT/'distribution/source-inputs.json').read_bytes())['files'])|
    {p.relative_to(ROOT).as_posix() for directory in ('runtime','launcher') for p in (ROOT/directory).glob('*.py')})


def case_passed(row, methods):
    result=row.get('result') or {}
    return (row.get('exit_code')==0 and row.get('timed_out') is False
        and all(row.get(key) is True for key in ('natural_tree_exit','cleanup_complete','temporary_home_absent'))
        and len(methods)>0 and len(methods)==len(set(methods))
        and sorted(result.get('ids',[]))==sorted(methods) and result.get('tests')==len(methods)
        and result.get('skipped')==[] and result.get('errors')==[] and result.get('failures')==[]
        and 'ResourceWarning' not in row.get('stdout','')+row.get('stderr',''))


def natural_tree_exit(owner, child):
    if child.poll() is None:
        return False
    if os.name=='nt':
        return owner.api.job_empty(owner.job)
    # The existing Linux owner intentionally pins the unreaped group leader.
    # No OTHER process (including zombie descendants) may remain in that group.
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==child.pid:
            continue
        try:
            fields=(p/'stat').read_bytes().rsplit(b') ',1)[1].split()
        except FileNotFoundError:
            continue
        if int(fields[2])==child.pid:
            return False
    return True


def run_case(script, child_code, *, filters=()):
    from launcher.candidate_launch import make_owner,child_environment
    from launcher.direct_python import current,environment_hint
    row={'exit_code':None,'timed_out':False,'natural_tree_exit':False,'cleanup_complete':False,
        'temporary_home_absent':False,'stdout':'','stderr':'','result':None}
    stderr=[]
    home=None
    try:
        with tempfile.TemporaryDirectory(prefix='peer-verifier-') as home:
            env=child_environment()
            env.update({key:home for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR')})
            env.update(environment_hint())
            owner=make_owner(os.getpid())
            try:
                with open(os.devnull,'rb') as stdin, tempfile.TemporaryFile() as stdout:
                    child=owner.spawn([current()['executable'],'-I','-B','-W','always::ResourceWarning',
                        '-c',child_code,str(script),'-',*filters],env,stderr.append,stdio=(stdin.fileno(),stdout.fileno()))
                    deadline=time.monotonic()+40
                    while child.poll() is None and time.monotonic()<deadline:
                        time.sleep(.02)
                    row['exit_code']=child.poll()
                    row['timed_out']=row['exit_code'] is None
                    row['natural_tree_exit']=natural_tree_exit(owner,child)
                    row['cleanup_complete']=owner.close()
                    stdout.seek(0)
                    row['stdout']=stdout.read().decode('utf-8','replace')
            finally:
                row['cleanup_complete']=owner.close()
    finally:
        row['temporary_home_absent']=home is not None and not Path(home).exists()
        row['stderr']='\n'.join(stderr)
    lines=[line.removeprefix('FIX_RESULT=') for line in row['stdout'].splitlines() if line.startswith('FIX_RESULT=')]
    if len(lines)==1:
        row['result']=json.loads(lines[0])
    return row


def main():
    if len(sys.argv)!=2 or re.fullmatch(r'[a-z0-9-]+',sys.argv[1]) is None:
        raise SystemExit('LABEL required')
    destination=ROOT/'evidence'/('peer-checked-'+sys.argv[1]+'.json')
    if destination.exists():
        raise SystemExit('Refusing to overwrite evidence')
    sys.path.insert(0,str(ROOT))
    spec=importlib.util.spec_from_file_location('bounded_fixture',ROOT/'evidence/runtime-fix-run.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def hashes():
        return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}
    report={'platform':sys.platform,'scope':'OS peer + owned runtime TLS handoff; Editor grant/evidence fixtures, not actual Editor reload',
        'source_before':hashes(),'rows':[],'passed':False}
    try:
        for name,(prefix,count) in SUITES.items():
            script=ROOT/'tests'/name
            tree=ast.parse(script.read_bytes())
            methods=['runtime_fix_tests.'+node.name+'.'+method.name for node in tree.body if isinstance(node,ast.ClassDef)
                for method in node.body if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)) and method.name.startswith('test_')]
            assert sorted(m.split('.test_')[1].split('_')[0] for m in methods)==[f'{prefix}{i:03}' for i in range(1,count+1)]
            for method in methods:
                row=run_case(script,module.CHILD,filters=(method,))
                row.update(file=name,expected=[method],passed=case_passed(row,[method]))
                report['rows'].append(row)
                destination.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    except Exception as error:
        report['error_type']=type(error).__name__
    finally:
        report['source_after']=hashes()
        report['passed']=(len(report['rows'])==sum(count for _,count in SUITES.values()) and all(row['passed'] for row in report['rows'])
            and report['source_before']==report['source_after'] and 'error_type' not in report)
        destination.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('platform','scope','passed')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
