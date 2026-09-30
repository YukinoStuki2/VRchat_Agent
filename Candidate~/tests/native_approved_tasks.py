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
TOOLS = ['agent_status','agent_prepare','agent_stop','manage_material',
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
                argv=[args.hermes_python,'-I','-B',str(ROOT/'tests/native_hermes_peer.py'),args.hermes_source]
            else:
                ca=folder/'public-ca.pem';ca.write_bytes(owner.tls.certificate)
                env.update(CODEX_HOME=str(folder),CODEX_CA_CERTIFICATE=str(ca))
                config='[features]\nplugins = false\n[analytics]\nenabled = false\n[feedback]\nenabled = false\n[mcp_servers.candidate]\n'
                config+='url = '+json.dumps(endpoint)+'\nbearer_token_env_var = "VRCHAT_AGENT_TEST_TOKEN"\n'
                config+='startup_timeout_sec = 8\ntool_timeout_sec = 8\nrequired = true\nenabled_tools = '+json.dumps(TOOLS)+'\n'
                (folder/'config.toml').write_text(config,encoding='utf-8')
                argv=[args.codex,'app-server','--stdio']
            process=await asyncio.create_subprocess_exec(*argv,cwd=folder,env=env,
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            processes.append(process)
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None
            peer=NativePeer(process,role,captured);peers[role]=peer
            report['approved_stage']=role+'_initialize'
            if role=='hermes':
                process.stdin.write((json.dumps({'endpoint':endpoint,'certificate':owner.tls.certificate.decode(),
                    'mode':'approved-task'})+'\n').encode());await process.stdin.drain()
                ready=await peer.request('ready',{})
                assert ready['native']=='hermes' and set(TOOLS)<=set(ready['tools'])
            else:
                await peer.request('initialize',{'clientInfo':{'name':'candidate-verifier','version':'1'},
                    'capabilities':{'experimentalApi':True}})
                process.stdin.write(b'{"method":"initialized"}\n');await process.stdin.drain()
                thread=await peer.request('thread/start',{'cwd':str(folder),'ephemeral':True,
                    'approvalPolicy':'on-request','sandbox':'read-only'})
                peer.thread=thread['thread']['id']
                data=await peer.request('mcpServerStatus/list',{'detail':'toolsAndAuthOnly','serverName':'candidate','threadId':peer.thread})
                assert data['nextCursor'] is None and len(data['data'])==1
                assert set(data['data'][0]['tools'])==set(TOOLS) and data['data'][0]['authStatus']=='bearerToken'
        yield peers
    finally:
        results=await asyncio.gather(*(peer.close() for peer in peers.values()),return_exceptions=True)
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
                    assert before=={'hermes':{'source':'original','candidate':'0.625','writes':4},
                                    'codex':{'source':'original','candidate':'0.875','writes':4}}
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
                    report['approved_stage']='completed'
            finally:
                responder.cancel();await asyncio.gather(responder,return_exceptions=True)
    report['session_cleanup']={role:{'created':len(created.get(role,set())),'deleted':len(deleted.get(role,set()))} for role in ('hermes','codex')}
    for role in ('hermes','codex'):
        assert len(created.get(role,set()))==1 and created[role]==deleted.get(role,set())
    assert created['hermes'].isdisjoint(created['codex'])
