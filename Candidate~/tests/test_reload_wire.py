"""Actual C# gate bytes + SDK/WS + OS-local control; NOT real Unity/domain reload.
Fresh-build verifier must provide WIRE_DLL/DOTNET. Approval, evidence, gate
replacement and the Editor/owner coordination caller remain explicit fixtures.
"""
import asyncio
from contextlib import asynccontextmanager,AsyncExitStack
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'runtime'),str(ROOT/'dependencies/mcp-1.29.1')]
import test_client_binding as compiled
import test_reload_control as controls
from fastmcp import Client
import websockets

WIRE_DLL=None
DOTNET=None

class ReloadWireTests(unittest.IsolatedAsyncioTestCase):
    fixture=controls.ReloadControlTests.fixture
    connect=controls.ReloadControlTests.connect
    register=controls.ReloadControlTests.register
    closed=controls.ReloadControlTests.closed
    os_control=controls.ReloadControlTests.os_control
    core_peer=compiled.ClientBindingTests.core_peer

    @asynccontextmanager
    async def editor(self,url,token,exchange):
        async with self.connect(url,token) as ws:
            sid=await self.register(ws)
            self.assertTrue((await exchange({'fixture_connection':sid}))['fixture_ready'])
            async def respond():
                async for message in ws:
                    wire=json.loads(message)
                    if wire['type']=='ping':
                        await ws.send(json.dumps({'type':'pong','session_id':sid}));continue
                    result=await exchange({'request':wire['params'],'route':wire['name']})
                    await ws.send(json.dumps({'type':'command_result','id':wire['id'],'result':result}))
            task=asyncio.create_task(respond())
            try:yield ws,sid
            finally:
                await ws.close()
                try:await asyncio.wait_for(task,3)
                except websockets.exceptions.ConnectionClosed:pass

    @asynccontextmanager
    async def ready(self):
        self.use_core=True;compiled.WIRE_DLL=WIRE_DLL;compiled.DOTNET=DOTNET
        async with self.core_peer('bootstrap') as exchange:
            async with self.fixture() as (url,tokens,mcp):
                runtime=mcp._candidate_runtime
                async with self.editor(url,tokens['unity'],exchange) as editor, AsyncExitStack() as clients:
                    client=await clients.enter_async_context(Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']))
                    read={'task_id':'read-中文','operations':[{'command':'manage_material','action':'get_material_info'}],
                        'targets':['Assets/source.mat'],'ttl_seconds':60}
                    material={'task_id':'material-中文','source':'Assets/source.mat','candidate':'Assets/candidate.mat',
                        'operations':['copy','edit'],'references':[],'ttl_seconds':60}
                    pa=(await client.call_tool('agent_prepare',read)).data['data']
                    pm=(await client.call_tool('material_prepare',material)).data['data']
                    self.assertTrue((await exchange({'fixture_approve_exact':pa}))['fixture_approved'])
                    self.assertTrue((await exchange({'route':'vrchat_agent_material_dispatch','fixture_approve_exact':pm}))['fixture_approved'])
                    copy=await client.call_tool('material_execute',{'task_id':material['task_id'],'plan_id':pm['plan_id'],'action':'copy','arguments':{}})
                    self.assertTrue(copy.data['success'])
                    yield runtime,client,editor,url,tokens,exchange,read,material,pa,pm,clients

    async def test_RW001_compiled_cohorts_cross_os_control_and_keep_approval_lineage(self):
        async with self.ready() as (runtime,client,editor,url,tokens,exchange,read,material,pa,pm,clients):
            original={gate:{k:(p.plan_id,p.approval_digest,p.expires_at,p.approval_client) for k,p in plans.items()}
                for gate,plans in [('read',runtime.plans),('material',runtime.material.plans)]}
            before=await exchange({'fixture_bytes':True});self.assertEqual(before['writes'],1)
            handoff='d'*32
            frozen=await exchange({'fixture_freeze_reload':{'handoff_id':handoff,'window':15}})
            self.assertEqual(frozen.get('fixture_frozen'),True,'compiled transfer wire fixture missing')
            async with self.os_control(runtime) as (request,process,server,channel):
                arm={'kind':'arm','handoff_id':handoff,'window':20,'editor_now':frozen['editor_now'],'transfers':frozen['transfers']}
                self.assertEqual((await request(arm))['kind'],'armed')
                await editor[0].close(code=1000);await self.closed(runtime,editor[1])
                resumed=await request({'kind':'reattach','handoff_id':handoff})
                self.assertEqual(resumed['transfers'],frozen['transfers'])
                async with self.editor(url,tokens['unity'],exchange) as (_,new):
                    staged=await exchange({'fixture_stage_reload':{'transfers':resumed['transfers']}})
                    self.assertTrue(staged['fixture_staged'])
                    self.assertEqual(await exchange({'fixture_bytes':True}),before,'stage dispatched work')
                    committed=await exchange({'fixture_commit_reload':{'handoff_id':handoff,'bindings':staged['bindings']}})
                    self.assertTrue(committed['fixture_committed'])
                    reply=await request({'kind':'commit','handoff_id':handoff,'connection_id':new,'bindings':staged['bindings']})
                    self.assertEqual(reply['kind'],'committed');self.assertTrue(await server)
                    self.assertEqual(await exchange({'fixture_bytes':True}),before,'commit replayed work')
                    for gate,plans in [('read',runtime.plans),('material',runtime.material.plans)]:
                        for key,p in plans.items():
                            self.assertEqual((p.plan_id,p.approval_digest,p.expires_at,p.approval_client),original[gate][key])
                            self.assertEqual(p.connection_id,new)
                    result=await client.call_tool('manage_material',{'action':'get_material_info','material_path':'Assets/source.mat'})
                    self.assertTrue(result.data['success'])
                    result=await client.call_tool('material_execute',{'task_id':material['task_id'],'plan_id':pm['plan_id'],
                        'action':'edit','arguments':{'property':'_Value','value':0.625}})
                    self.assertTrue(result.data['success'])
                    self.assertEqual((await exchange({'fixture_bytes':True}))['writes'],2)
                    for route,p in [('vrchat_agent_dispatch',pa),('vrchat_agent_material_dispatch',pm)]:
                        rows=(await exchange({'route':route,'fixture_local_plans':True}))['fixture_plans']
                        self.assertEqual(rows[0]['digest'],p['digest'])
                        self.assertEqual(rows[0]['approval_connection_id'],editor[1])
                        self.assertEqual(rows[0]['connection_id'],new)
                    await clients.aclose()
                    async with asyncio.timeout(3):
                        while len(runtime.lifecycle_results)<2:await asyncio.sleep(.01)
                    self.assertTrue(all(r['unity_confirmed'] for r in list(runtime.lifecycle_results)[-2:]))
                    self.assertFalse(runtime.sessions)
                    for route in ['vrchat_agent_dispatch','vrchat_agent_material_dispatch']:
                        self.assertEqual((await exchange({'route':route,'fixture_local_plans':True}))['fixture_plans'],[])

    async def test_RW002_changed_material_evidence_aborts_runtime_cohort(self):
        async with self.ready() as (runtime,client,editor,url,tokens,exchange,read,material,pa,pm,clients):
            before=await exchange({'fixture_bytes':True});handoff='e'*32
            frozen=await exchange({'fixture_freeze_reload':{'handoff_id':handoff,'window':15}})
            self.assertTrue(frozen['fixture_frozen'])
            async with self.os_control(runtime) as (request,process,server,channel):
                self.assertEqual((await request({'kind':'arm','handoff_id':handoff,'window':20,
                    'editor_now':frozen['editor_now'],'transfers':frozen['transfers']}))['kind'],'armed')
                await editor[0].close(code=1000);await self.closed(runtime,editor[1])
                resumed=await request({'kind':'reattach','handoff_id':handoff})
                async with self.editor(url,tokens['unity'],exchange):
                    changed=await exchange({'fixture_evidence_change':True})
                    self.assertTrue(changed.get('fixture_changed'), 'missing relevant-evidence fixture')
                    staged=await exchange({'fixture_stage_reload':{'transfers':resumed['transfers']}})
                    self.assertFalse(staged['fixture_staged'])
                    for route in ['vrchat_agent_dispatch','vrchat_agent_material_dispatch']:
                        self.assertEqual((await exchange({'route':route,'fixture_local_plans':True}))['fixture_plans'],[])
                    self.assertEqual(await exchange({'fixture_bytes':True}),before,'rejection caused mutation')
                    # The owner withholds commit on either failed gate ACK.
                    process.stdin.close();self.assertFalse(await server)
                    self.assertFalse(runtime.plans);self.assertFalse(runtime.material.plans)
                    denied=await client.call_tool('material_execute',{'task_id':material['task_id'],'plan_id':pm['plan_id'],
                        'action':'edit','arguments':{'property':'_Value','value':0.75}},raise_on_error=False)
                    self.assertTrue(denied.is_error or denied.data.get('success') is False)
                    self.assertEqual(await exchange({'fixture_bytes':True}),before)
                    await clients.aclose()

    async def test_RW003_changed_transfer_bytes_fail_compiled_digest_and_runtime_commit(self):
        async with self.ready() as (runtime,client,editor,url,tokens,exchange,read,material,pa,pm,clients):
            before=await exchange({'fixture_bytes':True});handoff='f'*32
            frozen=await exchange({'fixture_freeze_reload':{'handoff_id':handoff,'window':15}})
            self.assertTrue(frozen['fixture_frozen'])
            async with self.os_control(runtime,expect_eof=True) as (request,process,server,channel):
                self.assertEqual((await request({'kind':'arm','handoff_id':handoff,'window':20,
                    'editor_now':frozen['editor_now'],'transfers':frozen['transfers']}))['kind'],'armed')
                await editor[0].close(code=1000);await self.closed(runtime,editor[1])
                resumed=await request({'kind':'reattach','handoff_id':handoff})
                async with self.editor(url,tokens['unity'],exchange) as (_,new):
                    altered=list(resumed['transfers']);body=json.loads(altered[0]);body['plans'][0]['task_id']='foreign-task'
                    altered[0]=json.dumps(body,ensure_ascii=False,separators=(',',':'))
                    staged=await exchange({'fixture_stage_reload':{'transfers':altered}})
                    self.assertFalse(staged['fixture_staged']);self.assertIsNone(staged['bindings'][0])
                    reply=await request({'kind':'commit','handoff_id':handoff,'connection_id':new,'bindings':staged['bindings']})
                    self.assertIsNone(reply);self.assertFalse(await server)
                    self.assertFalse(runtime.plans);self.assertFalse(runtime.material.plans)
                    self.assertEqual(await exchange({'fixture_bytes':True}),before)
                    for route in ['vrchat_agent_dispatch','vrchat_agent_material_dispatch']:
                        self.assertEqual((await exchange({'route':route,'fixture_local_plans':True}))['fixture_plans'],[])
                    await clients.aclose()

if __name__=='__main__':unittest.main(verbosity=2)
