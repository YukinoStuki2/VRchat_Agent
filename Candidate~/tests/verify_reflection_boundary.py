"""Pinned native risk reproduction plus additive fixed-type reader/gate tests.
Real .NET assembly resolution, Unity API doubles; not Unity/Mono or permission
acceptance. No host/upstream edits, model calls, network or login.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from xml.sax.saxutils import quoteattr

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from owned_descendants import Descendants
DOTNET=Path('/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet')
UP=Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity')
PINS={
 'Editor/Tools/UnityReflect.cs':'b42f5b8de353eec2e6ce26bbfa72a4e235ecedcf7fabffbda548244f10f838ef',
 'Editor/Helpers/UnityTypeResolver.cs':'b6c89e35e6eb2120a7a33444497940a4b9980c24d25dabd8388d39db44ffa4e0',
 'Editor/Helpers/ToolParams.cs':'f708345c2913672011a7050ddceb96141a22f0880c9dfea65ebfb5b50c792abc',
 'Editor/Helpers/StringCaseUtility.cs':'5758c84d56fd4a3420aede775ddd1ca7cc8e0854476bedf65a1a9bca437cd411',
 'Editor/Helpers/ParamCoercion.cs':'69b425c49152a31d68e80d0a6498c78c406989242214a8f9b760b6936b17670b',
 'Editor/Helpers/Response.cs':'a1769de32b9c6824841c070f0590ae7e9f44485d2a6c44a0bce3ed3f68e17391',
 'Runtime/Helpers/UnityAssembliesCompat.cs':'ec9f4f1de38983f810616899decd63976cd2df8f741b7d592520a04b1dc08437'
}

def hashes():
    files=[UP/p for p in PINS]+[Path(__file__).resolve(),ROOT/'tests/unity-core/ReflectionBoundaryCases.cs',ROOT/'package/Editor/ScopedReflection/CandidateScopedUnityReflect.cs',ROOT/'package/Editor/Core/CandidateGate.cs']
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

async def main(label):
    output=ROOT/'evidence'/('reflection-boundary-'+label+'.json')
    if output.exists():raise FileExistsError('evidence_already_exists')
    for p,h in PINS.items():
        if hashlib.sha256((UP/p).read_bytes()).hexdigest()!=h:raise ValueError('native_source_drift')
    report={'scope':__doc__,'runs':[],'observations':[], 'hashes_before':hashes(),
            'unity_editor_verified':False,'reflection_enabled':False,'product_accepted':False}
    watcher=Descendants();done=asyncio.Event();watching=asyncio.create_task(watcher.watch(os.getpid(),done))
    temporary=None
    try:
        with tempfile.TemporaryDirectory(prefix='candidate-reflection-boundary-') as td:
            temporary=Path(td)
            env={'PATH':'/usr/bin:/bin','HOME':td,'TMPDIR':td,'LANG':'C.UTF-8',
                 'DOTNET_ROOT':str(DOTNET.parent),'DOTNET_CLI_HOME':td,
                 'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_NOLOGO':'1',
                 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1','MSBUILDDISABLENODEREUSE':'1'}
            async def run(name,argv):
                process=await asyncio.create_subprocess_exec(*map(str,argv),cwd=td,env=env,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                try:out,err=await asyncio.wait_for(process.communicate(),90)
                except BaseException:
                    if process.returncode is None:process.kill()
                    await process.communicate();raise
                row={'name':name,'exit_code':process.returncode,'stdout':out.decode(),'stderr':err.decode()}
                report['runs'].append(row)
                if process.returncode!=0:raise RuntimeError(name+'_failed')
                if 'ResourceWarning' in row['stderr'] or ' warning ' in row['stdout']:raise RuntimeError(name+'_warning')
                return row
            def project(name,source,refs='',exe=False):
                work=temporary/name;work.mkdir()
                (work/'Main.cs').write_text(source,encoding='utf-8')
                (work/(name+'.csproj')).write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                    '<TargetFramework>net8.0</TargetFramework><LangVersion>9.0</LangVersion>'
                    '<ImplicitUsings>disable</ImplicitUsings><Nullable>disable</Nullable>'
                    '<EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
                    +('<OutputType>Exe</OutputType>' if exe else '')+'</PropertyGroup><ItemGroup>'
                    '<Compile Include="Main.cs"/>'+refs+'</ItemGroup></Project>',encoding='utf-8')
                return work/(name+'.csproj')
            async def build(name,path):
                await run(name+'-build',[DOTNET,'build',path,'--configuration','Release','--disable-build-servers',
                    '-p:UseSharedCompilation=false','-p:NuGetAudit=false','-p:RestoreSources=',
                    '-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config')])
                return path.parent/'bin/Release/net8.0'/(name+'.dll')
            dependency=project('ReflectionMissingDependency','namespace MissingDependency {public class Base {}}')
            await build('ReflectionMissingDependency',dependency)
            broken=project('ReflectionBrokenPlugin','public class BrokenPlugin:MissingDependency.Base {}',
                           '<ProjectReference Include='+quoteattr(str(dependency))+'/>')
            broken_dll=await build('ReflectionBrokenPlugin',broken)
            isolated=temporary/'isolated';isolated.mkdir();broken_copy=isolated/broken_dll.name
            shutil.copyfile(broken_dll,broken_copy)
            sources=''.join('<Compile Include='+quoteattr(str(UP/p))+'/>' for p in PINS)
            sources += ''.join('<Compile Include='+quoteattr(str(ROOT/p))+'/>' for p in ('package/Editor/ScopedReflection/CandidateScopedUnityReflect.cs','package/Editor/Core/CandidateGate.cs'))
            sources+='<Reference Include="Newtonsoft.Json"><HintPath>$(MSBuildSDKsPath)/../Newtonsoft.Json.dll</HintPath></Reference>'
            case=project('ReflectionBoundaryCases',(ROOT/'tests/unity-core/ReflectionBoundaryCases.cs').read_text(),sources,True)
            dll=await build('ReflectionBoundaryCases',case)
            for mode in ('metadata','get_type','get_member','search','scoped_type','scoped_member','scoped_missing','scoped_search','scoped_gate'):
                row=await run(mode,[DOTNET,dll,mode,broken_copy])
                report['observations'].append(json.loads(row['stdout']))
    except Exception as error:
        report['failure']={'type':type(error).__name__,'message':str(error)}
    finally:
        done.set();await watching
        report['descendants']=await watcher.finish()
        report['temporary_root_absent']=temporary is not None and not temporary.exists()
        report['source_unchanged']=report['hashes_before']==hashes()
        descendants=report['descendants']
        # Shared watcher.clean requires a listener because it was built for transport
        # tests. This offline verifier instead requires that NO listener ever exists.
        report['offline_cleanup_verified']=(descendants['tracked_descendants']>0
            and descendants['tracked_listeners']==0 and not descendants['residual_pids']
            and not descendants['residual_ports'] and descendants['safety_cleanup_complete'])
        report['characterization_passed']=('failure' not in report
            and [x['mode'] for x in report['observations']]==['metadata','get_type','get_member','search','scoped_type','scoped_member','scoped_missing','scoped_search','scoped_gate']
            and report['offline_cleanup_verified'] and report['temporary_root_absent'] and report['source_unchanged'])
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('hashes_before','runs')},ensure_ascii=False))
    return 0 if report['characterization_passed'] else 1

if __name__=='__main__':raise SystemExit(asyncio.run(main(sys.argv[1])))
