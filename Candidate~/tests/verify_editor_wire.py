"""Fresh C# wire/OS fixtures with exact isolated methods and owned cleanup.
Neither net8 execution nor netstandard2.1 reference compilation is Unity acceptance.
Usage: locked-python -I -B tests/verify_editor_wire.py LABEL rw|ep [EXACT_IDS...]
"""
import ast,hashlib,importlib.util,json,os,re,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import verify_peer
from source_native_source import PINS
from distribution.assemble_source import collect
SUITES={'rw':('test_reload_wire.py','WirePeer','RW',3),'ep':('test_editor_peer.py','EditorPeerCases','EP',6),'ce':('test_editor_control.py','EditorBootstrapCases','CE',4),'er':('test_editor_reload.py','WirePeer','ER',5),'ec':('test_editor_orchestration.py','WriteUnityCases','EC',7)}
NATIVE_LOCAL=Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity/Editor')
NATIVE_URL='https://raw.githubusercontent.com/CoplayDev/unity-mcp/30d22075093d1d35dfb0091c1c7550e9ad948577/MCPForUnity/Editor/'

def response_source(work,fetch=None):
 local=NATIVE_LOCAL/'Helpers/Response.cs'
 if fetch is None and NATIVE_LOCAL.is_dir():raw=local.read_bytes()
 else:
  if fetch is None:
   from urllib.request import urlopen
   fetch=urlopen
  with fetch(NATIVE_URL+'Helpers/Response.cs',timeout=30) as response:raw=response.read()
 if hashlib.sha256(raw).hexdigest()!=PINS['Helpers/Response.cs']:raise ValueError('response_source_drift')
 path=work/'Response.cs';path.write_bytes(raw);return path

def native_source(work,fetch=None):
 pins={name:PINS[name] for name in ('Helpers/ToolParams.cs','Helpers/ParamCoercion.cs','Helpers/StringCaseUtility.cs')}
 pins['Tools/ReadConsole.cs']='80950f3ff610b845d34644aa0426775c7e1bfc20483c912c004067d43dfb119f'
 local=fetch is None and NATIVE_LOCAL.is_dir()
 if not local and fetch is None:
  from urllib.request import urlopen
  fetch=urlopen
 root=work/'native'
 for name,pin in pins.items():
  if local:raw=(NATIVE_LOCAL/name).read_bytes()
  else:
   with fetch(NATIVE_URL+name,timeout=30) as response:raw=response.read()
  if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('wire_native_source_drift')
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 return root

def select_methods(suite,filters):
 file,project,prefix,count=SUITES[suite]
 tree=ast.parse((ROOT/'tests'/file).read_text(encoding='utf-8'))
 methods=sorted('runtime_fix_tests.'+node.name+'.'+m.name for node in tree.body if isinstance(node,ast.ClassDef)
  for m in node.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name.startswith('test_'))
 ids=[m.split('.test_')[1].split('_')[0] for m in methods]
 if ids!=[f'{prefix}{i:03}' for i in range(1,count+1)]:raise ValueError('method_set_changed')
 if len(filters)!=len(set(filters)) or not set(filters)<=set(ids):raise ValueError('method_filter_invalid')
 return [m for m in methods if not filters or m.split('.test_')[1].split('_')[0] in filters]

def main():
 if len(sys.argv)<3 or re.fullmatch('[a-z0-9-]+',sys.argv[1]) is None or sys.argv[2] not in SUITES:
  raise SystemExit('LABEL rw|ep [EXACT_IDS...] required')
 LABEL=sys.argv[1];SUITE=sys.argv[2];FILTERS=sys.argv[3:]
 OUT=ROOT/'evidence'/('editor-wire-'+LABEL+'.json')
 if OUT.exists():raise SystemExit('Refusing to overwrite evidence')
 chosen=shutil.which('dotnet') or '/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet'
 DOTNET=Path(chosen).resolve()
 if not DOTNET.is_file() or sys.platform not in ('linux','win32'):raise SystemExit('native dotnet/platform unavailable')
 FILE_NAME,PROJECT,PREFIX,COUNT=SUITES[SUITE];PEER=SUITE=='ep'
 FILE=ROOT/'tests'/FILE_NAME;ALL=select_methods(SUITE,());expected=select_methods(SUITE,FILTERS)
 files=sorted(set([ROOT/p for p in verify_peer.SOURCES]+[FILE,Path(__file__),ROOT/'tests/source_native_source.py',ROOT/'tests/test_client_binding.py',
  ROOT/'tests/test_editor_control.py',ROOT/'tests/test_editor_owner.py',*list((ROOT/'package/Editor').rglob('*.cs')),*list((ROOT/'tests/unity-core').glob('*.cs')),*list((ROOT/'tests/unity-core').glob('*.csproj'))]))
 def hashes():return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
 report={'scope':('actual C# OS peer byte channel; net8, not Unity Mono or installed Editor' if PEER else 'actual C# gate bytes + SDK + private OS channel; Editor/native evidence/approval/owner coordination fixtures'),
  'platform':sys.platform,'suite':SUITE,'source_before':hashes(),'expected':expected,'all_methods':ALL,'full_suite':expected==ALL,'rows':[],'passed':False}
 if SUITE=='ec':report['scope']='shipped C# coordinator/session/UI + OS peer + collectible managed-domain fixture; Unity/transport/owner responses and local approval are doubles, not actual Editor'
 try:
  collect() # Reuse exact pinned input validation; this is not VPM/package acceptance.
  source=ast.parse((ROOT/'evidence/runtime-fix-run.py').read_text())
  child=next(ast.literal_eval(n.value) for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CHILD' for t in n.targets))
  with tempfile.TemporaryDirectory(prefix='vragent-reload-wire-') as td:
   work=Path(td)
   argv=[str(DOTNET),'build',str(ROOT/'tests/unity-core'/(PROJECT+'.csproj')),'-c','Release','--disable-build-servers','-p:UseSharedCompilation=false',
    f'-p:BaseIntermediateOutputPath={work}/obj/',f'-p:BaseOutputPath={work}/bin/',f'-p:RestoreConfigFile={ROOT}/tests/unity-core/ReviewNuGet.Config',
    '-p:NuGetAudit=false','-p:RestoreSources=']
   if SUITE in ('rw','er','ec'):argv.append('-p:CandidateResponseSource='+str(response_source(work)))
   if SUITE in ('rw','er'):argv.append('-p:CandidateNativeRoot='+str(native_source(work)))
   build_code='import os,subprocess;os.environ.update('+repr({**{key:os.environ[key] for key in ('PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA') if key in os.environ},'DOTNET_ROOT':str(DOTNET.parent),'DOTNET_CLI_HOME':td,'DOTNET_NOLOGO':'1','DOTNET_CLI_TELEMETRY_OPTOUT':'1','MSBUILDDISABLENODEREUSE':'1'})+');raise SystemExit(subprocess.run('+repr(argv)+',timeout=30).returncode)'
   build=verify_peer.run_case(FILE,build_code);report['build']=build
   dll=work/'bin/Release/net8.0'/(PROJECT+'.dll')
   report['build_passed']=(build['exit_code']==0 and not build['timed_out'] and build['natural_tree_exit'] and build['cleanup_complete'] and build['temporary_home_absent'] and dll.is_file() and not re.search(r'ResourceWarning|warning [A-Z]+\d+:',build['stdout']+build['stderr']))
   if PEER:
    reference_args=[str(ROOT/'tests/unity-core/EditorPeerNetStandard.csproj') if value==str(ROOT/'tests/unity-core/EditorPeerCases.csproj') else value for value in argv]+[
     '-p:BaseIntermediateOutputPath='+str(work/'refobj')+'/', '-p:BaseOutputPath='+str(work/'refbin')+'/']
    reference_code=build_code.replace(repr(argv),repr(reference_args))
    reference=verify_peer.run_case(FILE,reference_code);report['reference_build']=reference
    report['reference_build_passed']=bool(reference['exit_code']==0 and not reference['timed_out']
     and reference['natural_tree_exit'] and reference['cleanup_complete'] and reference['temporary_home_absent']
     and (work/'refbin/Release/netstandard2.1/EditorPeerNetStandard.dll').is_file()
     and not re.search(r'ResourceWarning|warning [A-Z]+\d+:',reference['stdout']+reference['stderr']))
    report['build_passed']=report['build_passed'] and report['reference_build_passed']
   if report['build_passed']:
    report['fresh_dll_sha256']=hashlib.sha256(dll.read_bytes()).hexdigest()
    injection='import importlib.util;spec=importlib.util.spec_from_file_location("runtime_fix_tests",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.WIRE_DLL='+repr(str(dll))+';module.DOTNET='+repr(str(DOTNET))+';namespace=vars(module)'
    assert child.count("namespace = runpy.run_path(path, run_name='runtime_fix_tests')")==1
    code=child.replace("namespace = runpy.run_path(path, run_name='runtime_fix_tests')",injection)
    for method in expected:
     row=verify_peer.run_case(FILE,code,filters=(method,));row['expected']=[method];row['passed']=verify_peer.case_passed(row,[method])
     report['rows'].append(row)
   report['dll_unchanged']=dll.is_file() and report.get('fresh_dll_sha256')==hashlib.sha256(dll.read_bytes()).hexdigest()
  report['build_root_absent']=not work.exists()
 except BaseException as error:
  report['error_type']=type(error).__name__
 report['source_after']=hashes();report['source_unchanged']=report['source_before']==report['source_after']
 report['passed']=bool('error_type' not in report and report.get('build_passed') and report.get('build_root_absent') and report.get('dll_unchanged') and report['source_unchanged'] and len(report['rows'])==len(expected) and all(r['passed'] for r in report['rows']))
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:report.get(k) for k in ['passed','expected','full_suite','build_passed','build_root_absent','source_unchanged','error_type']}))
 for row in report['rows']:
  if not row['passed']:print(row['stderr'][-6000:])
 if not report.get('build_passed'):print((report.get('build',{}).get('stdout','')+'\n'+report.get('reference_build',{}).get('stdout',''))[-5500:])
 return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
