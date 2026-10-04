"""TEST ONLY: native clients plus compiled gates, not a product handoff/Unity UI.
The verifier owns the gate stdin approval channel. Neither client receives it.
"""
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
import json
from pathlib import Path
import ssl
import sys

from test_bootstrap_runtime import child_environment
from test_runtime_lifecycle import PREPARE, READ
from test_runtime_material import MANIFEST
import test_client_binding as binding
import websockets

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ['agent_status','agent_catalog','agent_prepare','agent_stop','manage_material','manage_animation','read_console','manage_scene','find_gameobjects','get_gameobject','get_gameobject_components','get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items','manage_packages',
         'material_prepare','material_execute','material_stop']

def assert_denied_result(value,tool):
    result=value.get('structuredContent',{})
    if tool in ('get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items') and isinstance(result,dict) and set(result)=={'result'}:result=result['result']
    assert value.get('isError') is True or (isinstance(result,dict) and result.get('success') is False)

class NativePeer:
    """Test-only NDJSON client to installed Hermes adapter/official Codex app-server."""
    def __init__(self, process, role, captured):
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        self.process, self.role, self.captured = process, role, captured
        self.errors = asyncio.create_task(process.stderr.read())
        self.number = 0
        self.thread: str | None = None
        self.closed = False
        self.ssh_report = None
        self.wait_deleted: Callable[[], Awaitable[None]] | None = None
        self.close_observation = {}

    async def request(self, method, params):
        self.number += 1
        self.process.stdin.write((json.dumps({'id':self.number,'method':method,'params':params})+'\n').encode())
        await self.process.stdin.drain()
        async with asyncio.timeout(20):
            while True:
                line = await self.process.stdout.readline()
                assert line, 'native_peer_eof'
                self.captured.append(line)
                value = json.loads(line)
                assert 'error_type' not in value, 'native_peer_failed'
                if value.get('id') == self.number:
                    assert 'error' not in value, 'native_rpc_error'
                    return value['result']

    async def call(self, name, arguments):
        assert name in TOOLS
        return await self.request('mcpServer/tool/call' if self.role=='codex' else 'call',
            {'threadId':self.thread,'server':'candidate','tool':name,'arguments':arguments}
            if self.role=='codex' else {'tool':name,'arguments':arguments})

    async def close(self):
        if self.closed: return
        self.closed = True
        input_closed = False
        try:
            if self.role=='codex' and self.thread:
                reply=await self.request('thread/unsubscribe',{'threadId':self.thread})
                status=reply.get('status') if isinstance(reply,dict) else None
                self.close_observation['unsubscribe_status']=status if status in {'unsubscribed','notLoaded','notSubscribed'} else 'other'
                # This is the app-server control pipe, not the MCP TLS transport.
                # EOF triggers the pinned stdio branch's shutdown_threads; waiting
                # first races its 60s idle-unload against the server's 60s expiry.
                assert self.wait_deleted is not None,'native_delete_observer_missing'
                self.process.stdin.close()
                input_closed = True
                try:
                    await asyncio.wait_for(self.wait_deleted(),12)
                    self.close_observation['delete_confirmed']=True
                except BaseException as error:
                    self.close_observation['delete_confirmed']=False
                    self.close_observation['failure_type']=type(error).__name__
                    # Bounded queued notifications: no bodies or identifiers in the report.
                    kinds={}
                    for _ in range(32):
                        try: line=await asyncio.wait_for(self.process.stdout.readline(),.05)
                        except (TimeoutError,AttributeError): break
                        if not line: break
                        self.captured.append(line)
                        value=json.loads(line)
                        kind=value.get('method')
                        if kind not in {'thread/closed','thread/status/changed','thread/started'}:kind='other'
                        kinds[kind]=kinds.get(kind,0)+1
                    self.close_observation['queued_notifications']=kinds
                    raise
            elif self.role=='hermes' and self.process.returncode is None:
                result=await self.request('shutdown',{})
                self.ssh_report=result.pop('ssh',None)
                assert result=={'shutdown_complete':True}
        finally:
            if not input_closed:self.process.stdin.close()
            try: await asyncio.wait_for(self.process.wait(),12)
            except TimeoutError:
                self.process.kill();await self.process.wait();raise
            finally: self.captured.append(await self.errors)
        assert self.process.returncode==0,'native_peer_exit'

@asynccontextmanager
async def clients(args,home,endpoint,owner,processes,captured,report,wait_deleted):
    peers={}
    try:
        for role in ('hermes','codex'):
            folder=home/role;folder.mkdir()
            env=child_environment(folder)
            env['VRCHAT_AGENT_TEST_TOKEN']=owner.identity.credentials[role].token
            if role=='hermes':
                env['HERMES_HOME']=str(folder)
                if args.hermes_chat:
                    (folder/'config.yaml').write_text('model:\n  context_length: 131072\n',encoding='utf-8')
                argv=[args.hermes_python,'-I','-B',str(ROOT/'tests/native_hermes_peer.py'),args.hermes_source]
            else:
                ca=folder/'public-ca.pem';ca.write_bytes(owner.tls.certificate)
                env.update(CODEX_HOME=str(folder),CODEX_CA_CERTIFICATE=str(ca))
                sys.path.insert(0,str(ROOT))
                from launcher import codex_local
                local_argv,env,config=codex_local.configuration(owner,Path(args.codex),folder,folder)
                (folder/'config.toml').write_text(config,encoding='utf-8')
                argv=[*local_argv,'app-server','--stdio']
            process=await asyncio.create_subprocess_exec(*argv,cwd=folder,env=env,
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            processes.append(process)
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None
            peer=NativePeer(process,role,captured);peers[role]=peer
            report.setdefault('native_close_observations',{}).setdefault(role,[]).append(peer.close_observation)
            peer.wait_deleted=lambda role=role:wait_deleted(role)
            report['approved_stage']=role+'_initialize'
            if role=='hermes':
                document={'endpoint':endpoint,'certificate':owner.tls.certificate.decode(),'mode':'approved-task','ssh':args.hermes_ssh,'chat':args.hermes_chat}
                if args.hermes_handoff:
                    document['handoff']={'version':1,'project':owner.project,'role':'hermes','port':owner.port,'server_port':owner.port,
                        'certificate':owner.tls.certificate.decode(),'pin':owner.tls.pin,'expires_at':owner.identity.expires_at}
                process.stdin.write((json.dumps(document)+'\n').encode());await process.stdin.drain()
                ready=await peer.request('ready',{})
                assert ready['native']=='hermes' and set(TOOLS)<=set(ready['tools'])
                if args.hermes_handoff:
                    assert ready['handoff_pass_ids']==['HJ001','HJ002']
                    report['handoff_pass_ids']=ready['handoff_pass_ids']
            else:
                await peer.request('initialize',{'clientInfo':{'name':'candidate-verifier','version':'1'},
                    'capabilities':{'experimentalApi':True}})
                process.stdin.write(b'{"method":"initialized"}\n');await process.stdin.drain()
                thread=await peer.request('thread/start',{'cwd':str(folder),'ephemeral':True,
                    'approvalPolicy':'on-request','sandbox':'read-only'})
                peer.thread=thread['thread']['id']
                data=await peer.request('mcpServerStatus/list',{'detail':'toolsAndAuthOnly','serverName':'candidate','threadId':peer.thread})
                assert data['nextCursor'] is None and len(data['data'])==1
                assert set(data['data'][0]['tools'])==set(codex_local.TOOLS) and data['data'][0]['authStatus']=='bearerToken'
        yield peers
    except BaseException as error:
        # Bounded test diagnostics; no exception values, request bodies or identities.
        import traceback
        report['primary_failure']={'type':type(error).__name__,'frames':[
            {'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name}
            for frame in traceback.extract_tb(error.__traceback__)[-8:]]}
        raise
    finally:
        results=await asyncio.gather(*(peer.close() for peer in peers.values()),return_exceptions=True)
        if args.hermes_ssh and 'hermes' in peers:
            report['ssh']=peers['hermes'].ssh_report
            assert report['ssh'] is not None and report['ssh']['ssh_authenticated']
        if any(isinstance(result,BaseException) for result in results):
            raise AssertionError('native_peer_cleanup_failed')

async def fresh_gate(args,home,processes,captured,report):
    work=home/'gate-build';work.mkdir()
    env=child_environment(work)
    env.update(DOTNET_ROOT=str(Path(args.dotnet).parent),DOTNET_CLI_HOME=str(work),TMPDIR=str(work),TEMP=str(work),TMP=str(work))
    command=[args.dotnet,'build',str(ROOT/'tests/unity-core/WirePeer.csproj'),'--configuration','Release',
        '--disable-build-servers','-p:UseSharedCompilation=false','-p:NuGetAudit=false','-p:RestoreSources=',
        '-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),
        '-p:BaseIntermediateOutputPath='+str(work/'obj')+'/', '-p:BaseOutputPath='+str(work/'bin')+'/']
    process=await asyncio.create_subprocess_exec(*command,cwd=work,env=env,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    processes.append(process)
    out,err=await asyncio.wait_for(process.communicate(),90);captured.extend((out,err))
    assert process.returncode==0,'fresh_compiled_gate_build_failed'
    dll=work/'bin/Release/net8.0/WirePeer.dll';assert dll.is_file()
    report['fresh_gate_built']=True
    return dll

async def check_approved_tasks(args,home,endpoint,owner,runtime,processes,captured,report,created,deleted):
    async def wait_deleted(role):
        started=asyncio.get_running_loop().time()
        expected=set(created.get(role,set()))
        assert expected,'native_cleanup_without_session'
        try:
            while deleted.get(role,set()) != expected:
                await asyncio.sleep(.02)
        finally:
            report.setdefault('delete_observer_snapshots',{}).setdefault(role,[]).append({
                'expected':len(expected),'confirmed':len(deleted.get(role,set())),
                'runtime_sessions':len(runtime.sessions),'credential_live':__import__('time').time()<owner.identity.expires_at})
        report.setdefault('native_delete_confirmations',{}).setdefault(role,[]).append({
            'session_count':len(expected),'elapsed_seconds':asyncio.get_running_loop().time()-started})
    report['approved_task_scope']='real native MCP clients; net8 gates/file-backed Unity fixture; no model, Unity Editor, human UI or trusted delivery'
    report['approved_stage']='fresh_gate_build'
    binding.WIRE_DLL=await fresh_gate(args,home,processes,captured,report)
    binding.DOTNET=Path(args.dotnet)
    case=binding.ClientBindingTests();case.use_core=True
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.load_verify_locations(cadata=owner.tls.certificate.decode())
    async with websockets.connect(endpoint.removesuffix('/mcp').replace('https:','wss:')+'/hub/plugin',
        proxy=None,ssl=context,additional_headers={'Authorization':'Bearer '+owner.identity.credentials['unity'].token}) as socket:
        connection=await case.register(socket)
        async with case.core_peer(connection) as exchange:
            assert exchange is not None
            async def respond():
                async for raw in socket:
                    message=json.loads(raw)
                    if message['type']=='ping':
                        await socket.send(json.dumps({'type':'pong','session_id':connection}));continue
                    result=await exchange({'request':message['params'],'route':message['name']})
                    await socket.send(json.dumps({'type':'command_result','id':message['id'],'result':result}))
            responder=asyncio.create_task(respond())
            try:
                async with clients(args,home,endpoint,owner,processes,captured,report,wait_deleted) as peers:
                    report['approved_stage']='both_native_peers_ready'
                    report['native_peers_ready']=True
                    checks=[]
                    report['native_approved_pass_ids']=checks
                    async def data(role,tool,arguments):
                        value=await peers[role].call(tool,arguments)
                        assert not value.get('isError'), 'native_tool_error'
                        result=value['structuredContent']
                        if tool in ('get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items'):
                            assert set(result)=={'result'};result=result['result']
                        assert result['success'] is True,'gate_error'
                        return result['data']
                    async def denied(role,tool,arguments):
                        value=await peers[role].call(tool,arguments)
                        assert_denied_result(value,tool)
                    async def plans(material=False):
                        return (await exchange({'fixture_local_plans':True,
                            'route':'vrchat_agent_material_dispatch' if material else 'vrchat_agent_dispatch'}))['fixture_plans']
                    async def approve(plan,material=False):
                        assert (await exchange({'fixture_approve_exact':plan,
                            'route':'vrchat_agent_material_dispatch' if material else 'vrchat_agent_dispatch'}))['fixture_approved']
                    report['native_catalog_pass_ids']=[]
                    expected_catalog=json.loads((ROOT/'catalog/native-inventory.json').read_text(encoding='utf-8'))
                    for role in ('hermes','codex'):
                        rows=[];offset=0
                        while True:
                            value=await peers[role].call('agent_catalog',{'offset':offset,'limit':12})
                            assert not value.get('isError'),'native_catalog_not_exposed'
                            page=value['structuredContent']
                            assert page['permission_grant'] is False and page['returned']==len(page['tools'])
                            rows.extend(page['tools'])
                            if page['next_offset'] is None:break
                            assert page['next_offset']==offset+len(page['tools'])
                            offset=page['next_offset']
                        assert [row['name'] for row in rows]==[row['name'] for row in expected_catalog['tools']]
                        assert page['total']==len(rows) and await plans()==[] and await plans(True)==[]
                        report['native_catalog_pass_ids'].append('NC001' if role=='hermes' else 'NC002')
                    report['native_console_pass_ids']=[]
                    console_prepare={'task_id':'console-task','operations':[{'command':'read_console','action':'get'}],
                                     'targets':['Console'],'ttl_seconds':120}
                    console_args={'action':'get','page_size':2,'cursor':0,'format':'json','include_stacktrace':True}
                    for role,other,ident in (('hermes','codex','NQ001'),('codex','hermes','NQ002')):
                        report['approved_stage']='console_'+role
                        plan=await data(role,'agent_prepare',console_prepare)
                        assert plan['status']=='pending'
                        await denied(role,'read_console',console_args)
                        plan=await data(role,'agent_prepare',console_prepare)
                        await approve(plan)
                        await denied(other,'read_console',console_args)
                        rows=[];cursor=0
                        while True:
                            page=await data(role,'read_console',{**console_args,'cursor':cursor})
                            assert page['cursor']==cursor and page['pageSize']==2
                            rows.extend(page['items'])
                            if not page['truncated']:
                                assert page['nextCursor'] is None and page['total']==len(rows)
                                break
                            assert page['total']==cursor+3 and page['nextCursor']==str(cursor+2)
                            cursor=int(page['nextCursor'])
                        assert len(rows)==5 and len({r['message'] for r in rows})==5
                        assert all(r['file']=='Assets/Fixture.cs' for r in rows)
                        await data(role,'agent_stop',{'task_id':'console-task'})
                        await denied(role,'read_console',console_args)
                        plan=await data(role,'agent_prepare',console_prepare);await approve(plan)
                        await denied(role,'read_console',{**console_args,'action':'clear'})
                        await data(role,'agent_stop',{'task_id':'console-task'})
                        assert await plans()==[]
                        report['native_console_pass_ids'].append(ident)
                    report['native_pause_pass_ids']=[]
                    async def pause_resume(role,plan,tool,arguments,material=False):
                        route='vrchat_agent_material_dispatch' if material else 'vrchat_agent_dispatch'
                        assert (await exchange({'fixture_pause_exact':plan,'route':route}))['fixture_paused']
                        value=await peers[role].call(tool,arguments)
                        assert value.get('structuredContent',{}).get('success') is False
                        paused=value['structuredContent']['data']
                        assert paused=={'status':'paused','reason':'plan_paused','plan_id':plan['plan_id']}
                        remaining=await plans(material)
                        assert any(p['plan_id']==plan['plan_id'] and p['paused'] for p in remaining),'paused_plan_lost'
                        assert (await exchange({'fixture_resume_exact':plan,'route':route}))['fixture_resumed']
                        await data(role,tool,arguments)
                    report['native_scene_pass_ids']=[]
                    scene_prepare={'task_id':'scene-task','operations':[
                        {'command':'manage_scene','action':a} for a in ('get_active','get_build_settings','get_loaded_scenes')],
                        'targets':['Scenes'],'ttl_seconds':120}
                    for role,other,ident in (('hermes','codex','NE001'),('codex','hermes','NE002')):
                        report['approved_stage']='scene_'+role
                        plan=await data(role,'agent_prepare',scene_prepare)
                        await denied(role,'manage_scene',{'action':'get_active'})
                        plan=await data(role,'agent_prepare',scene_prepare);await approve(plan)
                        await denied(other,'manage_scene',{'action':'get_active'})
                        for action in ('get_active','get_build_settings','get_loaded_scenes'):
                            value=await data(role,'manage_scene',{'action':action})
                            assert value is not None
                        await pause_resume(role,plan,'manage_scene',{'action':'get_active'})
                        await data(role,'agent_stop',{'task_id':'scene-task'})
                        await denied(role,'manage_scene',{'action':'get_active'})
                        plan=await data(role,'agent_prepare',scene_prepare);await approve(plan)
                        await denied(role,'manage_scene',{'action':'save'})
                        await data(role,'agent_stop',{'task_id':'scene-task'})
                        assert await plans()==[]
                        report['native_scene_pass_ids'].append(ident)
                    report['native_validate_pass_ids']=[]
                    validate_prepare={'task_id':'validate-task','operations':[{'command':'manage_scene','action':'validate'}],
                                      'targets':['Scenes'],'ttl_seconds':120}
                    validate_args={'action':'validate','auto_repair':False}
                    for role,other,ident in (('hermes','codex','NV001'),('codex','hermes','NV002')):
                        report['approved_stage']='validate_'+role
                        plan=await data(role,'agent_prepare',validate_prepare);await denied(role,'manage_scene',validate_args)
                        plan=await data(role,'agent_prepare',validate_prepare);await approve(plan)
                        await denied(other,'manage_scene',validate_args)
                        value=await data(role,'manage_scene',validate_args)
                        assert value['repaired']==0 and value['totalIssues']==0 and value['issues']==[]
                        await pause_resume(role,plan,'manage_scene',validate_args)
                        await denied(role,'manage_scene',{**validate_args,'auto_repair':True})
                        plan=await data(role,'agent_prepare',validate_prepare);await approve(plan)
                        await data(role,'agent_stop',{'task_id':'validate-task'})
                        await denied(role,'manage_scene',validate_args);assert await plans()==[]
                        report['native_validate_pass_ids'].append(ident)
                    assert report['native_validate_pass_ids']==['NV001','NV002']
                    report['native_find_pass_ids']=[]
                    find_prepare={'task_id':'find-task','operations':[{'command':'find_gameobjects','action':'find'}],
                                  'targets':['Scenes'],'ttl_seconds':120}
                    for role,other,ident in (('hermes','codex','NF001'),('codex','hermes','NF002')):
                        report['approved_stage']='find_'+role
                        find_args={'search_term':'fixture','search_method':'by_name','include_inactive':True,'page_size':2}
                        plan=await data(role,'agent_prepare',find_prepare);await denied(role,'find_gameobjects',find_args)
                        plan=await data(role,'agent_prepare',find_prepare);await approve(plan)
                        await denied(other,'find_gameobjects',find_args)
                        first=await data(role,'find_gameobjects',find_args)
                        last=await data(role,'find_gameobjects',{**find_args,'cursor':2})
                        assert first['instanceIDs']==[11,12] and first['nextCursor']==2 and first['hasMore']
                        assert last['instanceIDs']==[13] and last['nextCursor'] is None and not last['hasMore']
                        await pause_resume(role,plan,'find_gameobjects',find_args)
                        for term in ('Transform','Probe.Component, ReadOnlyProbeMissingAssembly'):
                            await denied(role,'find_gameobjects',{**find_args,'search_term':term,'search_method':'by_component'})
                            plan=await data(role,'agent_prepare',find_prepare);await approve(plan)
                        await denied(role,'find_gameobjects',{**find_args,'include_inactive':'true'})
                        plan=await data(role,'agent_prepare',find_prepare);await approve(plan)
                        await data(role,'agent_stop',{'task_id':'find-task'})
                        await denied(role,'find_gameobjects',find_args);assert await plans()==[]
                        report['native_find_pass_ids'].append(ident)
                    assert report['native_find_pass_ids']==['NF001','NF002']
                    report['native_object_pass_ids']=[]
                    for role,other,ident in (('hermes','codex','NO001'),('codex','hermes','NO002')):
                        report['approved_stage']='object_'+role
                        for command,object_args in (('get_gameobject',{'instance_id':'11'}),
                                ('get_gameobject_components',{'instance_id':'11','page_size':2,'include_properties':False})):
                            prepare={'task_id':'object-task','operations':[{'command':command,'action':'read'}],'targets':['Scenes'],'ttl_seconds':120}
                            plan=await data(role,'agent_prepare',prepare);await denied(role,command,object_args)
                            plan=await data(role,'agent_prepare',prepare);await approve(plan)
                            await denied(other,command,object_args)
                            value=await data(role,command,object_args)
                            if command=='get_gameobject': assert value['instanceID']==11 and value['componentTypes']==['Transform']
                            else:
                                assert len(value['components'])==2 and value['nextCursor']==2 and not value['includeProperties']
                                last=await data(role,command,{**object_args,'cursor':2})
                                assert len(last['components'])==1 and last['nextCursor'] is None
                            await pause_resume(role,plan,command,object_args)
                            await denied(role,command,{**object_args,'include_properties':True})
                            plan=await data(role,'agent_prepare',prepare);await approve(plan)
                            await data(role,'agent_stop',{'task_id':'object-task'})
                            await denied(role,command,object_args);assert await plans()==[]
                        report['native_object_pass_ids'].append(ident)
                    assert report['native_object_pass_ids']==['NO001','NO002']
                    report['native_project_metadata_pass_ids']=[]
                    metadata_prepare={'task_id':'metadata-task','operations':[{'command':name,'action':'read'} for name in ('get_project_info','get_tags','get_layers')],'targets':['ProjectMetadata'],'ttl_seconds':120}
                    for role,other,ident in (('hermes','codex','NMD001'),('codex','hermes','NMD002')):
                        report['approved_stage']='project_metadata_'+role
                        plan=await data(role,'agent_prepare',metadata_prepare)
                        await denied(role,'get_project_info',{})
                        plan=await data(role,'agent_prepare',metadata_prepare);await approve(plan)
                        await denied(other,'get_project_info',{})
                        assert (await data(role,'get_project_info',{}))['projectRoot']=='/Fixture'
                        assert await data(role,'get_tags',{})==['Untagged','Player']
                        assert await data(role,'get_layers',{})=={'0':'Default','5':'UI'}
                        assert (await exchange({'fixture_pause_exact':plan,'route':'vrchat_agent_dispatch'}))['fixture_paused']
                        value=await peers[role].call('get_tags',{})
                        assert value.get('isError') is True
                        assert value['structuredContent']['result']['error']=='plan_paused'
                        assert any(p['plan_id']==plan['plan_id'] and p['paused'] for p in await plans())
                        assert (await exchange({'fixture_resume_exact':plan,'route':'vrchat_agent_dispatch'}))['fixture_resumed']
                        assert await data(role,'get_tags',{})==['Untagged','Player']
                        await data(role,'agent_stop',{'task_id':'metadata-task'})
                        await denied(role,'get_tags',{})
                        report['native_project_metadata_pass_ids'].append(ident)
                    report['native_package_metadata_pass_ids']=[]
                    package_prepare={'task_id':'package-metadata','operations':[{'command':'manage_packages','action':'get_package_info'}],'targets':['ProjectMetadata'],'ttl_seconds':120}
                    package_args={'action':'get_package_info','package':'com.unity.ugui'}
                    for role,other,ident in (('hermes','codex','NPK001'),('codex','hermes','NPK002')):
                        report['approved_stage']='package_metadata_'+role
                        plan=await data(role,'agent_prepare',package_prepare)
                        await denied(role,'manage_packages',package_args)
                        plan=await data(role,'agent_prepare',package_prepare);await approve(plan)
                        await denied(other,'manage_packages',package_args)
                        assert (await data(role,'manage_packages',package_args))['name']=='com.unity.ugui'
                        assert (await exchange({'fixture_pause_exact':plan,'route':'vrchat_agent_dispatch'}))['fixture_paused']
                        value=await peers[role].call('manage_packages',package_args)
                        assert value.get('isError') is True and value['structuredContent']['error']=='plan_paused'
                        assert any(p['plan_id']==plan['plan_id'] and p['paused'] for p in await plans())
                        assert (await exchange({'fixture_resume_exact':plan,'route':'vrchat_agent_dispatch'}))['fixture_resumed']
                        assert (await data(role,'manage_packages',package_args))['dependency_count']==0
                        await data(role,'agent_stop',{'task_id':'package-metadata'})
                        await denied(role,'manage_packages',package_args)
                        report['native_package_metadata_pass_ids'].append(ident)
                    report['native_menu_metadata_pass_ids']=[]
                    report['native_editor_metadata_pass_ids']=[]
                    editor_prepare={'task_id':'editor-metadata-task','operations':[{'command':name,'action':'read'} for name in ('get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items')],'targets':['EditorMetadata'],'ttl_seconds':120}
                    for role,other,ident in (('hermes','codex','NEM001'),('codex','hermes','NEM002')):
                        report['approved_stage']='editor_metadata_'+role
                        plan=await data(role,'agent_prepare',editor_prepare);await denied(role,'get_selection',{})
                        plan=await data(role,'agent_prepare',editor_prepare);await approve(plan)
                        await denied(other,'get_selection',{})
                        assert (await data(role,'get_selection',{}))['count']==0
                        assert await data(role,'get_windows',{})==[]
                        assert (await data(role,'get_active_tool',{}))['activeTool']=='Move'
                        assert (await data(role,'get_prefab_stage',{}))['isOpen'] is False
                        assert await data(role,'get_menu_items',{})==['Tools/Fixture']
                        assert (await exchange({'fixture_pause_exact':plan,'route':'vrchat_agent_dispatch'}))['fixture_paused']
                        value=await peers[role].call('get_windows',{})
                        assert value.get('isError') is True and value['structuredContent']['result']['error']=='plan_paused'
                        assert any(p['plan_id']==plan['plan_id'] and p['paused'] for p in await plans())
                        assert (await exchange({'fixture_resume_exact':plan,'route':'vrchat_agent_dispatch'}))['fixture_resumed']
                        assert await data(role,'get_windows',{})==[]
                        await data(role,'agent_stop',{'task_id':'editor-metadata-task'})
                        await denied(role,'get_windows',{})
                        await denied(role,'get_menu_items',{})
                        report['native_menu_metadata_pass_ids'].append('NMN001' if role=='hermes' else 'NMN002')
                        report['native_editor_metadata_pass_ids'].append(ident)
                    report['native_animator_pass_ids']=[]
                    for role,other,ident in (('hermes','codex','NI001'),('codex','hermes','NI002')):
                        report['approved_stage']='animator_'+role
                        for action in ('animator_get_info','animator_get_parameter'):
                            animator_args: dict[str, object]={'action':action,'target':'11','search_method':'by_id'}
                            if action=='animator_get_parameter':animator_args['properties']={'parameter_name':'Speed'}
                            prepare={'task_id':'animator-task','operations':[{'command':'manage_animation','action':action}],
                                     'targets':['Scenes'],'ttl_seconds':120}
                            plan=await data(role,'agent_prepare',prepare);await denied(role,'manage_animation',animator_args)
                            plan=await data(role,'agent_prepare',prepare);await approve(plan)
                            await denied(other,'manage_animation',animator_args)
                            value=await data(role,'manage_animation',animator_args)
                            if action=='animator_get_info':assert value['gameObject']=='Avatar' and value['parameterCount']==0
                            else:assert value=={'name':'Speed','type':'Float','value':0.5}
                            await pause_resume(role,plan,'manage_animation',animator_args)
                            await denied(role,'manage_animation',{**animator_args,'search_method':'by_name'})
                            plan=await data(role,'agent_prepare',prepare);await approve(plan)
                            await data(role,'agent_stop',{'task_id':'animator-task'})
                            await denied(role,'manage_animation',animator_args);assert await plans()==[]
                        report['native_animator_pass_ids'].append(ident)
                    assert report['native_animator_pass_ids']==['NI001','NI002']
                    report['native_hierarchy_pass_ids']=[]
                    hierarchy_prepare={'task_id':'hierarchy-task','operations':[{'command':'manage_scene','action':'get_hierarchy'}],
                                       'targets':['Scenes'],'ttl_seconds':120}
                    for role,other,ident in (('hermes','codex','NH001'),('codex','hermes','NH002')):
                        report['approved_stage']='hierarchy_'+role
                        hierarchy_args={'action':'get_hierarchy','page_size':2,'include_transform':True}
                        plan=await data(role,'agent_prepare',hierarchy_prepare);await denied(role,'manage_scene',hierarchy_args)
                        plan=await data(role,'agent_prepare',hierarchy_prepare);await approve(plan)
                        await denied(other,'manage_scene',hierarchy_args)
                        first=await data(role,'manage_scene',hierarchy_args);last=await data(role,'manage_scene',{**hierarchy_args,'cursor':2})
                        assert first['total']==3 and first['next_cursor']=='2' and len(first['items'])==2
                        assert not last['truncated'] and last['next_cursor'] is None and len(last['items'])==1
                        assert len({x['instanceID'] for x in first['items']+last['items']})==3
                        children=await data(role,'manage_scene',{**hierarchy_args,'parent':11})
                        assert children['scope']=='children' and children['items'][0]['instanceID']==44
                        await pause_resume(role,plan,'manage_scene',hierarchy_args)
                        await denied(role,'manage_scene',{**hierarchy_args,'parent':'11'})
                        plan=await data(role,'agent_prepare',hierarchy_prepare);await approve(plan)
                        await data(role,'agent_stop',{'task_id':'hierarchy-task'})
                        await denied(role,'manage_scene',hierarchy_args);assert await plans()==[]
                        report['native_hierarchy_pass_ids'].append(ident)
                    assert report['native_hierarchy_pass_ids']==['NH001','NH002']
                    read_plans={}
                    report['approved_stage']='NA001_signed_local_plans'
                    for role in ('hermes','codex'):
                        read_plans[role]=await data(role,'agent_prepare',PREPARE)
                    local=await plans()
                    assert len(local)==2
                    for role in ('hermes','codex'):
                        assert len(created[role])==1
                        sid=next(iter(created[role])).decode()
                        plan=next(p for p in local if p['plan_id']==read_plans[role]['plan_id'])
                        assert json.loads(plan['client_id'])==[owner.identity.credentials[role].principal,sid]
                    checks.append('NA001')
                    report['approved_stage']='NA002_separate_local_approval'
                    await approve(read_plans['hermes'])
                    await data('hermes','manage_material',READ)
                    await denied('codex','manage_material',READ)
                    await data('hermes','manage_material',READ)
                    read_plans['codex']=await data('codex','agent_prepare',PREPARE)
                    await approve(read_plans['codex'])
                    await data('codex','manage_material',READ)
                    checks.append('NA002')
                    for role,number in [('hermes',1),('codex',2)]:
                        report['approved_stage']='NP00'+str(number)+'_read_pause_'+role
                        await pause_resume(role,read_plans[role],'manage_material',READ)
                        report['native_pause_pass_ids'].append('NP00'+str(number))
                    manifests={role:{**MANIFEST,'source':'Assets/source.mat',
                        'candidate':'Assets/candidate.mat' if role=='hermes' else 'Assets/codex-candidate.mat',
                        'operations':['copy','edit'],'references':[]} for role in ('hermes','codex')}
                    material_plans={}
                    async def file_bytes():
                        return {role:await exchange({'fixture_bytes':role}) for role in ('hermes','codex')}
                    report['approved_stage']='NA003_single_writer_no_cross_client_takeover'
                    for role,other,value in (('hermes','codex',.625),('codex','hermes',.875)):
                        material_plans[role]=await data(role,'material_prepare',manifests[role])
                        await approve(material_plans[role],True)
                        for action,arguments in [('copy',{}),('edit',{'property':'_Value','value':value})]:
                            await data(role,'material_execute',{'task_id':MANIFEST['task_id'],
                                'plan_id':material_plans[role]['plan_id'],'action':action,'arguments':arguments})
                        number=3 if role=='hermes' else 4
                        report['approved_stage']='NP00'+str(number)+'_material_pause_'+role
                        await pause_resume(role,material_plans[role],'material_execute',
                            {'task_id':MANIFEST['task_id'],'plan_id':material_plans[role]['plan_id'],
                             'action':'edit','arguments':{'property':'_Value','value':.625 if role=='hermes' else .875}},True)
                        report['native_pause_pass_ids'].append('NP00'+str(number))
                        before=await file_bytes()
                        denied_result=await peers[other].call('material_prepare',manifests[other])
                        assert denied_result.get('isError') and denied_result['structuredContent']['error']=='project_write_busy'
                        await denied(other,'material_stop',{'task_id':MANIFEST['task_id'],
                            'plan_id':material_plans[role]['plan_id']})
                        assert [p['plan_id'] for p in await plans(True)]==[material_plans[role]['plan_id']]
                        # Both clients' independently approved reads survive a rejected write takeover.
                        for reader in ('hermes','codex'): await data(reader,'manage_material',READ)
                        stopped=await data(role,'material_stop',{'task_id':MANIFEST['task_id'],
                            'plan_id':material_plans[role]['plan_id']})
                        assert stopped['status']=='stopped' and await plans(True)==[]
                        await denied(role,'material_execute',{'task_id':MANIFEST['task_id'],
                            'plan_id':material_plans[role]['plan_id'],'action':'edit',
                            'arguments':{'property':'_Value','value':.125}})
                        assert await file_bytes()==before
                    before=await file_bytes()
                    report['fixture_bytes_before_stop']=before
                    assert before=={'hermes':{'source':'original','candidate':'0.625','writes':6},
                                    'codex':{'source':'original','candidate':'0.875','writes':6}}
                    checks.append('NA003')
                    report['approved_stage']='NA004_explicit_stop_isolation_without_rollback'
                    for role,other in (('hermes','codex'),('codex',None)):
                        stopped=await data(role,'agent_stop',{'task_id':PREPARE['task_id']})
                        assert stopped['status']=='stopped'
                        await denied(role,'manage_material',READ)
                        assert await file_bytes()==before
                        if other:
                            assert [p['plan_id'] for p in await plans()]==[read_plans[other]['plan_id']]
                            await data(other,'manage_material',READ)
                    assert await plans()==[] and await plans(True)==[]
                    checks.append('NA004')
                    report['approved_stage']='NA005_new_plans_need_new_local_approval'
                    for role in ('hermes','codex'):
                        current=await data(role,'agent_prepare',PREPARE)
                        assert current['plan_id']!=read_plans[role]['plan_id'] and current['status']=='pending'
                        await denied(role,'manage_material',READ)
                        current=await data(role,'agent_prepare',PREPARE)
                        await approve(current);read_plans[role]=current
                    assert await file_bytes()==before
                    checks.append('NA005')
                    report['approved_stage']='NA006_native_session_delete_revoke_both_families'
                    for role,other in (('hermes','codex'),('codex',None)):
                        material_plans[role]=await data(role,'material_prepare',{**manifests[role],'operations':['edit']})
                        pending_id=material_plans[role]['plan_id']
                        assert material_plans[role]['status']=='pending'
                        await denied(role,'material_execute',{'task_id':MANIFEST['task_id'],
                            'plan_id':pending_id,'action':'edit','arguments':{'property':'_Value','value':.125}})
                        assert await file_bytes()==before
                        material_plans[role]=await data(role,'material_prepare',{**manifests[role],'operations':['edit']})
                        assert material_plans[role]['plan_id']!=pending_id and material_plans[role]['status']=='pending'
                        await approve(material_plans[role],True)
                        sid=next(iter(created[role])).decode()
                        await peers[role].close()
                        async with asyncio.timeout(5):
                            while len([r for r in runtime.lifecycle_results if r.get('client_id')==sid and r.get('plan_id') in
                                {read_plans[role]['plan_id'],material_plans[role]['plan_id']}])<2:
                                await asyncio.sleep(.02)
                        receipts=[r for r in runtime.lifecycle_results if r.get('client_id')==sid and r.get('plan_id') in
                            {read_plans[role]['plan_id'],material_plans[role]['plan_id']}]
                        assert len(receipts)==2 and all(r['unity_confirmed'] for r in receipts)
                        assert deleted.get(role)==created[role]
                        assert await file_bytes()==before and await plans(True)==[]
                        if other:
                            assert [p['plan_id'] for p in await plans()]==[read_plans[other]['plan_id']]
                            await data(other,'manage_material',READ)
                    assert await plans()==[] and await plans(True)==[]
                    assert not runtime.sessions and not runtime.session_identities and not runtime.plans
                    assert not runtime.material.plans and not runtime.material.history
                    checks.append('NA006')
                    assert report['native_pause_pass_ids']==[f'NP{i:03d}' for i in range(1,5)]
                    report['native_recovery_pass_ids']=[]
                    report['approved_stage']='NR001_reload_history_without_grants'
                    loaded=await exchange({'fixture_reload_material':True})
                    assert loaded['fixture_reloaded'] and loaded['plans']==[] and loaded['capabilities']==[], 'reload_restored_grant'
                    report['native_recovery_pass_ids'].append('NR001')
                    history=(await exchange({'fixture_material_records':True}))['records']
                    await exchange({'fixture_material_capabilities':['edit']})
                    recovery_home=home/'recovery-clients';recovery_home.mkdir()
                    async with clients(args,recovery_home,endpoint,owner,processes,captured,report,wait_deleted) as peers:
                        for role in ('hermes','codex'):
                            report['approved_stage']='NR002_explicit_recovery_'+role
                            pending=await data(role,'material_prepare',{**manifests[role],'operations':['edit']})
                            record=next(r for r in history if r['record_id']==pending['recovery_record_id'])
                            current=(await plans(True))[0]
                            assert json.loads(current['client_id'])[0]==owner.identity.credentials[role].principal
                            assert current['client_id']!=record['client_id'], 'old_sdk_identity_reused'
                            assert not (await exchange({'fixture_approve_exact':pending,'route':'vrchat_agent_material_dispatch'}))['fixture_approved']
                            arguments={'task_id':MANIFEST['task_id'],'plan_id':pending['plan_id'],'action':'edit','arguments':{'property':'_Value','value':.125}}
                            await denied(role,'material_execute',arguments)
                            assert await file_bytes()==before
                            pending=await data(role,'material_prepare',{**manifests[role],'operations':['edit']})
                            assert (await exchange({'fixture_recover_exact':{'plan_id':pending['plan_id'],'digest':pending['digest'],
                                'record_id':record['record_id'],'record_digest':record['digest']}}))['fixture_recovered']
                            # Confirm the production native tool route uses the new approval, no copy/replay.
                            await data(role,'material_execute',{'task_id':MANIFEST['task_id'],'plan_id':pending['plan_id'],'action':'edit',
                                'arguments':{'property':'_Value','value':.625 if role=='hermes' else .875}})
                            await data(role,'material_stop',{'task_id':MANIFEST['task_id'],'plan_id':pending['plan_id']})
                            before=await file_bytes()
                            assert before[role]['candidate']==('0.625' if role=='hermes' else '0.875') and before[role]['source']=='original'
                        report['native_recovery_pass_ids'].append('NR002')
                    assert await plans(True)==[]
                    assert report['native_recovery_pass_ids']==['NR001','NR002']
                    report['approved_stage']='completed'
            finally:
                responder.cancel();await asyncio.gather(responder,return_exceptions=True)
    report['session_cleanup']={role:{'created':len(created.get(role,set())),'deleted':len(deleted.get(role,set()))} for role in ('hermes','codex')}
    for role in ('hermes','codex'):
        assert len(created.get(role,set()))==2 and created[role]==deleted.get(role,set())
    assert created['hermes'].isdisjoint(created['codex'])
