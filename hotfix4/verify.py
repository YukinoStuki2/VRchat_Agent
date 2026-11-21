"""Check the released assembly boundary with the actual Coplay sources and Unity API doubles."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,os
from zipfile import ZipFile

project='''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework><OutputType>Exe</OutputType><DefineConstants>UNITY_EDITOR</DefineConstants><ImplicitUsings>disable</ImplicitUsings></PropertyGroup><ItemGroup><Reference Include="Newtonsoft.Json"><HintPath>$(MSBuildSDKsPath)/../Newtonsoft.Json.dll</HintPath></Reference></ItemGroup></Project>'''

def test(agent,dep,dotnet,red):
    assert __debug__ and hashlib.sha256(dep.read_bytes()).hexdigest()=='9409c972fb801eb991e00028d5f3a8e3f54931077476cd6c01e34242eb72e46a'
    with tempfile.TemporaryDirectory() as name, ZipFile(agent) as a, ZipFile(dep) as c:
        t=Path(name); source='Editor/ScopedAssets/CandidateScopedAssets.cs'
        ref=json.loads(a.read('Editor/ScopedAssets/CandidateAssets.asmref'))['reference'].removeprefix('GUID:')
        assert ('guid: '+ref).encode() in c.read('Editor/MCPForUnity.Editor.asmdef.meta')
        assert json.loads(c.read('Runtime/MCPForUnity.Runtime.asmdef'))['name'] in json.loads(c.read('Editor/MCPForUnity.Editor.asmdef'))['references']
        assert ('Runtime~.meta' in a.namelist())==red and 'Runtime~/launcher/editor_owner.py' in a.namelist()
        for n in ['Runtime/Helpers/UnityObjectIdCompat.cs','Editor/Helpers/Response.cs']: (t/Path(n).name).write_bytes(c.read(n))
        (t/'CandidateScopedAssets.cs').write_bytes(a.read(source));(t/'Fixture.cs').write_bytes(Path(__file__).with_name('Fixture.cs').read_bytes())
        (t/'global.json').write_text(json.dumps({'sdk':{'version':'8.0.100','rollForward':'latestFeature','allowPrerelease':False}}))
        (t/'check.csproj').write_text(project);(t/'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
        env=dict(os.environ,DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_HOME=str(t),DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
        r=subprocess.run([dotnet,'build','check.csproj','--disable-build-servers','--nologo','-p:UseSharedCompilation=false','-p:NuGetAudit=false'],cwd=t,env=env,capture_output=True,text=True,timeout=100); log=r.stdout+r.stderr
        if red:
            assert r.returncode!=0 and 'CandidateScopedAssets.cs(252,36): error CS1061' in log and "'GetInstanceIDCompat'" in log and all('error CS1061' in l for l in log.splitlines() if ': error ' in l),log
            print('RED reproduced:',next(l.split('/CandidateScopedAssets.cs')[-1] for l in log.splitlines() if 'error CS1061' in l));return
        assert r.returncode==0,log
        subprocess.run([dotnet,'bin/Debug/net8.0/check.dll'],cwd=t,env=env,timeout=30,check=True)

if __name__=='__main__':test(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],sys.argv[4:] == ['--red'])
