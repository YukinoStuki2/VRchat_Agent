"""Bounded targeted gates; native job characterization has a separate runner."""
from pathlib import Path
import hashlib,json,os,re,signal,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from verify_unity import DOTNET,TESTS,hashes as unity_hashes

def hashes():
    result=unity_hashes()
    for name in ('tests/verify_effect_gate.py','tests/review_import_pipe.py','diagnostics/asset_review.py','diagnostics/snapshot.py','diagnostics/windows_handles.py'):
        result[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    for path in (ROOT/'launcher').glob('*.py'):
        result[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def main(label,projects):
    assert re.fullmatch('[a-zA-Z0-9_-]{1,100}',label)
    assert projects and set(projects)<={'PluginSessionCases','PluginTrustCases','CleanupLifetimeCases','PrefabGateCases','AssetReviewCases','AssetGateCases','EffectGateCases','CoreTests','AdapterTests','ContinuityCases','ReloadCases','JobObservationCases','ReviewCaptureCases'}
    output=ROOT/'evidence'/('effect-gates-'+label+'.json')
    assert not output.exists(),'old evidence must remain'
    report={'before':hashes(),'runs':[],'product_accepted':False}
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def run(name,argv,env):
        proc=subprocess.Popen([str(x) for x in argv],env=env,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        timed=False
        try:out,err=proc.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(proc.pid,signal.SIGKILL);out,err=proc.communicate(timeout=10)
        residual=False
        try:os.killpg(proc.pid,0);residual=True
        except ProcessLookupError:pass
        if residual:os.killpg(proc.pid,signal.SIGKILL)
        report['runs'].append({'name':name,'exit_code':proc.returncode,'stdout':out,'stderr':err,'timeout':timed,'pid_absent':not Path(f'/proc/{proc.pid}').exists(),'group_absent':not residual})
        save();print(json.dumps({'name':name,'exit_code':proc.returncode}),flush=True)
        if proc.returncode:print(out,err,flush=True)
        return proc.returncode==0
    td=None
    try:
        with tempfile.TemporaryDirectory(prefix='vragent-effects-targeted-') as td:
            env={'PATH':'/usr/bin:/bin','HOME':td,'TMPDIR':td,'LANG':'C.UTF-8','DOTNET_ROOT':str(DOTNET.parent),'DOTNET_CLI_HOME':td,'DOTNET_NOLOGO':'1','DOTNET_CLI_TELEMETRY_OPTOUT':'1','MSBUILDDISABLENODEREUSE':'1'}
            for name in projects:
                work=Path(td)/name
                if run(name+'-build',[DOTNET,'build',TESTS/(name+'.csproj'),'-c','Release','--disable-build-servers','-p:UseSharedCompilation=false','-p:BaseIntermediateOutputPath='+str(work/'obj')+'/','-p:BaseOutputPath='+str(work/'bin')+'/','-p:RestoreConfigFile='+str(TESTS/'ReviewNuGet.Config'),'-p:NuGetAudit=false'],env):
                    if name=='JobObservationCases':
                        for i in range(1,6):run(f'JO{i:03d}',[DOTNET,work/'bin/Release/net8.0'/(name+'.dll'),f'JO{i:03d}'],env)
                    else:run(name,[DOTNET,work/'bin/Release/net8.0'/(name+'.dll')]+([sys.executable,ROOT] if name=='ReviewCaptureCases' else []),env)
                    if name=='AssetReviewCases':
                        run('AR007-pipe',[sys.executable,'-I','-B',ROOT/'tests/review_import_pipe.py',DOTNET,work/'bin/Release/net8.0'/(name+'.dll')],env)
    finally:
        report['after']=hashes();report['source_unchanged']=report['after']==report['before'];report['build_root_absent']=td is not None and not Path(td).exists();save()
    report['pass_ids']=re.findall(r'^PASS ([A-Z]+\d{3})(?: |_)','\n'.join(x['stdout'] for x in report['runs']),re.M)
    report['warnings']=[line for row in report['runs'] for line in (row['stdout']+'\n'+row['stderr']).splitlines() if re.search(r'ResourceWarning|(?i:\bwarning\s+[A-Z]+\d+:)',line)]
    report['passed']=len(report['runs'])==len(projects)*2+(4 if 'JobObservationCases' in projects else 0)+(1 if 'AssetReviewCases' in projects else 0) and report['source_unchanged'] and report['build_root_absent'] and not report['warnings'] and all(r['exit_code']==0 and not r['timeout'] and r['pid_absent'] and r['group_absent'] for r in report['runs'])
    if 'PluginSessionCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('PS')]==['PS001','PS002','PS003','PS004','PS008','PS005','PS006','PS007']
    if 'PluginTrustCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('PT')]==['PT001','PT002','PT003']
    if 'CleanupLifetimeCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('CD')]==['CD001','CD002','CD003','CD004','CD005','CD006','CD007','CD008']
    if 'PrefabGateCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('PG')]==['PG001','PG002','PG003','PG004','PG005','PG006','PG007','PG008','PG009']
    if 'AssetReviewCases' in projects:report['passed'] &= sorted(i for i in report['pass_ids'] if i.startswith('AR'))==['AR001','AR002','AR003','AR004','AR005','AR006','AR007','AR008']
    if 'AssetGateCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('AG')]==[f'AG{i:03d}' for i in range(1,8)]
    if 'EffectGateCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('EG')]==[f'EG{i:03d}' for i in range(1,5)]
    if 'JobObservationCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('JO')]==[f'JO{i:03d}' for i in range(1,6)]
    if 'ReviewCaptureCases' in projects:report['passed'] &= [i for i in report['pass_ids'] if i.startswith('RC')]==['RC001','RC002','RC003','RC004','RC005']
    save();print(json.dumps({k:report[k] for k in ('passed','source_unchanged','build_root_absent','pass_ids')}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1],sys.argv[2:]))
