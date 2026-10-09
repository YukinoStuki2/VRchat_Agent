"""Real SDK HTTP/WS and signed fixture roles; local owner calls are fixtures.
Not OS-authenticated surviving owner, TLS, C# domain reload, or product approval.
"""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'dependencies/mcp-1.29.1')]
import test_runtime_unity_auth as auth_fixtures
from fastmcp import Client
import websockets
from transport.plugin_hub import PluginHub

PREPARE={'task_id':'handoff-task','operations':[{'command':'manage_material','action':'get_material_info'}],
         'targets':['Assets/Original.mat'],'ttl_seconds':60}

class RuntimeHandoffTests(unittest.IsolatedAsyncioTestCase):
    fixture=auth_fixtures.UnityAuthTests.fixture
    connect=auth_fixtures.UnityAuthTests.connect
    register=auth_fixtures.UnityAuthTests.register

    @asynccontextmanager
    async def editor(self,url,token):
        async with self.connect(url,token) as ws:
            sid=await self.register(ws)
            events=[]
            async def respond():
                async for message in ws:
                    wire=json.loads(message)
                    if wire['type']=='ping':
                        await ws.send(json.dumps({'type':'pong','session_id':sid}));continue
                    events.append(wire)
                    kind=wire['params']['kind']
                    data=({'status':'pending','plan_id':'material-plan' if wire['name']=='vrchat_agent_material_dispatch' else 'read-plan','digest':'a'*64} if kind=='prepare' else
                          {'status':'stopped'} if kind=='stop' else {'status':'fixture-ready','read_only':True})
                    await ws.send(json.dumps({'type':'command_result','id':wire['id'],
                        'result':{'success':True,'data':data}}))
            task=asyncio.create_task(respond())
            try:yield ws,sid,events
            finally:
                await ws.close()
                try: await asyncio.wait_for(task,3)
                except websockets.exceptions.ConnectionClosed: pass

    async def closed(self, runtime, old):
        async with asyncio.timeout(3):
            while old in await PluginHub._registry.list_sessions() or runtime.unity_ingress.live:
                await asyncio.sleep(.01)

    async def test_HF001_one_authenticated_reattach_keeps_frozen_until_local_commit(self):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            self.assertTrue(callable(getattr(runtime,'suspend_reload_handoff',None)),'authenticated reload handoff missing')
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                async with self.editor(url,tokens['unity']) as (ws,old,events):
                    await client.call_tool('agent_prepare',PREPARE)
                    original=dict(runtime.plans)
                    ticket=await runtime.freeze_for_reload(window=20)
                    self.assertTrue(runtime.suspend_reload_handoff(ticket))
                    self.assertFalse(runtime.unity_ingress.allow_reload_reattach(ticket),'admitted before old socket closed')
                await self.closed(runtime,old)
                self.assertEqual(runtime.plans,original)
                self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
                async with self.editor(url,tokens['unity']) as (new_ws,new,events):
                    self.assertNotEqual(old,new)
                    self.assertTrue(runtime.reload_is_frozen())
                    denied=await client.call_tool('agent_prepare',PREPARE,raise_on_error=False)
                    self.assertTrue(denied.is_error)
                    self.assertFalse(await runtime.commit_reload_handoff(object()))
                    self.assertTrue(await runtime.commit_reload_handoff(ticket))
                    self.assertFalse(await runtime.commit_reload_handoff(ticket))
                    for key,previous in original.items():
                        current=runtime.plans[key]
                        self.assertEqual(current.connection_id,new)
                        self.assertEqual(current.expires_at,previous.expires_at)
                        self.assertEqual(current.task_id,previous.task_id)
                        self.assertEqual(current.plan_id,previous.plan_id)
                        self.assertEqual(current.approval_client,previous.approval_client)
                        self.assertEqual(current.operations,previous.operations)
                        self.assertEqual(current.targets,previous.targets)
                    await client.call_tool('agent_stop',{'task_id':PREPARE['task_id']})
                    self.assertEqual(runtime.plans,{})
                with self.assertRaises(websockets.exceptions.InvalidStatus):
                    async with self.connect(url,tokens['unity']):self.fail('ordinary reconnect after handoff')

    async def test_HF002_material_execute_and_stop_use_new_binding_after_commit(self):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                async with self.editor(url,tokens['unity']) as (ws,old,events):
                    await client.call_tool('agent_prepare',PREPARE)
                    await client.call_tool('material_prepare',{'task_id':'material-task','source':'Assets/Original.mat',
                        'candidate':'Assets/Candidate.mat','operations':['copy'],'references':[],'ttl_seconds':60})
                    original=dict(runtime.material.plans)
                    ticket=await runtime.freeze_for_reload(window=20)
                    self.assertTrue(runtime.suspend_reload_handoff(ticket))
                await self.closed(runtime,old)
                self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
                async with self.editor(url,tokens['unity']) as (ws,new,events):
                    self.assertTrue(await runtime.commit_reload_handoff(ticket))
                    result=await client.call_tool('material_execute',{'task_id':'material-task','plan_id':'material-plan','action':'copy','arguments':{}},raise_on_error=False)
                    self.assertFalse(result.is_error,'rebinding lost material execution identity')
                    self.assertEqual(events[-1]['params']['connection_id'],new)
                    for client_id,previous in original.items():
                        current=runtime.material.plans[client_id]
                        self.assertEqual(current.expires_at,previous.expires_at)
                        self.assertEqual(current.manifest,previous.manifest)
                        self.assertIs(runtime.material.history[client_id][current.plan_id],current)
                    await client.call_tool('material_stop',{'task_id':'material-task','plan_id':'material-plan'})
                    await client.call_tool('agent_stop',{'task_id':PREPARE['task_id']})
                    self.assertFalse(runtime.material.plans)

    async def test_HF003_abnormal_close_never_preserves_armed_grants(self):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                async with self.editor(url,tokens['unity']) as (ws,old,events):
                    await client.call_tool('agent_prepare',PREPARE)
                    ticket=await runtime.freeze_for_reload(window=20)
                    self.assertTrue(runtime.suspend_reload_handoff(ticket))
                    await ws.close(code=1011)
                await self.closed(runtime,old)
                self.assertFalse(runtime.plans)
                self.assertIsNone(runtime._reload_barrier)
                self.assertFalse(runtime.unity_ingress.allow_reload_reattach(ticket))
                self.assertFalse(await runtime.commit_reload_handoff(ticket))
                with self.assertRaises(websockets.exceptions.InvalidStatus):
                    async with self.connect(url,tokens['unity']): self.fail('abnormal close reattached')

    @asynccontextmanager
    async def suspended(self, window=20):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                try:
                    async with self.editor(url,tokens['unity']) as (ws,old,events):
                        await client.call_tool('agent_prepare',PREPARE)
                        ticket=await runtime.freeze_for_reload(window=window)
                        self.assertTrue(runtime.suspend_reload_handoff(ticket))
                    await self.closed(runtime,old)
                    yield url,tokens,runtime,client,ticket
                finally:
                    runtime.cancel_reload_barrier()

    async def test_HF004_reattach_requires_local_permit_and_one_exact_role_socket(self):
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            self.assertFalse(runtime.unity_ingress.allow_reload_reattach(object()))
            with self.assertRaises(websockets.exceptions.InvalidStatus):
                async with self.connect(url,tokens['unity']): self.fail('no owner permit')
            self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
            self.assertFalse(runtime.unity_ingress.allow_reload_reattach(ticket))
            for bad in ('not-a-jwt',tokens['mcp'],tokens['wrong-project-principal']):
                with self.assertRaises(websockets.exceptions.InvalidStatus):
                    async with self.connect(url,bad): self.fail('foreign role consumed owner permit')
            async with self.editor(url,tokens['unity']) as (ws,new,events):
                with self.assertRaises(websockets.exceptions.InvalidStatus):
                    async with self.connect(url,tokens['unity']): self.fail('second concurrent socket')
                self.assertTrue(runtime.reload_is_frozen())
                self.assertTrue(await runtime.commit_reload_handoff(ticket))
                await client.call_tool('agent_stop',{'task_id':PREPARE['task_id']})

    async def test_HF005_sdk_session_close_cancels_suspended_grants(self):
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            await client.close()
            async with asyncio.timeout(3):
                while runtime.plans: await asyncio.sleep(.01)
            self.assertIsNone(runtime._reload_barrier)
            self.assertFalse(runtime.unity_ingress.allow_reload_reattach(ticket))
            self.assertFalse(await runtime.commit_reload_handoff(ticket))

    async def test_HF006_exact_stop_while_suspended_reports_local_revocation(self):
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            wrong=await client.call_tool('agent_stop',{'task_id':'wrong-task'},raise_on_error=False)
            self.assertTrue(wrong.is_error)
            self.assertTrue(runtime.reload_is_frozen())
            result=await client.call_tool('agent_stop',{'task_id':PREPARE['task_id']},raise_on_error=False)
            self.assertFalse(result.is_error,'local stop was reported as remote execution failure')
            self.assertEqual(result.data['data'],{'status':'locally_stopped','unity_confirmed':False})
            self.assertIsNone(runtime._reload_barrier)
            self.assertFalse(runtime.plans)
            self.assertFalse(runtime.unity_ingress.allow_reload_reattach(ticket))

    async def test_HF007_material_stop_while_suspended_revokes_both_cohorts(self):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                async with self.editor(url,tokens['unity']) as (ws,old,events):
                    await client.call_tool('agent_prepare',PREPARE)
                    pending=await client.call_tool('material_prepare',{'task_id':'material-task','source':'Assets/Original.mat',
                        'candidate':'Assets/Candidate.mat','operations':['copy'],'references':[],'ttl_seconds':60})
                    ticket=await runtime.freeze_for_reload(window=20)
                    self.assertTrue(runtime.suspend_reload_handoff(ticket))
                await self.closed(runtime,old)
                wrong=await client.call_tool('material_stop',{'task_id':'wrong','plan_id':'material-plan'},raise_on_error=False)
                self.assertTrue(wrong.is_error)
                self.assertTrue(runtime.reload_is_frozen())
                result=await client.call_tool('material_stop',{'task_id':'material-task','plan_id':'material-plan'},raise_on_error=False)
                self.assertFalse(result.is_error,'material stop after normal suspend failed')
                self.assertEqual(result.data['data'],{'status':'locally_stopped','unity_confirmed':False})
                self.assertFalse(runtime.plans)
                self.assertFalse(runtime.material.plans)
                self.assertFalse(runtime.unity_ingress.allow_reload_reattach(ticket))

    async def test_HF008_suspended_deadline_revokes_without_further_requests(self):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                async with self.editor(url,tokens['unity']) as (ws,old,events):
                    await client.call_tool('agent_prepare',PREPARE)
                    ticket=await runtime.freeze_for_reload(window=.2)
                    self.assertTrue(runtime.suspend_reload_handoff(ticket))
                await self.closed(runtime,old)
                await asyncio.sleep(.3)  # No polling method may perform the revocation for the implementation.
                self.assertIsNone(runtime._reload_barrier,'idle expired handoff retained authority')
                self.assertFalse(runtime.plans)
                self.assertFalse(runtime.unity_ingress.reload_pending())

    async def test_HF009_revoke_closes_reattached_idle_socket(self):
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
            async with self.connect(url,tokens['unity']) as ws:
                new=await self.register(ws)
                runtime.cancel_reload_barrier()
                try:
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):
                        await asyncio.wait_for(ws.recv(),1)
                except TimeoutError:
                    self.fail('revocation left reattached idle socket open')
                self.assertFalse(runtime.plans)
                self.assertFalse(await runtime.commit_reload_handoff(ticket))

    async def test_HF010_armed_original_idle_socket_expires_without_close(self):
        async with self.fixture() as (url,tokens,mcp):
            runtime=mcp._candidate_runtime
            async with Client(url.replace('ws:','http:').removesuffix('/hub/plugin')+'/mcp',auth=tokens['mcp']) as client:
                async with self.editor(url,tokens['unity']) as (ws,old,events):
                    await client.call_tool('agent_prepare',PREPARE)
                    ticket=await runtime.freeze_for_reload(window=.2)
                    self.assertTrue(runtime.suspend_reload_handoff(ticket))
                    await asyncio.wait_for(ws.wait_closed(),1)
                    self.assertFalse(runtime.plans)
                    self.assertIsNone(runtime._reload_barrier)
                    self.assertFalse(runtime.unity_ingress.allow_reload_reattach(ticket))

    async def test_HF011_unregistered_reattach_cannot_outlive_original_window(self):
        async with self.suspended(window=.3) as (url,tokens,runtime,client,ticket):
            ingress=runtime.unity_ingress
            self.assertTrue(ingress.allow_reload_reattach(ticket))
            async with self.connect(url,tokens['unity']) as ws:
                self.assertEqual(json.loads(await ws.recv())['type'],'welcome')
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    await asyncio.wait_for(ws.recv(),1)
                self.assertFalse(runtime.plans)
                self.assertFalse(await runtime.commit_reload_handoff(ticket))

    async def test_HF012_cancel_during_registry_await_cannot_commit(self):
        from unittest.mock import patch
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
            async with self.editor(url,tokens['unity']) as (ws,new,events):
                original=PluginHub._registry.list_sessions
                async def cancel_during_lookup():
                    rows=await original()
                    runtime.cancel_reload_barrier()
                    return rows
                with patch.object(PluginHub._registry,'list_sessions',cancel_during_lookup):
                    self.assertFalse(await runtime.commit_reload_handoff(ticket))
                self.assertFalse(runtime.plans)
                self.assertFalse(runtime.material.plans)
                self.assertIsNone(runtime._reload_barrier)

    async def test_HF013_changed_sdk_identity_cannot_commit(self):
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
            async with self.editor(url,tokens['unity']) as (ws,new,events):
                key=next(iter(runtime.plans))
                runtime.session_identities[key]='different-host-route'
                self.assertFalse(await runtime.commit_reload_handoff(ticket))
                self.assertFalse(runtime.plans)
                self.assertIsNone(runtime._reload_barrier)

    async def test_HF014_foreign_project_registration_consumes_attempt_without_grants(self):
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
            async with self.connect(url,tokens['unity']) as ws:
                self.assertEqual(json.loads(await ws.recv())['type'],'welcome')
                await ws.send(json.dumps({'type':'register','project_hash':'foreign-project'}))
                with self.assertRaises(websockets.exceptions.ConnectionClosed):
                    await asyncio.wait_for(ws.recv(),1)
                self.assertFalse(runtime.plans)
                self.assertFalse(await runtime.commit_reload_handoff(ticket))
            with self.assertRaises(websockets.exceptions.InvalidStatus):
                async with self.connect(url,tokens['unity']):self.fail('failed attempt retried')

    async def test_HF015_late_old_disconnect_cannot_revoke_committed_new_generation(self):
        async with self.suspended() as (url,tokens,runtime,client,ticket):
            old=runtime._reload_barrier['connection']
            self.assertTrue(runtime.unity_ingress.allow_reload_reattach(ticket))
            async with self.editor(url,tokens['unity']) as (ws,new,events):
                self.assertTrue(await runtime.commit_reload_handoff(ticket))
                original=dict(runtime.plans)
                runtime.connection_closed(old)
                self.assertEqual(runtime.plans,original)
                self.assertEqual(await runtime.connection(),new)
                self.assertIsNone(runtime.unity_ingress._reload_timer)
                await client.call_tool('agent_stop',{'task_id':PREPARE['task_id']})

if __name__=='__main__':unittest.main(verbosity=2)
