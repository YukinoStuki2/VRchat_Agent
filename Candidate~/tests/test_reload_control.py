"""Local OS control + real SDK fixtures; not installed owner/Editor acceptance.
C# grant/evidence messages remain fixtures until the cross-language gate runs.
"""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'runtime')]
import test_runtime_handoff as fixtures
from fastmcp import Client

class ReloadControlTests(unittest.IsolatedAsyncioTestCase):
    fixture=fixtures.RuntimeHandoffTests.fixture
    editor=fixtures.RuntimeHandoffTests.editor
    connect=fixtures.RuntimeHandoffTests.connect
    register=fixtures.RuntimeHandoffTests.register
    closed=fixtures.RuntimeHandoffTests.closed

    @asynccontextmanager
    async def prepared(self):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                async with self.editor(url,tokens['unity']) as editor:
                    await client.call_tool('agent_prepare',fixtures.PREPARE)
                    await client.call_tool('material_prepare',{'task_id':'material-task','source':'Assets/Original.mat',
                        'candidate':'Assets/Candidate.mat','operations':['copy'],'references':[],'ttl_seconds':60})
                    yield runtime,client,editor,url,tokens

    async def test_OC001_prepare_retains_exact_digest_for_both_frozen_cohorts(self):
        async with self.prepared() as (runtime,client,editor,url,tokens):
            for plans in (runtime.plans,runtime.material.plans):
                self.assertEqual(len(plans),1)
                self.assertEqual(getattr(next(iter(plans.values())),'approval_digest',None),'a'*64,
                    'runtime drops original approval digest before reload verification')

    def transfers(self,runtime,handoff):
        import time
        now=10.0 # Editor clock is a fixture, deliberately not Python monotonic.
        result=[]
        for gate,plans in [('read',runtime.plans),('material',runtime.material.plans)]:
            rows=[]
            for plan in plans.values():
                manifest=plan.manifest if gate=='material' else {
                    'operations':[{'command':a,'action':b} for a,b in sorted(plan.operations)],
                    'targets':sorted(plan.targets),'ttl_seconds':60}
                row={'plan_id':plan.plan_id,'approval_digest':plan.approval_digest,
                    'client_id':plan.approval_client,'task_id':plan.task_id,
                    'approval_connection_id':plan.connection_id,'previous_binding_digest':plan.approval_digest,
                    'expires_at':now+50,'manifest':manifest,'evidence':{'fixture':'not-real-Unity'}}
                if gate=='material':row.update(copied=False,history_digest='b'*64,records_digest='c'*64)
                rows.append(row)
            if rows:
                transfer={'version':1,'gate':gate,'handoff_id':handoff,'project_id':runtime.project_id,
                    'from_connection_id':next(iter(plans.values())).connection_id,'deadline':now+15,
                    'capabilities':['copy'] if gate=='material' else ['manage_material/get_material_info'],'plans':rows}
                result.append(json.dumps(transfer,ensure_ascii=False,separators=(',',':')))
        return {'kind':'arm','handoff_id':handoff,'window':20,'editor_now':now,'transfers':result}

    async def test_OC002_local_control_exact_cohort_rebind_is_single_use(self):
        import importlib.util,hashlib
        path=ROOT/'runtime/reload_control.py'
        self.assertTrue(path.is_file(),'OS-local runtime control dispatcher missing')
        from reload_control import ReloadControl
        async with self.prepared() as (runtime,client,editor,url,tokens):
            control=ReloadControl(runtime)
            request=self.transfers(runtime,'d'*32)
            reply=await control.dispatch(request)
            self.assertEqual(reply['kind'],'armed')
            self.assertTrue(runtime.reload_is_frozen())
            original={**runtime.plans,**runtime.material.plans}
            await editor[0].close(code=1000)
            await self.closed(runtime,editor[1])
            resumed=await control.dispatch({'kind':'reattach','handoff_id':'d'*32})
            self.assertEqual(resumed['transfers'],request['transfers'])
            async with self.editor(url,tokens['unity']) as (_,new,_):
                bindings=[hashlib.sha256(('{"transfer":'+raw+',"to_connection_id":'+json.dumps(new)+'}').encode()).hexdigest() for raw in request['transfers']]
                committed=await control.dispatch({'kind':'commit','handoff_id':'d'*32,'connection_id':new,'bindings':bindings})
                self.assertEqual(committed['kind'],'committed')
                for plans in (runtime.plans,runtime.material.plans):
                    for p in plans.values():
                        self.assertEqual(p.connection_id,new)
                        self.assertEqual(p.approval_digest,'a'*64)
                self.assertFalse(runtime.reload_is_frozen())
                with self.assertRaises(PermissionError):
                    await control.dispatch({'kind':'reattach','handoff_id':'d'*32})

    async def test_OC003_transfer_mutations_reject_without_changing_current_manifest(self):
        import copy
        from reload_control import ReloadControl
        async with self.prepared() as (runtime,client,editor,url,tokens):
            ticket=await runtime.freeze_for_reload(window=20)
            control=ReloadControl(runtime);control.handoff='d'*32
            source=self.transfers(runtime,'d'*32)
            baseline=copy.deepcopy(source)
            mutations=[
                lambda t:t.update(project_id='foreign'),
                lambda t:t.update(from_connection_id='foreign'),
                lambda t:t.update(handoff_id='e'*32),
                lambda t:t.update(deadline=float('nan')),
                lambda t:t['plans'][0].update(approval_digest='f'*64),
                lambda t:t['plans'][0].update(client_id='foreign'),
                lambda t:t['plans'][0].update(task_id='foreign'),
                lambda t:t['plans'][0].update(plan_id='foreign'),
                lambda t:t['plans'][0]['manifest'].update(targets=['Assets/Foreign.mat']),
                lambda t:t['plans'].append(copy.deepcopy(t['plans'][0])),
                lambda t:t.update(capabilities=[]),
                lambda t:t['plans'][0].update(expires_at=0),
                lambda t:t['plans'][0].update(evidence={})]
            for mutation in mutations:
                request=copy.deepcopy(source);first=json.loads(request['transfers'][0]);mutation(first)
                request['transfers'][0]=json.dumps(first,separators=(',',':'))
                with self.subTest(mutation=mutations.index(mutation)):
                    with self.assertRaises((ValueError,TypeError)):control.validate_transfers(request)
                    self.assertTrue(runtime.reload_is_frozen())
            for transfers in (source['transfers'][:1],source['transfers']*2,[] ):
                with self.assertRaises(ValueError):control.validate_transfers({**source,'transfers':transfers})
            self.assertEqual(source,baseline)
            self.assertTrue(await runtime.release_reload_barrier(ticket))

    async def test_OC004_control_abort_during_freeze_never_arms_late(self):
        from reload_control import ReloadControl
        async with self.prepared() as (runtime,client,editor,url,tokens):
            control=ReloadControl(runtime);request=self.transfers(runtime,'d'*32)
            original=runtime.connection;entered=asyncio.Event();proceed=asyncio.Event()
            async def delayed():
                entered.set();await proceed.wait();return await original()
            runtime.connection=delayed
            task=asyncio.create_task(control.dispatch(request))
            await entered.wait();control.abort();proceed.set()
            try:
                with self.assertRaises(PermissionError):await task
                self.assertFalse(runtime.plans)
                self.assertFalse(runtime.material.plans)
                self.assertIsNone(runtime._reload_barrier)
            finally:
                runtime.connection=original
                if not task.done():task.cancel()
                await asyncio.gather(task,return_exceptions=True)

    @asynccontextmanager
    async def os_control(self,runtime,*,reusable=False,expect_eof=False):
        import os,subprocess,time
        from launcher.peer_channel import PeerListener
        from launcher.peer_identity import PeerProcess
        from launcher.direct_python import current,environment_hint
        import reload_control
        self.assertTrue(callable(getattr(reload_control,'serve_channel',None)),'runtime OS channel adapter missing')
        source="""import json,sys,time
sys.path.insert(0,sys.argv[1])
from launcher.peer_identity import PeerProcess
from launcher.peer_channel import PeerChannel
with PeerProcess(int(sys.argv[3])) as peer:
 with PeerChannel.connect(sys.argv[2],peer,deadline=time.monotonic()+15) as channel:
  for line in sys.stdin.buffer:
   channel.send(line.strip())
   try:reply=channel.receive()
   except EOFError:
    if sys.argv[4]=="expected-eof":break
    raise
   sys.stdout.buffer.write(reply+b'\\n');sys.stdout.buffer.flush()
"""
        listener=PeerListener();process=None;peer=None;server=None;channel=None
        try:
            process=subprocess.Popen([current()['executable'],'-I','-B','-W','always::ResourceWarning','-c',
                source,str(ROOT),listener.address,str(os.getpid()),"expected-eof" if expect_eof else "reply-required"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,env={**os.environ,**environment_hint()})
            peer=PeerProcess(process.pid)
            channel=await asyncio.to_thread(listener.accept,peer,deadline=time.monotonic()+15)
            server=asyncio.create_task(reload_control.serve_channel(runtime,channel,reusable=reusable))
            async def exchange(doc):
                process.stdin.write(json.dumps(doc,separators=(',',':')).encode()+b'\n');process.stdin.flush()
                raw=await asyncio.wait_for(asyncio.to_thread(process.stdout.readline),5)
                if not raw and expect_eof:return None  # Observed EOF, not a server response.
                return json.loads(raw)
            yield exchange,process,server,channel
        finally:
            if process is not None:
                if process.stdin and not process.stdin.closed:process.stdin.close()
                try:await asyncio.wait_for(asyncio.to_thread(process.wait),5)
                except TimeoutError:process.kill();await asyncio.to_thread(process.wait)
                if server is not None:
                    try:await asyncio.wait_for(asyncio.shield(server),5)
                    except TimeoutError:server.cancel();await asyncio.gather(server,return_exceptions=True)
                    except asyncio.CancelledError:
                        if not server.cancelled():raise
                stderr=process.stderr.read().decode('utf-8','replace')
                process.stdout.close();process.stderr.close()
                self.assertEqual(process.returncode,0,stderr)
                self.assertNotIn('ResourceWarning',stderr)
            if channel is not None:channel.close()
            if peer is not None:peer.close()
            listener.close()

    async def test_OC005_os_peer_eof_revokes_both_frozen_cohorts(self):
        async with self.prepared() as (runtime,client,editor,url,tokens):
            async with self.os_control(runtime) as (exchange,process,server,channel):
                reply=await exchange(self.transfers(runtime,'d'*32))
                self.assertEqual(reply['kind'],'armed')
                self.assertTrue(runtime.reload_is_frozen())
                process.stdin.close()
                result=await asyncio.wait_for(asyncio.shield(server),5)
                self.assertFalse(result)
                self.assertFalse(runtime.plans)
                self.assertFalse(runtime.material.plans)
                self.assertIsNone(channel._handle)

    async def test_OC006_real_os_channel_commits_exact_binding_then_closes(self):
        import hashlib
        async with self.prepared() as (runtime,client,editor,url,tokens):
            async with self.os_control(runtime) as (exchange,process,server,channel):
                request=self.transfers(runtime,'d'*32)
                self.assertEqual((await exchange(request))['kind'],'armed')
                await editor[0].close(code=1000);await self.closed(runtime,editor[1])
                reply=await exchange({'kind':'reattach','handoff_id':'d'*32})
                self.assertEqual(reply['transfers'],request['transfers'])
                async with self.editor(url,tokens['unity']) as (_,new,events):
                    bindings=[hashlib.sha256(('{"transfer":'+s+',"to_connection_id":'+json.dumps(new)+'}').encode()).hexdigest() for s in request['transfers']]
                    self.assertEqual((await exchange({'kind':'commit','handoff_id':'d'*32,
                        'connection_id':new,'bindings':bindings}))['kind'],'committed')
                    self.assertTrue(await server)
                    result=await client.call_tool('material_execute',{'task_id':'material-task','plan_id':'material-plan','action':'copy','arguments':{}},raise_on_error=False)
                    self.assertFalse(result.is_error)
                    self.assertEqual(events[-1]['params']['connection_id'],new)

    async def test_OC007_local_channel_cancel_joins_worker_and_revokes(self):
        async with self.prepared() as (runtime,client,editor,url,tokens):
            async with self.os_control(runtime) as (exchange,process,server,channel):
                await exchange(self.transfers(runtime,'d'*32))
                await asyncio.sleep(.05) # Ensure idle I/O, not a task cancelled before start.
                server.cancel()
                with self.assertRaises(asyncio.CancelledError):await server
                self.assertIsNone(channel._handle)
                self.assertFalse(runtime.plans);self.assertFalse(runtime.material.plans)
                self.assertIsNone(runtime._reload_barrier)

    async def test_OC008_wrong_commit_binding_revokes_all_after_reattach(self):
        from reload_control import ReloadControl
        async with self.prepared() as (runtime,client,editor,url,tokens):
            control=ReloadControl(runtime)
            await control.dispatch(self.transfers(runtime,'d'*32))
            await editor[0].close(code=1000);await self.closed(runtime,editor[1])
            await control.dispatch({'kind':'reattach','handoff_id':'d'*32})
            async with self.editor(url,tokens['unity']) as (_,new,_):
                with self.assertRaises(PermissionError):
                    await control.dispatch({'kind':'commit','handoff_id':'d'*32,'connection_id':new,'bindings':['f'*64]})
                self.assertFalse(runtime.plans);self.assertFalse(runtime.material.plans)
                self.assertFalse(runtime.unity_ingress.active())
                self.assertFalse(control.transfers)

    async def test_OC009_idle_transfer_deadline_clears_private_bytes(self):
        from reload_control import ReloadControl
        async with self.prepared() as (runtime,client,editor,url,tokens):
            control=ReloadControl(runtime);request=self.transfers(runtime,'d'*32)
            for i,raw in enumerate(request['transfers']):
                transfer=json.loads(raw);transfer['deadline']=request['editor_now']+.1
                request['transfers'][i]=json.dumps(transfer,separators=(',',':'))
            await control.dispatch(request)
            async with asyncio.timeout(3):
                while control.transfers:await asyncio.sleep(.02)
            self.assertEqual(control.phase,'closed')
            self.assertFalse(runtime.plans);self.assertFalse(runtime.material.plans)

    async def test_OC010_duplicate_json_key_never_arms_over_os_channel(self):
        from reload_control import decode
        for raw in ('{"kind":"arm","kind":"commit"}', '{"nested":{"x":1,"x":2}}',
                    '{"clock":NaN}', '{"clock":Infinity}', '{} trailing'):
            with self.assertRaises(ValueError):decode(raw)

    async def test_OC011_one_held_os_channel_carries_distinct_reload_generations(self):
        import hashlib
        from contextlib import AsyncExitStack
        async with self.prepared() as (runtime,client,editor,url,tokens):
            original_read=next(iter(runtime.plans.values()))
            async with self.os_control(runtime,reusable=True) as (exchange,process,server,channel),AsyncExitStack() as stack:
                current=editor
                for handoff in ('d'*32,'e'*32):
                    request=self.transfers(runtime,handoff)
                    self.assertEqual((await exchange(request))['kind'],'armed')
                    await current[0].close(code=1000);await self.closed(runtime,current[1])
                    await exchange({'kind':'reattach','handoff_id':handoff})
                    current=await stack.enter_async_context(self.editor(url,tokens['unity']))
                    new=current[1]
                    bindings=[hashlib.sha256(('{"transfer":'+s+',"to_connection_id":'+json.dumps(new)+'}').encode()).hexdigest() for s in request['transfers']]
                    self.assertEqual((await exchange({'kind':'commit','handoff_id':handoff,
                        'connection_id':new,'bindings':bindings}))['kind'],'committed')
                    self.assertFalse(server.done())
                    self.assertEqual(next(iter(runtime.plans.values())).expires_at,original_read.expires_at)
                process.stdin.close()
                self.assertFalse(await server)
                # Owner control loss after commit must revoke the active generation too.
                self.assertFalse(runtime.plans);self.assertFalse(runtime.material.plans)

    async def test_OC012_owned_runtime_cli_binds_exact_owner_control_and_closes(self):
        import os,socket,threading,time
        from launcher.owned_run import create_owned_run,supervise_owned
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        raw={'project':'local-control-'+str(os.getpid()),'local_port':port,'parent_pid':os.getpid()}
        # The option is local API only; no public CLI/MCP activation.
        import inspect
        self.assertIn('enable_reload',inspect.signature(create_owned_run).parameters,'owned runtime control not wired')
        owned=create_owned_run(raw,enable_reload=True)
        stop=threading.Event();task=asyncio.create_task(asyncio.to_thread(supervise_owned,raw,owned=owned,stop=stop))
        try:
            async with asyncio.timeout(10):
                while not owned.transport_ready.is_set():
                    if task.done():self.fail('runtime exited before TLS ready: '+str(task.result()))
                    await asyncio.sleep(.02)
            control=owned.reload_control
            self.assertIsNotNone(control.peer)
            self.assertTrue(control.peer.alive())
            reply=await asyncio.to_thread(control.connect)
            self.assertEqual(reply,{'kind':'control_ready','version':1,'project_id':raw['project']})
            self.assertTrue(control.channel.peer.matches_channel(control.channel._handle,server=True))
        finally:
            stop.set()
            result=await asyncio.wait_for(asyncio.shield(task),12)
        self.assertTrue(result['process_cleanup_complete'],result)
        self.assertTrue(result['probe_session_cleanup_confirmed'],result)
        self.assertTrue(result['reload_control_cleanup_complete'],result)
        self.assertIsNone(owned.reload_control.peer)
        self.assertTrue(owned.reload_control.listener.closed)
        with socket.socket() as s:self.assertNotEqual(s.connect_ex(('127.0.0.1',port)),0)

    async def test_OC013_cancelled_native_worker_is_joined_before_return(self):
        import threading
        import reload_control
        self.assertTrue(callable(getattr(reload_control,'joined_worker',None)),'joined OS worker missing')
        stop=threading.Event();entered=threading.Event();exited=threading.Event()
        def worker():
            entered.set()
            try:stop.wait(3)
            finally:exited.set()
        task=asyncio.create_task(reload_control.joined_worker(stop,worker))
        async with asyncio.timeout(3):
            while not entered.is_set():await asyncio.sleep(.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(exited.is_set());self.assertTrue(stop.is_set())

    async def test_OC014_owned_tls_runtime_handoff_preserves_sdk_session(self):
        import os,socket,threading,ssl,hashlib,time
        import httpx,websockets
        from launcher.owned_run import create_owned_run,supervise_owned
        from launcher.reload_owner import OwnerReloadControl
        from fastmcp.client.transports import StreamableHttpTransport
        self.assertTrue(callable(getattr(OwnerReloadControl,'request',None)),'owner reload request path missing')
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        config={'project':'owned-handoff-'+str(os.getpid()),'local_port':port,'parent_pid':os.getpid()}
        owned=create_owned_run(config,clients=('codex',),enable_reload=True)
        stop=threading.Event();task=asyncio.create_task(asyncio.to_thread(supervise_owned,config,owned=owned,stop=stop))
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);tls.load_verify_locations(cadata=owned.owner.tls.certificate.decode())
        requests=[]
        async def record(response):requests.append((response.request.method,response.status_code,response.request.headers.get('mcp-session-id'),response.headers.get('mcp-session-id')))
        def http_factory(**kwargs):
            kwargs.update(verify=tls,trust_env=False,follow_redirects=False,event_hooks={'response':[record]})
            return httpx.AsyncClient(**kwargs)
        def connect(url,token):return websockets.connect(url,ssl=tls,proxy=None,additional_headers={'Authorization':'Bearer '+token})
        self.connect=connect
        async def register(ws):
            self.assertEqual(json.loads(await ws.recv())['type'],'welcome')
            await ws.send(json.dumps({'type':'register','project_hash':config['project'],
                'project_name':'fixture','unity_version':'fixture'}))
            reply=json.loads(await ws.recv());self.assertEqual(reply['type'],'registered')
            return reply['session_id']
        self.register=register
        url=f'wss://127.0.0.1:{port}/hub/plugin';token=owned.owner.identity.credentials['unity'].token
        transport=StreamableHttpTransport(f'https://127.0.0.1:{port}/mcp',
            headers={'Authorization':'Bearer '+owned.owner.identity.credentials['codex'].token},httpx_client_factory=http_factory)
        try:
            async with asyncio.timeout(10):
                while not owned.transport_ready.is_set():
                    if task.done():self.fail(str(task.result()))
                    await asyncio.sleep(.02)
            from contextlib import AsyncExitStack
            async with self.editor(url,token) as (ws,old,events),AsyncExitStack() as clients:
                client=await clients.enter_async_context(Client(transport))
                await client.call_tool('agent_prepare',fixtures.PREPARE)
                async with asyncio.timeout(5):
                    while not owned.binding.ready.is_set():await asyncio.sleep(.01)
                prepare=next(e['params'] for e in events if e['params']['kind']=='prepare')
                row={'plan_id':'read-plan','approval_digest':'a'*64,'client_id':prepare['client_id'],
                    'task_id':prepare['task_id'],'approval_connection_id':old,'previous_binding_digest':'a'*64,
                    'expires_at':60,'manifest':prepare['body'],'evidence':{'fixture':'not-real-Unity'}}
                t={'version':1,'gate':'read','handoff_id':'d'*32,'project_id':config['project'],
                    'from_connection_id':old,'deadline':25,'capabilities':['manage_material/get_material_info'],'plans':[row]}
                raw=json.dumps(t,separators=(',',':'))
                control=owned.reload_control
                reply=await asyncio.to_thread(control.request,{'kind':'arm','handoff_id':'d'*32,
                    'window':20,'editor_now':10,'transfers':[raw]})
                self.assertEqual(reply['kind'],'armed')
                self.assertFalse(owned.binding.ready.is_set(),'frozen is not healthy readiness')
                self.assertFalse(task.done(),'probe killed the approved handoff')
                await ws.close(code=1000)
                reply=await asyncio.to_thread(control.request,{'kind':'reattach','handoff_id':'d'*32})
                self.assertEqual(reply['transfers'],[raw])
                async with self.editor(url,token) as (_,new,next_events):
                    binding=hashlib.sha256(('{"transfer":'+raw+',"to_connection_id":'+json.dumps(new)+'}').encode()).hexdigest()
                    reply=await asyncio.to_thread(control.request,{'kind':'commit','handoff_id':'d'*32,'connection_id':new,'bindings':[binding]})
                    self.assertEqual(reply['kind'],'committed')
                    # Same client context/session, no recreated native client.
                    await client.call_tool('agent_stop',{'task_id':fixtures.PREPARE['task_id']})
                    self.assertTrue(any(e['params']['kind']=='stop' and e['params']['connection_id']==new for e in next_events))
                    await clients.aclose() # Confirm normal MCP DELETE BEFORE ending runtime.
                    sessions={row[3] for row in requests if row[0]=='POST' and row[3]}
                    self.assertEqual(len(sessions),1,'SDK session changed during reload')
                    deletes=[row for row in requests if row[0]=='DELETE']
                    self.assertEqual([(r[1],r[2]) for r in deletes],[(200,next(iter(sessions)))])
                    stop.set()
                    result=await asyncio.wait_for(asyncio.shield(task),12)
        finally:
            stop.set()
            result=await asyncio.wait_for(asyncio.shield(task),12)
            del self.connect
            del self.register
        self.assertTrue(result['process_cleanup_complete'],result)
        self.assertTrue(result['probe_session_cleanup_confirmed'],result)
        self.assertTrue(result['reload_control_cleanup_complete'],result)

    async def test_OC015_cli_rejects_forged_control_locator_before_listening(self):
        import os,socket
        from launcher.direct_python import current,environment_hint
        from launcher.candidate_launch import child_environment
        from owner_bootstrap import new_local_run
        from launcher.peer_channel import PeerListener
        with PeerListener() as listener,socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
            owner=new_local_run('bad-control-fixture',port)
            environment=owner.take_environment()
            baseline={'version':1,'address':listener.address,'parent_pid':os.getpid(),'expires_at':owner.identity.expires_at}
            docs=[{**baseline,'parent_pid':os.getpid()+1000000},{**baseline,'address':'tcp://127.0.0.1'},
                {**baseline,'expires_at':owner.identity.expires_at+1},{**baseline,'version':True},{**baseline,'unexpected':'value'}]
            for doc in docs:
                with self.subTest(field=list(k for k in doc if doc.get(k)!=baseline.get(k))):
                    env=child_environment({**environment,'VRCHAT_AGENT_RELOAD':json.dumps(doc)})
                    env.update(environment_hint())
                    process=await asyncio.create_subprocess_exec(current()['executable'],'-I','-B',str(ROOT/'runtime'),
                        '--project','bad-control-fixture','--port',str(port),env=env,
                        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    try:
                        out,err=await asyncio.wait_for(process.communicate(),5)
                        self.assertNotEqual(process.returncode,0)
                        self.assertIn(b'LOCAL_CONTROL_INVALID',err)
                        self.assertNotIn(b'Traceback',out+err)
                        self.assertNotIn(b'ResourceWarning',out+err)
                    finally:
                        if process.returncode is None:process.kill()
                        await process.communicate()

if __name__=='__main__':unittest.main(verbosity=2)
