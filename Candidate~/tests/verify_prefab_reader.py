"""Compile and exercise the actual shipped candidate reader, with Unity API doubles.
No real Unity, client authorization, independent review or product acceptance.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from launcher.candidate_launch import make_owner
from verify_peer import natural_tree_exit
from verify_unity import DOTNET
NATIVE=Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity/Editor')
PINS=json.loads((ROOT/'evidence/native-prefab-effects-20261008-pins.json').read_bytes())
FIXTURE=ROOT/'tests/unity-core/PrefabReadCases.cs'
EXPECTED=['PR001','PR002','PR003','PR004','PR005','PR006','PR007','PR008','PR009','PR010']

def extract(name,methods):
    lines=(NATIVE/name).read_text(encoding='utf-8').splitlines(keepends=True)
    pieces=[];hashes={}
    for method in methods:
        starts=[i for i,line in enumerate(lines) if line.startswith('        ') and ('private static ' in line or 'public static ' in line) and ' '+method+'(' in line]
        assert len(starts)==1,'ambiguous method'
        a=starts[0];b=next(i for i in range(a+1,len(lines)) if lines[i].rstrip()=='        }')
        part=''.join(lines[a:b+1]);pieces.append(part);hashes[method]=hashlib.sha256(part.encode()).hexdigest()
    return '\n'.join(pieces),hashes

def main(label):
    assert re.fullmatch('[a-z0-9-]+',label)
    output=ROOT/'evidence'/('prefab-reader-'+label+'.json');assert not output.exists()
    def hashes():return {**{n:hashlib.sha256((NATIVE/n).read_bytes()).hexdigest() for n in PINS['pins']},'fixture':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),'runner':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),**{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'package/Editor/ScopedPrefabs').glob('*') if p.is_file()},**{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'distribution').glob('materialize_prefabs.py')}}
    before=hashes();assert all(before[n]==h for n,h in PINS['pins'].items()),'fixed native source drift'
    report={'scope':__doc__,'upstream_commit':PINS['commit'],'before':before,'runs':[],'product_accepted':False}
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    td=None
    try:
        with tempfile.TemporaryDirectory(prefix='vragent-prefab-characterization-') as td:
            work=Path(td)
            shipped=ROOT/'package/Editor/ScopedPrefabs'
            if shipped.exists():
                from distribution.materialize_prefabs import materialize
                generated=work/'additive';report['provenance']=materialize(NATIVE.parent,generated)
                assert {p.name:p.read_bytes() for p in shipped.iterdir()}=={p.name:p.read_bytes() for p in generated.iterdir()},'shipped reader differs from generated source'
                (work/'CandidateScopedPrefabs.cs').write_bytes((shipped/'CandidateScopedPrefabs.cs').read_bytes())
            for src,dest in [(NATIVE/'Helpers/Response.cs','Response.cs'),(FIXTURE,'Fixture.cs')]:
                (work/dest).write_bytes(src.read_bytes())
            (work/'PrefabEffects.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><LangVersion>9.0</LangVersion><ImplicitUsings>disable</ImplicitUsings><Nullable>disable</Nullable><UseSharedCompilation>false</UseSharedCompilation><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup><Compile Include="*.cs" /><Reference Include="Newtonsoft.Json"><HintPath>$(MSBuildSDKsPath)/../Newtonsoft.Json.dll</HintPath></Reference></ItemGroup></Project>''')
            env={'PATH':'/usr/bin:/bin','HOME':td,'TMPDIR':td,'LANG':'C.UTF-8','DOTNET_ROOT':str(DOTNET.parent),'DOTNET_CLI_HOME':td,'DOTNET_NOLOGO':'1','DOTNET_CLI_TELEMETRY_OPTOUT':'1','MSBUILDDISABLENODEREUSE':'1'}
            def run(name,args):
                owner=make_owner(os.getpid());stderr=[];row={'name':name}
                try:
                    with open(os.devnull,'rb') as stdin,tempfile.TemporaryFile() as stdout:
                        proc=owner.spawn([str(x) for x in args],env,stderr.append,stdio=(stdin.fileno(),stdout.fileno()))
                        deadline=time.monotonic()+(90 if name=='build' else 15)
                        while proc.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                        row.update(exit_code=proc.poll(),timeout=proc.poll() is None,natural_tree_exit=natural_tree_exit(owner,proc))
                        row['cleanup_complete']=owner.close();stdout.seek(0);row['stdout']=stdout.read().decode('utf-8','replace')
                finally:
                    row['cleanup_complete']=owner.close();row['stderr']='\n'.join(stderr);report['runs'].append(row);save()
                print(json.dumps({k:row[k] for k in ('name','exit_code','timeout','cleanup_complete')}),flush=True)
                return row['exit_code']
            if run('build',[DOTNET,'build',work/'PrefabEffects.csproj','-c','Release','--disable-build-servers','-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),'-p:NuGetAudit=false'])==0:
                dll=work/'bin/Release/net8.0/PrefabEffects.dll'
                for case in EXPECTED:run(case,[DOTNET,dll,case])
    except Exception as exc:report['error_type']=type(exc).__name__
    finally:
        report['after']=hashes();report['source_unchanged']=report['before']==report['after'];report['build_root_absent']=td is not None and not Path(td).exists()
        report['pass_ids']=re.findall(r'^PASS (PR\d{3}) ','\n'.join(row.get('stdout','') for row in report['runs']),re.M)
        warnings=[line for row in report['runs'] for line in (row.get('stdout','')+'\n'+row['stderr']).splitlines() if re.search(r'ResourceWarning|(?i:\bwarning\s+[A-Z]+\d+:)',line)]
        report['warning_lines']=warnings
        report['passed']=len(report['runs'])==len(EXPECTED)+1 and report['pass_ids']==EXPECTED and report['source_unchanged'] and report['build_root_absent'] and not warnings and 'error_type' not in report and all(row['exit_code']==0 and not row['timeout'] and row['natural_tree_exit'] and row['cleanup_complete'] for row in report['runs'])
        save()
    print(json.dumps({k:report[k] for k in ('passed','pass_ids','source_unchanged','build_root_absent')}))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
