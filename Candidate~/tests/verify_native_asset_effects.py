"""Test-only pinned exact-method asset characterization; not full native compilation.
Original SearchAssets/GetAssetInfo/AssetExists/GetAssetData bytes are extracted
without edits after whole-file pin verification. Unity APIs are explicit doubles.
No production changes, MCP exposure, real Unity or external network required.
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
from verify_unity import DOTNET,TESTS,hashes
NATIVE=Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity/Editor')
PINS={'Tools/ManageAsset.cs':'2b2dd181e92f38522938468dcf3b2682fa4ea40caa166c8c2dbeb00d7c86799e',
      'Helpers/Response.cs':'a1769de32b9c6824841c070f0590ae7e9f44485d2a6c44a0bce3ed3f68e17391'}
NAMES=('SearchAssets','GetAssetInfo','AssetExists','GetAssetData')
BUDGET_IDS=('BA001','BA002','BA003','BA004','BA005','BA006','BA007','BA008','BA009','BA010','BA011','BA012','BA013','BA014','BA015')

def assemble(output):
    if any(hashlib.sha256((NATIVE/p).read_bytes()).hexdigest()!=h for p,h in PINS.items()):
        raise ValueError('native_source_drift')
    lines=(NATIVE/'Tools/ManageAsset.cs').read_bytes().decode('utf-8').splitlines(keepends=True)
    pieces=[];method_hashes={}
    for name in NAMES:
        starts=[i for i,line in enumerate(lines) if line.startswith('        private static ') and ' '+name+'(' in line]
        if len(starts)!=1:raise ValueError('native_method_ambiguous')
        start=starts[0]
        end=next(i for i in range(start+1,len(lines)) if lines[i].rstrip()=='        }')
        part=''.join(lines[start:end+1]);pieces.append(part)
        method_hashes[name]=hashlib.sha256(part.encode('utf-8')).hexdigest()
    prefix='using System; using System.IO; using System.Linq; using System.Collections.Generic; using System.Globalization; using Newtonsoft.Json.Linq; using UnityEngine; using UnityEditor; using MCPForUnity.Editor.Helpers;\nnamespace MCPForUnity.Editor.Tools { public static class ManageAsset {\n'
    suffix='\npublic static object Query(JObject p)=>SearchAssets(p);\npublic static object Info(string p)=>GetAssetInfo(p,false);\n} }\n'
    output.write_text(prefix+'\n'.join(pieces)+suffix,encoding='utf-8',newline='\n')
    return {'method_hashes':method_hashes,'generated_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}

def snapshot():
    return {**hashes(),str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        **{'native/'+p:hashlib.sha256((NATIVE/p).read_bytes()).hexdigest() for p in PINS},
        **{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'distribution').glob('materialize_*.py')}}

def main(label, budget_contract=False, candidate=False):
    if not re.fullmatch('[a-z0-9-]{1,100}',label):raise ValueError('invalid_label')
    output=ROOT/'evidence'/('native-asset-effects-'+label+'.json')
    if output.exists():raise FileExistsError('immutable evidence exists')
    report={'scope':'test-only exact pinned native methods; other handlers omitted; Unity APIs/callbacks doubles; no production integration',
        'upstream_commit':'30d22075093d1d35dfb0091c1c7550e9ad948577','native_pins':PINS,
        'before':snapshot(),'runs':[],'characterization_passed':False,'product_accepted':False}
    def save():output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    td=None
    try:
        with tempfile.TemporaryDirectory(prefix='vragent-native-asset-') as td:
            work=Path(td);source=work/'ManageAsset.cs'
            if candidate:
                from distribution.materialize_assets import materialize
                report['extraction']=materialize(NATIVE.parent,work/'additive')
                generated=work/'additive'
                shipped=ROOT/'package/Editor/ScopedAssets'
                if {f.name:f.read_bytes() for f in generated.iterdir()} != {f.name:f.read_bytes() for f in shipped.iterdir()}:
                    raise ValueError('shipped_asset_reader_drift')
                source=shipped/'CandidateScopedAssets.cs'
                report['compiled_actual_shipped_source']=True
            else:report['extraction']=assemble(source)
            env={'PATH':'/usr/bin:/bin','HOME':td,'TMPDIR':td,'LANG':'C.UTF-8','DOTNET_ROOT':str(DOTNET.parent),
                'DOTNET_CLI_HOME':td,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_NOLOGO':'1',
                'DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1','MSBUILDDISABLENODEREUSE':'1'}
            def run(name,argv):
                owner=make_owner(os.getpid());stderr=[]
                row={'name':name,'exit_code':None,'timed_out':False,'natural_tree_exit':False,'cleanup_complete':False}
                try:
                    with open(os.devnull,'rb') as stdin,tempfile.TemporaryFile() as stdout:
                        child=owner.spawn([str(v) for v in argv],env,stderr.append,stdio=(stdin.fileno(),stdout.fileno()))
                        deadline=time.monotonic()+(90 if name=='build' else 15)
                        while child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                        row['exit_code']=child.poll();row['timed_out']=row['exit_code'] is None
                        row['natural_tree_exit']=natural_tree_exit(owner,child)
                        row['cleanup_complete']=owner.close();stdout.seek(0)
                        row['stdout']=stdout.read().decode('utf-8','replace')
                finally:
                    row['cleanup_complete']=owner.close();row['stderr']='\n'.join(stderr)
                    report['runs'].append(row);save()
                print(json.dumps({k:row[k] for k in ('name','exit_code','timed_out','cleanup_complete')}),flush=True)
                return row
            build=run('build',[DOTNET,'build',TESTS/'NativeAssetEffects.csproj','-c','Release','--disable-build-servers',
                '-p:UseSharedCompilation=false','-p:BaseIntermediateOutputPath='+str(work/'obj')+'/',
                '-p:BaseOutputPath='+str(work/'bin')+'/', '-p:RestoreConfigFile='+str(TESTS/'ReviewNuGet.Config'),
                '-p:NuGetAudit=false','-p:RestoreSources=','-p:NativeAssetSource='+str(source),'-p:NativeEditorRoot='+str(NATIVE),'-p:CandidateAsset='+str(candidate).lower()])
            if build['exit_code']==0:
                dll=work/'bin/Release/net8.0/NativeAssetEffects.dll'
                if budget_contract:
                    for case in BUDGET_IDS:run(case,[DOTNET,dll,case])
                else:
                    run('page-budget-red',[DOTNET,dll,'NA001','--assert-page-budget'])
                    for number in range(1,7):run(f'NA{number:03d}',[DOTNET,dll,f'NA{number:03d}'])
    except Exception as exc:report['error_type']=type(exc).__name__
    finally:
        report['after']=snapshot();report['source_unchanged']=report['before']==report['after']
        report['build_root_absent']=td is not None and not Path(td).exists()
        report['pass_ids']=re.findall(r'^PASS (NA\d{3}) ', '\n'.join(r.get('stdout','') for r in report['runs']),re.M)
        red=[r for r in report['runs'] if r['name']=='page-budget-red']
        report['page_budget_negative_reproduced']=len(red)==1 and red[0]['exit_code']==1 and 'PAGE_LOAD_BUDGET_VIOLATED' in red[0]['stderr']
        report['warning_lines']=[line for r in report['runs'] for line in (r.get('stdout','')+'\n'+r['stderr']).splitlines() if re.search(r'ResourceWarning|(?i:\bwarning\s+[A-Z]+\d+:)',line)]
        report['characterization_passed']=(len(report['runs'])==8 and report['pass_ids']==[f'NA{i:03d}' for i in range(1,7)]
            and report['page_budget_negative_reproduced'] and report['source_unchanged'] and report['build_root_absent']
            and not report['warning_lines'] and 'error_type' not in report
            and all(not r['timed_out'] and r['natural_tree_exit'] and r['cleanup_complete']
                and r['exit_code']==(1 if r['name']=='page-budget-red' else 0) for r in report['runs']))
        if budget_contract:
            report['scope']='asset budget contract against current reader, not original characterization'
            report['budget_pass_ids']=re.findall(r'^PASS (BA\d{3}) ', '\n'.join(r.get('stdout','') for r in report['runs']),re.M)
            report['characterization_passed']=(len(report['runs'])==1+len(BUDGET_IDS) and report['source_unchanged'] and report['build_root_absent']
                and not report['warning_lines'] and 'error_type' not in report
                and all(r['exit_code']==0 and not r['timed_out'] and r['natural_tree_exit'] and r['cleanup_complete'] for r in report['runs'])
                and report['budget_pass_ids']==list(BUDGET_IDS))
        save()
    print(json.dumps({k:report[k] for k in ('characterization_passed','page_budget_negative_reproduced','source_unchanged','build_root_absent')}))
    return 0 if report['characterization_passed'] else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1],budget_contract='--budget-contract' in sys.argv[2:],candidate='--candidate' in sys.argv[2:]))
