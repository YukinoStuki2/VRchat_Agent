"""TEST ONLY: native clients plus compiled gates, not a product handoff/Unity UI.
The verifier owns the gate stdin approval channel. Neither client receives it.
"""
import asyncio
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
TOOLS = ['agent_status','agent_catalog','agent_prepare','agent_stop','manage_material','read_console','manage_scene',
         'material_prepare','material_execute','material_stop']

class NativePeer:
    """Test-only NDJSON client to installed Hermes adapter/official Codex app-server."""
    def __init__(self, process, role, captured):
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        self.process, self.role, self.captured = process, role, captured
        self.errors = asyncio.create_task(process.stderr.read())
        self.number = 0
        self.thread = None
        self.closed = False
        self.ssh_report = None

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
        try:
            if self.role=='codex' and self.thread:
                await self.request('thread/unsubscribe',{'threadId':self.thread})
            elif self.role=='hermes' and self.process.returncode is None:
                result=await self.request('shutdown',{})
                self.ssh_report=result.pop('ssh',None)
                assert result=={'shutdown_complete':True}
        finally:
            self.process.stdin.close()
            try: await asyncio.wait_for(self.process.wait(),12)
            except TimeoutError:
                self.process.kill();await self.process.wait();raise
            finally: self.captured.append(await self.errors)
        assert self.process.returncode==0,'native_peer_exit'

@asynccontextmanager
async def clients(args,home,endpoint,owner,processes,captured,report):
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
                async with clients(args,home,endpoint,owner,processes,captured,report) as peers:
                    report['approved_stage']='both_native_peers_ready'
                    report['native_peers_ready']=True
                    checks=[]
                    report['native_approved_pass_ids']=checks
                    async def data(role,tool,arguments):
                        value=await peers[role].call(tool,arguments)
                        assert not value.get('isError'), 'native_tool_error'
                        result=value['structuredContent'];assert result['success'] is True,'gate_error'
                        return result['data']
                    async def denied(role,tool,arguments):
                        value=await peers[role].call(tool,arguments)
                        assert value.get('isError') is True or value.get('structuredContent',{}).get('success') is False
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
                    async with clients(args,recovery_home,endpoint,owner,processes,captured,report) as peers:
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
