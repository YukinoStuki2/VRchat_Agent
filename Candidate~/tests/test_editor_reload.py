"""Real owner CLI loop/runtime/SDK and compiled gate bytes; Editor lifecycle,
approval and relevant evidence remain fixtures. Test-only anonymous-pipe tap
hands an SDK role to this test, never to the production Editor bootstrap.
"""
import asyncio
from contextlib import asynccontextmanager,AsyncExitStack
import json
import os
from pathlib import Path
import ssl
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'runtime'),str(ROOT/'dependencies/mcp-1.29.1')]
import test_client_binding as compiled
import test_reload_wire as wires
from test_editor_owner import environment,EXECUTABLE
from launcher.peer_identity import PeerProcess
from launcher.peer_channel import PeerChannel
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import httpx
import websockets
WIRE_DLL=None
DOTNET=None
CHILD='''import sys,json,os
sys.path.insert(0,sys.argv[1])
from launcher import owned_run,editor_owner
original=owned_run.create_owned_run
held=[]
def create(*args,**kwargs):
 value=original(*args,**kwargs);held.append(value);return value
owned_run.create_owned_run=create
emit=editor_owner.emit
def tapped(row):
 if row.get('kind')=='unity_binding':
  row={**row,'fixture_sdk':held[0].owner.identity.credentials['hermes'].token,'fixture_certificate':held[0].owner.tls.certificate.decode('ascii')}
 emit(row)
editor_owner.emit=tapped
if sys.argv[2]=='delay-legacy-eof':
 read_control=editor_owner.read_control
 async def delayed_control(*args,**kwargs):
  value=await read_control(*args,**kwargs)
  if value==b'':
   import asyncio
   await asyncio.Future()  # Simulate an EOF callback delayed until final cancellation.
  return value
 editor_owner.read_control=delayed_control
sys.argv=['editor_owner.py','--project','fixture-project','--parent-pid',str(os.getppid()),'--client','hermes','--reload-control']
raise SystemExit(editor_owner.main())
'''

class EditorReloadTests(unittest.IsolatedAsyncioTestCase):
    core_peer=compiled.ClientBindingTests.core_peer
    register=wires.ReloadWireTests.register
    editor=wires.ReloadWireTests.editor
    def connect(self,url,token):
        return websockets.connect(url,ssl=self.tls,proxy=None,additional_headers={'Authorization':'Bearer '+token})

    @asynccontextmanager
    async def ready(self):
        self.use_core=True;compiled.WIRE_DLL=WIRE_DLL;compiled.DOTNET=DOTNET
        process=await asyncio.create_subprocess_exec(EXECUTABLE,'-I','-B','-c',CHILD,str(ROOT),
            'delay-legacy-eof' if getattr(self,'delay_legacy_eof',False) else 'normal',env=environment(),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        self.channels=[]
        try:
            process.stdin.write(b'start\n');await process.stdin.drain()
            bundle=json.loads(await asyncio.wait_for(process.stdout.readline(),10))
            self.assertEqual(bundle['owner_pid'],process.pid)
            self.tls=ssl.create_default_context(cadata=bundle['fixture_certificate'])
            with PeerProcess(process.pid) as owner:
                self.assertEqual(owner.identity[1],bundle['reload']['created'])
                async def channel(address,window=20):
                    ch=await asyncio.to_thread(PeerChannel.connect,address,owner,deadline=time.monotonic()+window)
                    self.channels.append(ch)
                    async def request(message):
                        def exchange():ch.send(json.dumps(message,ensure_ascii=False).encode());return json.loads(ch.receive())
                        return await asyncio.to_thread(exchange)
                    return ch,request
                ch,request=await channel(bundle['reload']['address'])
                self.assertEqual((await request({'kind':'hello','version':1,'project':'fixture-project'}))['kind'],'editor_control_ready')
                self.http=[]
                async def observed(response):self.http.append((response.request.method,response.status_code,response.request.headers.get('mcp-session-id')))
                def factory(**kwargs):
                    kwargs.update(verify=self.tls,trust_env=False,event_hooks={'response':[observed]})
                    return httpx.AsyncClient(**kwargs)
                url=bundle['endpoint'];transport=StreamableHttpTransport(url.replace('wss:','https:').removesuffix('/hub/plugin')+'/mcp',
                    headers={'Authorization':'Bearer '+bundle['fixture_sdk']},httpx_client_factory=factory)
                async with self.core_peer('bootstrap') as exchange,AsyncExitStack() as stack:
                    editor=await stack.enter_async_context(self.editor(url,bundle['unity_bearer'],exchange))
                    self.assertEqual(json.loads(await asyncio.wait_for(process.stdout.readline(),5)),{'kind':'ready'})
                    client=await stack.enter_async_context(Client(transport,timeout=3))
                    pa=(await client.call_tool('agent_prepare',{'task_id':'read-task','operations':[{'command':'manage_material','action':'get_material_info'}],
                        'targets':['Assets/source.mat'],'ttl_seconds':60})).data['data']
                    pm=(await client.call_tool('material_prepare',{'task_id':'material-task','source':'Assets/source.mat','candidate':'Assets/candidate.mat',
                        'operations':['copy','edit'],'references':[],'ttl_seconds':60})).data['data']
                    for route,plan in [('vrchat_agent_dispatch',pa),('vrchat_agent_material_dispatch',pm)]:
                        self.assertTrue((await exchange({'route':route,'fixture_approve_exact':plan}))['fixture_approved'])
                    self.assertTrue((await client.call_tool('material_execute',{'task_id':'material-task','plan_id':pm['plan_id'],'action':'copy','arguments':{}})).data['success'])
                    yield process,bundle,request,ch,channel,exchange,editor,client,stack,pa,pm
        finally:
            if process.returncode is None:
                if not process.stdin.is_closing():
                    process.stdin.write(b'stop\n');await process.stdin.drain();process.stdin.close()
                for ch in self.channels:ch.close()
                try:await asyncio.wait_for(process.communicate(),12)
                except TimeoutError:process.kill();await process.communicate();self.fail('owned relay required forced cleanup')
            for ch in self.channels:ch.close()

    async def test_ER001_expected_detach_keeps_original_sdk_and_finite_approval(self):
        async with self.ready() as (process,bundle,request,ch,channel,exchange,editor,client,stack,pa,pm):
            frozen=await exchange({'fixture_freeze_reload':{'handoff_id':'a'*32,'window':20}})
            self.assertTrue(frozen['fixture_frozen'])
            armed=await request({'kind':'arm','handoff_id':'a'*32,'window':20,'editor_now':frozen['editor_now'],'transfers':frozen['transfers']})
            self.assertEqual(armed['kind'],'armed')
            self.assertIn('next_address',armed,'surviving owner has no authenticated continuation listener')
            before=await exchange({'fixture_bytes':True})
            self.assertEqual((await request({'kind':'detach','handoff_id':'a'*32}))['kind'],'detached')
            await editor[0].close();ch.close();process.stdin.close()
            next_channel,resume=await channel(armed['next_address'])
            resumed=await resume({'kind':'resume','version':1,'project':'fixture-project','handoff_id':'a'*32})
            self.assertEqual(resumed['transfers'],frozen['transfers'])
            self.assertEqual(resumed['unity_binding']['endpoint'],bundle['endpoint'])
            self.assertEqual(resumed['unity_binding']['expires_at'],bundle['expires_at'])
            self.assertNotIn('fixture_sdk',resumed['unity_binding'])
            _,sid=await stack.enter_async_context(self.editor(bundle['endpoint'],resumed['unity_binding']['unity_bearer'],exchange))
            stage=await exchange({'fixture_stage_reload':{'transfers':resumed['transfers']}});self.assertTrue(stage['fixture_staged'])
            self.assertTrue((await exchange({'fixture_commit_reload':{'handoff_id':'a'*32,'bindings':stage['bindings']}}))['fixture_committed'])
            self.assertEqual((await resume({'kind':'commit','handoff_id':'a'*32,'connection_id':sid,'bindings':stage['bindings']}))['kind'],'committed')
            self.assertEqual(await exchange({'fixture_bytes':True}),before)
            self.assertTrue((await client.call_tool('manage_material',{'action':'get_material_info','material_path':'Assets/source.mat'})).data['success'])
            self.assertTrue((await client.call_tool('material_execute',{'task_id':'material-task','plan_id':pm['plan_id'],'action':'edit','arguments':{'property':'_Value','value':0.75}})).data['success'])
            await client.close()
            self.assertTrue(any(method=='DELETE' and code==200 for method,code,sid in self.http))
            sessions={sid for method,code,sid in self.http if sid};self.assertEqual(len(sessions),1)
            stopped=await resume({'kind':'stop'})
            self.assertTrue(stopped['process_cleanup_complete']);self.assertTrue(stopped['probe_session_cleanup_confirmed'])
            out,err=await asyncio.wait_for(process.communicate(),8)
            self.assertEqual(process.returncode,0,err.decode());self.assertEqual(out,b'')

    async def test_ER002_armed_without_explicit_detach_rejects_eof(self):
        async with self.ready() as (process,bundle,request,ch,channel,exchange,editor,client,stack,pa,pm):
            frozen=await exchange({'fixture_freeze_reload':{'handoff_id':'b'*32,'window':10}})
            armed=await request({'kind':'arm','handoff_id':'b'*32,'window':10,'editor_now':frozen['editor_now'],'transfers':frozen['transfers']})
            self.assertEqual(armed['kind'],'armed')
            ch.close() # Armed is NOT permission to ignore an unexpected disconnect.
            out,err=await asyncio.wait_for(process.communicate(),10)
            final=json.loads(out.decode().splitlines()[-1])
            self.assertEqual(final['code'],'EDITOR_CONTROL_CLOSED')
            self.assertEqual(final['phase'],'blocked');self.assertNotEqual(process.returncode,0)
            self.assertTrue(final['process_cleanup_complete']);self.assertTrue(final['editor_control_cleanup_complete'])
            self.assertNotIn(bundle['fixture_sdk'].encode(),out+err)
            # Failure shutdown is NOT relabelled as a normal client DELETE.

    async def test_ER003_explicit_legacy_stop_is_not_ignored_after_detach_ack(self):
        async with self.ready() as (process,bundle,request,ch,channel,exchange,editor,client,stack,pa,pm):
            frozen=await exchange({'fixture_freeze_reload':{'handoff_id':'c'*32,'window':10}})
            self.assertEqual((await request({'kind':'arm','handoff_id':'c'*32,'window':10,'editor_now':frozen['editor_now'],'transfers':frozen['transfers']}))['kind'],'armed')
            self.assertEqual((await request({'kind':'detach','handoff_id':'c'*32}))['kind'],'detached')
            process.stdin.write(b'stop\n');await process.stdin.drain();process.stdin.close()
            out,err=await asyncio.wait_for(process.communicate(),10)
            final=json.loads(out.decode().splitlines()[-1])
            self.assertEqual(final['phase'],'stopped');self.assertEqual(process.returncode,0,err.decode())
            self.assertTrue(final['process_cleanup_complete']);self.assertTrue(final['editor_control_cleanup_complete'])
            self.assertTrue(final['probe_session_cleanup_confirmed'])

    async def test_ER005_private_cancel_does_not_wait_for_legacy_eof_poll(self):
        self.delay_legacy_eof=True
        await self.test_ER004_detached_cancel_stops_without_reauthorizing_unity()

    async def test_ER004_detached_cancel_stops_without_reauthorizing_unity(self):
        async with self.ready() as (process,bundle,request,ch,channel,exchange,editor,client,stack,pa,pm):
            frozen=await exchange({'fixture_freeze_reload':{'handoff_id':'d'*32,'window':15}})
            armed=await request({'kind':'arm','handoff_id':'d'*32,'window':15,'editor_now':frozen['editor_now'],'transfers':frozen['transfers']})
            self.assertEqual((await request({'kind':'detach','handoff_id':'d'*32}))['kind'],'detached')
            ch.close();process.stdin.close()
            _,cancel=await channel(armed['next_address'])
            reply=await cancel({'kind':'cancel','version':1,'project':'fixture-project','handoff_id':'d'*32})
            self.assertEqual(reply['kind'],'stopped');self.assertEqual(reply['phase'],'stopped')
            self.assertNotIn('unity_binding',reply);self.assertNotIn('transfers',reply)
            self.assertTrue(reply['process_cleanup_complete']);self.assertTrue(reply['probe_session_cleanup_confirmed'])
            out,err=await asyncio.wait_for(process.communicate(),8)
            self.assertEqual(process.returncode,0,err.decode());self.assertEqual(out,b'')
