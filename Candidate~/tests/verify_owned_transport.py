"""Compile actual pinned C# transport; Unity APIs are declared fixture substitutes.
Synthetic keys use the real memory-only TLS loader; no PEM files are created.
"""
from pathlib import Path
import asyncio
import datetime
import hashlib
import ipaddress
import json
import os
import ssl
import subprocess
import sys
import tempfile
import xml.sax.saxutils
ROOT=Path(__file__).resolve().parents[1]
UP=Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity')
DOTNET=Path('/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet')
SOURCE=UP/'Editor/Services/Transport/Transports/WebSocketTransportClient.cs'
EXPECTED='79a911dd5cd2539d0ab6cdfb92defa873184f6d91dc1a64a213d6cf3fa7d8665'
async def main(label):
 gates = len(sys.argv)>2 and sys.argv[2]=="gates"
 supervised = gates and len(sys.argv)>3 and sys.argv[3]=="owned"
 editor = gates and len(sys.argv)>3 and sys.argv[3]=="editor"
 out=ROOT/'evidence'/('owned-transport-'+label+'.json')
 if out.exists():raise ValueError('Evidence exists')
 assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED
 report={'scope':'Parent .NET actual transport, synthetic TLS, Unity APIs substituted; not Unity/Mono acceptance','runs':[],'independent_approval':False}
 with tempfile.TemporaryDirectory(prefix='candidate-owned-ws-') as td:
  work=Path(td)
  diff=ROOT/'dependencies/coplay-10.2.0-owned/transport.patch'
  provenance=json.loads((diff.parent/'PROVENANCE.json').read_text())
  report['patch_sha256']=hashlib.sha256(diff.read_bytes()).hexdigest()
  sys.path.insert(0, str(ROOT/'distribution'))
  from materialize_owned_transport import materialize
  generated=work/'OwnedTransport';materialize(UP,generated)
  shipped=ROOT/'package/Editor/OwnedTransport'
  assert {p.name:p.read_bytes() for p in generated.iterdir()}=={p.name:p.read_bytes() for p in shipped.iterdir()},'shipped_additive_source_drift'
  additive=shipped/'CandidateOwnedWebSocketTransportClient.cs'
  source=[SOURCE,additive,UP/'Editor/Services/IToolDiscoveryService.cs',UP/'Editor/Services/Transport/TransportState.cs',UP/'Editor/Services/Transport/IMcpTransportClient.cs',ROOT/'tests/unity-core/OwnedTransportStubs.cs',ROOT/'tests/unity-core/OwnedTransportCases.cs']
  if gates:
   text=(ROOT/'tests/unity-core/WriteUnityStubs.cs').read_text()
   text=text.replace(' public static class Application { public static string dataPath; }','')
   text=text.replace('return "Assets/source.mat";', 'return obj is UnityEngine.Shader ? "Resources/unity_builtin_extra" : "Assets/source.mat";')
   a=text.index('namespace MCPForUnity.Editor.Helpers {');b=text.index('namespace MCPForUnity.Editor.Tools {',a)
   text=text[:a]+text[b:]
   doubled=work/'GateUnityDoubles.cs';doubled.write_text(text+'\ninternal static class WriteUnityCases {}\n')
   source=[p for p in source if p.name!='OwnedTransportCases.cs']+[doubled,UP/'Editor/Helpers/Response.cs',ROOT/'tests/unity-core/OwnedGatePeer.cs',*sorted(p for p in (ROOT/'package/Editor').rglob('*.cs') if 'OwnedTransport' not in p.parts)]
  if editor:source=[ROOT/'tests/unity-core/EditorOwnerPeer.cs' if p.name=='OwnedGatePeer.cs' else p for p in source]
  freeze=source+[ROOT/'distribution/materialize_owned_transport.py',diff,diff.parent/'PROVENANCE.json',*shipped.iterdir()]+list((ROOT/'runtime').glob('*.py'))+list((ROOT/'launcher').glob('*.py'))+list((ROOT/'native/src').rglob('*.py'))+[ROOT/'tests/unity-core/WriteUnityStubs.cs',Path(__file__),ROOT/'tests/owned_descendants.py',ROOT/'distribution/assemble_source.py',ROOT/'distribution/source-inputs.json',ROOT/'build_candidate.py'];hashes={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in freeze};report['input_sha256']=hashes
  csproj=work/'OwnedTransport.csproj'
  application=[p for p in source if p.name in ('OwnedGatePeer.cs','OwnedTransportCases.cs','EditorOwnerPeer.cs') or ((ROOT/'package/Editor') in p.parents and p!=additive)]
  support=[p for p in source if p not in application]
  def project_xml(files, executable=False, reference=None):
   properties='<TargetFramework>net8.0</TargetFramework><LangVersion>9.0</LangVersion><ImplicitUsings>disable</ImplicitUsings><EnableDefaultCompileItems>false</EnableDefaultCompileItems><DefineConstants>UNITY_EDITOR</DefineConstants>'
   if executable:properties+='<OutputType>Exe</OutputType>'
   items=''.join('<Compile Include="'+xml.sax.saxutils.escape(str(p))+'"/>' for p in files)
   items+='<Reference Include="Newtonsoft.Json"><HintPath>$(MSBuildSDKsPath)/../Newtonsoft.Json.dll</HintPath></Reference>'
   if reference:items+='<ProjectReference Include="'+xml.sax.saxutils.escape(str(reference))+'"/>'
   return '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'+properties+'</PropertyGroup><ItemGroup>'+items+'</ItemGroup></Project>'
  library=work/'Support'/'MCPForUnity.Editor.csproj';library.parent.mkdir()
  library.write_text(project_xml(support))
  csproj.write_text(project_xml(application,True,library))
  env={'PATH':'/usr/bin:/bin','HOME':td,'DOTNET_ROOT':str(DOTNET.parent),'DOTNET_CLI_HOME':td,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1','DOTNET_NOLOGO':'1','MSBUILDDISABLENODEREUSE':'1'}
  p=subprocess.run([str(DOTNET),'build',str(csproj),'-c','Release','--disable-build-servers','-p:UseSharedCompilation=false','-p:NuGetAudit=false','-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config')],env=env,capture_output=True,text=True,timeout=70)
  report['build']={'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr};print(p.stdout,p.stderr)
  dll=work/'bin/Release/net8.0/OwnedTransport.dll'
  async def run(*args):
   from owned_descendants import Descendants
   tracker=Descendants() if editor else None
   done=asyncio.Event()
   proc=await asyncio.create_subprocess_exec(str(DOTNET),str(dll),*args,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
   watch=asyncio.create_task(tracker.watch(proc.pid,done)) if tracker else None
   try:stdout,stderr=await asyncio.wait_for(proc.communicate(),45)
   except TimeoutError:
    proc.kill();stdout,stderr=await proc.communicate()
   finally:
    done.set()
    if watch is not None:await watch
   descendants=await tracker.finish() if tracker else None
   row={'args_mode':args[-1] if args else 'constructor','exit':proc.returncode,'stdout':stdout.decode(),'stderr':stderr.decode(),'pid':proc.pid,'pid_absent':not Path('/proc/'+str(proc.pid)).exists()}
   if tracker:row['descendants']=descendants
   report['runs'].append(row);print(json.dumps(row),flush=True)
   return proc.returncode==0
  if editor:
   if p.returncode==0:
    project=work/'FixtureProject';(project/'Assets').mkdir(parents=True)
    from assemble_source import collect
    payload=collect(ROOT);package=work/'FixturePackage';package.mkdir()
    for relative,data in payload.items():
     destination=package/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
    report['source_payload_sha256']={name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}
    await run(str(sys.executable),str(package/'Runtime~/launcher/editor_owner.py'),str(project),str(package))
    report['source_payload_unchanged']=({str(x.relative_to(package)):hashlib.sha256(x.read_bytes()).hexdigest() for x in package.rglob('*') if x.is_file()}==report['source_payload_sha256'])
    assert report['source_payload_unchanged'] and not any(x.is_symlink() for x in package.rglob('*'))
   report['sources_unchanged']=all(hashlib.sha256(x.read_bytes()).hexdigest()==hashes[str(x)] for x in freeze)
   report['passed']=(p.returncode==0 and len(report['runs'])==1 and all(r['exit']==0 and r['pid_absent'] and r['descendants']['clean'] and 'private_editor_clean' in r['stdout'] and 'private_editor_ready' in r['stdout'] for r in report['runs']) and report['sources_unchanged'])
   out.write_text(json.dumps(report,indent=2));print(json.dumps({'passed':report['passed'],'evidence':str(out)}))
   return 0 if report['passed'] else 1
  if p.returncode==0 and (gates or await run()):
   sys.path.insert(0,str(ROOT/'runtime'))
   from tls_context import issue_tls_material,load_tls_context
   from run_identity import issue_run_identity
   import websockets
   material=issue_tls_material(lifetime=120)
   ctx=load_tls_context(material);pin=material.pin
   report['memory_only_tls_loader']=True
   if not gates:
    rows=[]; mode="owned-wire"
    async def peer(ws):
     row={};rows.append(row)
     row['path']=ws.request.path;row['auth_correct']=ws.request.headers.get('Authorization')=='Bearer fixture-bearer-not-real'
     row['register']=json.loads(await ws.recv())
     await ws.send(json.dumps({'type':'registered','session_id':'fixture-session'}))
     await asyncio.sleep(.08)
     if mode=='duplicate-register':
      await ws.send(json.dumps({'type':'registered','session_id':'replacement-session'}))
      try:
       async with asyncio.timeout(6):
        await ws.wait_closed()
       row['duplicate_closed']=True
      except TimeoutError:row['duplicate_closed']=False
      return
     for i,command in enumerate(['execute_anything','vrchat_agent_dispatch']):
      await ws.send(json.dumps({'type':'execute','id':str(i),'name':command,'params':{},'timeout':2}))
      row[command]=json.loads(await ws.recv())
     await ws.close()
    async with websockets.serve(peer,'127.0.0.1',0,ssl=ctx) as server:
     owned_sockets=list(server.sockets);port=owned_sockets[0].getsockname()[1];url=f'wss://127.0.0.1:{port}/hub/plugin'
     await run(url,'00'*32,'bad-pin');assert not rows,'bearer reached wrong certificate'
     await run(url,pin,'owned-wire')
     mode='duplicate-register'
     await run(url,pin,mode)
    report['wire']=rows
    report['listener_closed']=bool(owned_sockets) and all(x.fileno()==-1 for x in owned_sockets)
    report['wire_valid']=(len(rows)==2 and rows[1].get('duplicate_closed') is True and rows[0]['auth_correct'] and rows[0]['path']=='/hub/plugin'
     and rows[0].get('register',{}).get('project_hash')=='fixture-project'
     and rows[0].get('execute_anything',{}).get('result',{}).get('status')=='error'
     and rows[0].get('vrchat_agent_dispatch',{}).get('result',{}).get('result',{}).get('data',{}).get('probe')=='owned-native-wire')
   # Full real SDK -> authenticated native hub -> patched upstream C# -> readback.
   for path in (ROOT/'native/src',ROOT/'runtime',ROOT/'dependencies/mcp-1.29.1'):
    sys.path.insert(0,str(path))
   from candidate_auth import CandidateJWTVerifier
   from candidate_runtime import create_app,create_server
   from fastmcp import Client
   from fastmcp.client.transports import StreamableHttpTransport
   from transport.plugin_hub import PluginHub
   import uvicorn,socket
   identity=issue_run_identity(lifetime=120,clients=('hermes','codex'))
   def verifier(roles):
    credentials=[identity.credentials[role] for role in roles]
    return CandidateJWTVerifier(public_key=identity.public_key,issuer=identity.issuer,
      audience=credentials[0].audience,required_scope=credentials[0].scope,
      principals=[value.principal for value in credentials])
   report['real_run_issuer']=True
   sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   if supervised:
    import threading
    sys.path.insert(0,str(ROOT))
    from launcher.owned_run import create_owned_run,supervise_owned
    raw={'project':'fixture-project','local_port':port,'parent_pid':os.getpid()}
    owned=create_owned_run(raw,lifetime=120);identity=owned.owner.identity;material=owned.owner.tls;pin=material.pin
    sock.close();stop=threading.Event();statuses=[]
    task=asyncio.create_task(asyncio.to_thread(supervise_owned,raw,owned=owned,stop=stop,report=statuses.append))
   else:
    mcp=create_server('fixture-project',mcp_auth=verifier(('hermes','codex')))
    app=create_app(mcp,unity_auth=verifier(('unity',)))
    web=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',lifespan='on',ssl_context_factory=lambda config, default:ctx,timeout_graceful_shutdown=3))
    task=asyncio.create_task(web.serve(sockets=[sock]))
   agent_token=identity.credentials['hermes'].token
   env['FIXTURE_UNITY_BEARER']=identity.credentials['unity'].token
   trust=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);trust.load_verify_locations(cadata=material.certificate.decode('ascii'))
   peer_task=None;gate_peer=None
   try:
    async with asyncio.timeout(8):
     if supervised:
      while True:
       if task.done():raise AssertionError('owned launcher stopped: '+str(await task))
       try:
        reader,writer=await asyncio.open_connection('127.0.0.1',port,ssl=trust)
        writer.close();await writer.wait_closed();break
       except ConnectionRefusedError:await asyncio.sleep(.05)
     else:
      while not web.started and not task.done():await asyncio.sleep(.01)
    if task.done():await task
    if gates:
     project=work/'FixtureProject';(project/'Assets').mkdir(parents=True)
     (project/'Assets/Read.mat').write_text('original');(project/'Assets/Read.mat.meta').write_text('source-guid')
     gate_peer=await asyncio.create_subprocess_exec(str(DOTNET),str(dll),f'wss://127.0.0.1:{port}/hub/plugin',pin,str(project),env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
     ready=await asyncio.wait_for(gate_peer.stdout.readline(),7)
     if ready!=b'fixture_ready\n':
      stdout,stderr=await asyncio.wait_for(gate_peer.communicate(),3)
      raise AssertionError('fixture_ready_missing: '+stderr.decode())
     async def local_event(line):
      gate_peer.stdin.write((line+'\n').encode());await gate_peer.stdin.drain()
      return json.loads(await asyncio.wait_for(gate_peer.stdout.readline(),3))
    else:
     peer_task=asyncio.create_task(run(f'wss://127.0.0.1:{port}/hub/plugin',pin,'sdk-wire'))
    async with asyncio.timeout(5):
     while not (owned.binding.ready.is_set() if supervised else PluginHub._connections):
      if task.done():raise AssertionError('server stopped before Unity ready')
      await asyncio.sleep(.01)
    async with Client(StreamableHttpTransport(f'https://127.0.0.1:{port}/mcp',auth=agent_token,verify=trust)) as client:
     result=await asyncio.wait_for(client.call_tool('agent_status',{}),3)
     report['sdk_readback']=not result.is_error and (result.data.get('success') is True if gates else 'owned-native-wire' in str(result))
     if gates:
      native={'task_id':'fixture-native','operations':[{'command':'manage_material','action':'get_material_info'}],'targets':['Assets/Read.mat'],'ttl_seconds':60}
      prepared=await client.call_tool('agent_prepare',native);assert prepared.data['success']
      refused=await client.call_tool('manage_material',{'action':'get_material_info','material_path':'Assets/Read.mat'},raise_on_error=False)
      assert refused.is_error or refused.data.get('success') is False
      assert (await local_event('inspect'))['calls']==0
      prepared=await client.call_tool('agent_prepare',native);assert prepared.data['success']
      assert (await local_event('approve-native'))['approved']
      read=await client.call_tool('manage_material',{'action':'get_material_info','material_path':'Assets/Read.mat'})
      assert read.data['success'] and read.data['data']['material']=='fixture material',str(read)
      report['native_gate_readback']=True
      m={'task_id':'fixture-material','source':'Assets/Read.mat','candidate':'Assets/Candidate.mat','operations':['copy','edit'],'references':[],'ttl_seconds':60}
      prepared=await client.call_tool('material_prepare',m);assert prepared.data['success'];plan=prepared.data['data']['plan_id']
      refused=await client.call_tool('material_execute',{'task_id':m['task_id'],'plan_id':plan,'action':'copy','arguments':{}},raise_on_error=False)
      assert refused.is_error and not (project/'Assets/Candidate.mat').exists()
      prepared=await client.call_tool('material_prepare',m);assert prepared.data['success'];plan=prepared.data['data']['plan_id']
      assert (await local_event('approve-material'))['approved']
      async with Client(StreamableHttpTransport(f'https://127.0.0.1:{port}/mcp',auth=agent_token,verify=trust)) as stranger:
       refused=await stranger.call_tool('material_execute',{'task_id':m['task_id'],'plan_id':plan,'action':'copy','arguments':{}},raise_on_error=False)
       assert refused.is_error and not (project/'Assets/Candidate.mat').exists()
      report['unapproved_and_foreign_session_denied']=True
      for action,arguments in [('copy',{}),('edit',{'property':'_Glossiness','value':0.6})]:
       changed=await client.call_tool('material_execute',{'task_id':m['task_id'],'plan_id':plan,'action':action,'arguments':arguments})
       assert changed.data['success'],str(changed)
      assert (project/'Assets/Read.mat').read_text()=='original'
      assert (project/'Assets/Candidate.mat').read_text()=='0.6'
      report['material_gate_disk_readback']=True
      stopped=await client.call_tool('material_stop',{'task_id':m['task_id'],'plan_id':plan});assert stopped.data['success']
      assert (await local_event('inspect'))['material_plans']==0
      assert (project/'Assets/Candidate.mat').read_text()=='0.6' # revoke is not rollback
      refused=await client.call_tool('material_execute',{'task_id':m['task_id'],'plan_id':plan,'action':'edit','arguments':{'property':'_Glossiness','value':0.9}},raise_on_error=False)
      assert refused.is_error and (project/'Assets/Candidate.mat').read_text()=='0.6'
      report['material_stop_no_rollback']=True
    if supervised:
     stop.set();report['owned_launcher_result']=await asyncio.wait_for(task,12)
     assert report['owned_launcher_result']['code']=='STOPPED',report['owned_launcher_result']
    else:
     for ws in list(PluginHub._connections.values()):await ws.close()
    if peer_task is not None:await asyncio.wait_for(peer_task,5)
    if gate_peer is not None:
     gate_peer.stdin.write(b'stop\n');await gate_peer.stdin.drain()
     stdout,stderr=await asyncio.wait_for(gate_peer.communicate(),6)
     report['runs'].append({'args_mode':'gates-sdk-wire','exit':gate_peer.returncode,'stdout':stdout.decode(),'stderr':stderr.decode(),'pid':gate_peer.pid,'pid_absent':not Path('/proc/'+str(gate_peer.pid)).exists()})
   finally:
    if supervised:stop.set()
    else:web.should_exit=True
    await asyncio.wait_for(task,12)
    if peer_task is not None:await asyncio.wait_for(peer_task,6)
    if gate_peer is not None and gate_peer.returncode is None:
     gate_peer.kill();late_stdout,late_stderr=await gate_peer.communicate();print('FIXTURE_PEER_EXIT',gate_peer.returncode,late_stdout.decode(),late_stderr.decode())
    sock.close();env.pop('FIXTURE_UNITY_BEARER',None)
   report['no_PEM_files_created']=not (work/'key').exists() and not (work/'cert').exists()
   if supervised:
    outcome=report['owned_launcher_result']
    with socket.socket() as probe:listener_absent=probe.connect_ex(('127.0.0.1',port))!=0
    report['sdk_cleanup']={'owned_process_cleanup':outcome['process_cleanup_complete'],
       'observer_thread_removed':outcome['probe_cleanup_complete'],
       'probe_delete_confirmed':outcome['probe_session_cleanup_confirmed'],'listener_closed':listener_absent}
   else:
    report['sdk_cleanup']={'connections_empty':not PluginHub._connections,'pending_empty':not PluginHub._pending,'sessions_empty':not await PluginHub._registry.list_sessions(),'listener_fd_closed':sock.fileno()==-1}
  report['sources_unchanged']=all(hashlib.sha256(x.read_bytes()).hexdigest()==hashes[str(x)] for x in freeze)
 report['temporary_directory_removed']=not Path(td).exists()
 branch_ok=(all(report.get(k) is True for k in ['native_gate_readback','material_gate_disk_readback','material_stop_no_rollback','unapproved_and_foreign_session_denied']) if gates else report.get('listener_closed') is True and report.get('wire_valid') is True)
 report['passed']=all(report.get(k) is True for k in ('memory_only_tls_loader','real_run_issuer','no_PEM_files_created')) and branch_ok and report.get('sdk_readback') is True and len(report.get('sdk_cleanup',{}))==4 and all(report['sdk_cleanup'].values()) and report['build']['exit']==0 and len(report['runs'])==(1 if gates else 5) and all(x['exit']==0 and x['pid_absent'] for x in report['runs']) and report['sources_unchanged'] and report['temporary_directory_removed']
 out.write_text(json.dumps(report,indent=2));print(json.dumps({'passed':report['passed'],'evidence':str(out)}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(asyncio.run(main(sys.argv[1])))
