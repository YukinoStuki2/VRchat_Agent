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
NATIVE=ROOT/'evidence/test-framework-1.1.31'
FIXTURE=ROOT/'tests/unity-core/DiscoveryReadCases.cs'
EXPECTED=['DR001', 'DR002', 'DR003', 'DR004', 'DR005', 'DR006', 'DR007', 'DR008', 'DR009', 'DR010', 'DR011', 'DR012', 'DR013', 'DR014', 'DR015', 'DR016', 'DR017', 'DR018', 'DR019', 'DR020', 'DR021', 'DR022', 'DR023', 'DR024', 'DR025']

def main(label,gate=False):
    expected=["DG001","DG002","DG003","DG004","DG005","DG006","DG007","DG008","DG009","DG010","DG011","DG012","DG013","DG014","DG015"] if gate else EXPECTED
    assert re.fullmatch('[a-z0-9-]+',label)
    output=ROOT/'evidence'/('discovery-reader-'+label+'.json');assert not output.exists()
    def hashes():
        paths=[FIXTURE,Path(__file__),ROOT/'tests/unity-core/DiscoveryGateCases.cs',ROOT/'package/Editor/Core/CandidateGate.cs',ROOT/'distribution/materialize_discovery.py',ROOT/'distribution/source-inputs.json']+list((ROOT/'package/Editor/ScopedTests').glob('*'))
        return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    before=hashes()
    report={'scope':__doc__,'before':before,'runs':[],'product_accepted':False}
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    td=None
    try:
        with tempfile.TemporaryDirectory(prefix='vragent-discovery-reader-') as td:
            work=Path(td)
            from distribution.assemble_source import collect
            from distribution.materialize_discovery import materialize
            files=collect(ROOT)
            generated=work/'generated';proof=materialize(NATIVE,Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity'),generated)
            for p in generated.iterdir():
                assert p.read_bytes()==files['Editor/ScopedTests/'+p.name], 'generated_source_drift: '+p.name
            for name,data in files.items():
                if name.startswith('Editor/ScopedTests/') and name.endswith('.cs'):
                    (work/Path(name).name).write_bytes(data)
            report['actual_payload_compiled']=True
            report['provenance']=proof
            (work/'Fixture.cs').write_bytes(FIXTURE.read_bytes())
            if gate:
                (work/'GateFixture.cs').write_bytes((ROOT/'tests/unity-core/DiscoveryGateCases.cs').read_bytes())
                (work/'CandidateGate.cs').write_bytes(files['Editor/Core/CandidateGate.cs'])
            (work/'DiscoveryEffects.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><AssemblyName>UnityEditor.TestRunner</AssemblyName><TargetFramework>net8.0</TargetFramework><LangVersion>9.0</LangVersion><ImplicitUsings>disable</ImplicitUsings><Nullable>disable</Nullable><UseSharedCompilation>false</UseSharedCompilation><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup><Compile Include="*.cs" /><Reference Include="Newtonsoft.Json"><HintPath>$(MSBuildSDKsPath)/../Newtonsoft.Json.dll</HintPath></Reference></ItemGroup></Project>''')
            if gate:
                project=work/'DiscoveryEffects.csproj'
                project.write_text(project.read_text().replace('<OutputType>Exe</OutputType>','<OutputType>Exe</OutputType><StartupObject>DiscoveryGateCases</StartupObject>'))
            env={'PATH' :'/usr/bin:/bin','HOME':td,'TMPDIR':td,'LANG':'C.UTF-8','DOTNET_ROOT':str(DOTNET.parent),'DOTNET_CLI_HOME':td,'DOTNET_NOLOGO':'1','DOTNET_CLI_TELEMETRY_OPTOUT':'1','MSBUILDDISABLENODEREUSE':'1'}
            def run(name,args):
                owner=make_owner(os.getpid());stderr=[];row={'name':name}
                try:
                    with open(os.devnull,'rb') as stdin,tempfile.TemporaryFile() as stdout:
                        proc=owner.spawn([str(x) for x in args],env,stderr.append,stdio=(stdin.fileno(),stdout.fileno()))
                        deadline=time.monotonic()+(90 if name.endswith('build') else 15)
                        while proc.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                        row.update(exit_code=proc.poll(),timeout=proc.poll() is None,natural_tree_exit=natural_tree_exit(owner,proc))
                        row['cleanup_complete']=owner.close();stdout.seek(0);row['stdout']=stdout.read().decode('utf-8','replace')
                finally:
                    row['cleanup_complete']=owner.close();row['stderr']='\n'.join(stderr);report['runs'].append(row);save()
                print(json.dumps({k:row[k] for k in ('name','exit_code','timeout','cleanup_complete')}),flush=True)
                return row['exit_code']
            if run('build',[DOTNET,'build',work/'DiscoveryEffects.csproj','-c','Release','--disable-build-servers','-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),'-p:NuGetAudit=false'])==0:
                dll=work/'bin/Release/net8.0/UnityEditor.TestRunner.dll'
                for case in (["gate"] if gate else expected):run(case,[DOTNET,dll,case])
                external=work/'external';external.mkdir()
                (external/'Consumer.cs').write_text('using UnityEditor.TestTools.TestRunner; class Consumer {static int Main(){var j=CandidateDiscoveryJob.Begin("EditMode",()=>false);var r=j.Completion.Result;if(r.Success||r.EffectsMayHaveOccurred||!r.CleanupConfirmed)return 1;System.Console.WriteLine("PASS DA001 separate_assembly_default_denied");return 0;}}')
                (external/'Consumer.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><UseSharedCompilation>false</UseSharedCompilation></PropertyGroup><ItemGroup><Reference Include="UnityEditor.TestRunner"><HintPath>'+str(dll)+'</HintPath></Reference></ItemGroup></Project>')
                if run('external-build',[DOTNET,'build',external/'Consumer.csproj','-c','Release','--disable-build-servers','-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),'-p:NuGetAudit=false'])==0:
                    run('external',[DOTNET,external/'bin/Release/net8.0/Consumer.dll'])
    except Exception as exc:report['error_type']=type(exc).__name__
    finally:
        report['after']=hashes();report['source_unchanged']=report['before']==report['after'];report['build_root_absent']=td is not None and not Path(td).exists()
        report['pass_ids']=re.findall(r'^PASS (D[RG]\d{3}) ','\n'.join(row.get('stdout','') for row in report['runs']),re.M)
        warnings=[line for row in report['runs'] for line in (row.get('stdout','')+'\n'+row['stderr']).splitlines() if re.search(r'ResourceWarning|(?i:\bwarning\s+[A-Z]+\d+:)',line)]
        report['warning_lines']=warnings
        report['passed']=len(report['runs'])==(4 if gate else len(expected)+3) and any('PASS DA001 separate_assembly_default_denied' in q.get('stdout','') for q in report['runs']) and report['pass_ids']==expected and report['source_unchanged'] and report['build_root_absent'] and not warnings and 'error_type' not in report and all(row['exit_code']==0 and not row['timeout'] and row['natural_tree_exit'] and row['cleanup_complete'] for row in report['runs'])
        save()
    print(json.dumps({k:report[k] for k in ('passed','pass_ids','source_unchanged','build_root_absent')}))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1],"--gate" in sys.argv[2:]))
