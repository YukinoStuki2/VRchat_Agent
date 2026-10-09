"""Real SDK/native Python job wrapper; Unity authority is an explicit peer double."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_runtime as f
from fastmcp import Client
from transport.plugin_hub import PluginHub
import importlib
native=importlib.import_module('services.tools.run_tests')
JOB='0123456789abcdef0123456789abcdef'
RECEIPT={'kind':'project_test_job_maintenance','version':1,'project_wide':True,'read_only':False,
 'persistence':'not_claimed','all_mutations_observed':False,'observed_at_utc':'2026-10-07T23:00:00+00:00'}
PREPARE={'task_id':'job-task','operations':[{'command':'get_test_job','action':'observe'}],
 'targets':['TestJobs/'+JOB],'ttl_seconds':60,'effects':[{'kind':'project_test_job_maintenance','version':1}]}
class JobPeer(f.UnityPeerFixture):
 execute_data: dict
 execute_response: dict | None
 async def send_json(self,payload):
  if payload['params'].get('kind')!='stop':return await super().send_json(payload)
  self.events.append(payload)
  from transport.models import CommandResultMessage
  await PluginHub._handle_command_result(object.__new__(PluginHub),CommandResultMessage(id=payload['id'],
   result={'status':'success','result':{'success':True,'data':{'status':'stopped'}}}))
class RuntimeJobEffects(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.server=f.create_server();self.client=await self.enterAsyncContext(Client(self.server));self.peer=JobPeer()
  await PluginHub._registry.register(f.CONNECTION,'NOT-UNITY',f.PROJECT,'FIXTURE');PluginHub._connections[f.CONNECTION]=self.peer
  self.peer.execute_data={'job_id':JOB,'status':'running','mode':'EditMode','last_update_unix_ms':1,'progress':{'editor_is_focused':False},'candidate_effects':dict(RECEIPT)}
 async def asyncTearDown(self):
  await self.client.__aexit__(None,None,None)
  self.assertEqual(self.server._candidate_runtime.sessions,{})
  self.assertTrue(all(r['unity_confirmed'] for r in self.server._candidate_runtime.lifecycle_results))
  self.assertFalse(native._background_tasks)
  self.assertEqual(PluginHub._pending,{})
  for sid in list(await PluginHub._registry.list_sessions()):
   PluginHub._connections.pop(sid,None);await PluginHub._registry.unregister(sid)
 async def ready(self):
  result=await self.client.call_tool('agent_prepare',PREPARE,raise_on_error=False)
  self.assertFalse(result.is_error,'explicit project maintenance manifest missing')
  self.peer.approved=True
 async def test_JE001_explicit_effect_manifest_real_wrapper_no_nudge(self):
  await self.ready()
  self.assertEqual(self.peer.events[-1]['params']['body'],{k:v for k,v in PREPARE.items() if k!='task_id'})
  with patch.object(native,'nudge_unity_focus',new=AsyncMock()) as nudge,patch.object(native,'_get_unity_project_path',new=AsyncMock()) as path:
   result=await self.client.call_tool('get_test_job',{'job_id':JOB})
   self.assertTrue(result.data['success'])
   self.assertEqual(result.data['data']['candidate_effects'],RECEIPT)
   self.assertFalse(result.data['data']['candidate_effects']['read_only'])
   self.assertTrue(result.data['data']['candidate_effects']['project_wide'])
   nudge.assert_not_called();path.assert_not_awaited();self.assertFalse(native._background_tasks)
  self.assertEqual(self.peer.events[-1]['params']['body'],{'command':'get_test_job','params':{'job_id':JOB}})
  tool=next(x for x in await self.client.list_tools() if x.name=='get_test_job')
  self.assertIs(tool.annotations.readOnlyHint,False);self.assertIs(tool.annotations.idempotentHint,False)
 async def test_JE005_missing_receipt_is_not_invented(self):
  await self.ready();self.peer.execute_data.pop('candidate_effects')
  result=await self.client.call_tool('get_test_job',{'job_id':JOB},raise_on_error=False)
  self.assertTrue(result.is_error)
  self.assertIn('effects_may_have_occurred=true',' '.join(x.text for x in result.content if hasattr(x,'text')))
  self.assertEqual(self.server._candidate_runtime.plans,{})
 async def test_JE006_invalid_or_lost_response_discloses_uncertainty(self):
  for mode in ('wrong_job','forged_receipt','transport'):
   await self.ready()
   self.peer.execute_data['job_id']=JOB
   self.peer.execute_data['candidate_effects']=dict(RECEIPT)
   if mode=='wrong_job':self.peer.execute_data['job_id']='a'*32
   if mode=='forged_receipt':self.peer.execute_data['candidate_effects']['read_only']=True
   if mode=='transport':
    with patch.object(native,'get_unity_instance_from_context',side_effect=RuntimeError('private-test-marker')):
     result=await self.client.call_tool('get_test_job',{'job_id':JOB},raise_on_error=False)
   else:result=await self.client.call_tool('get_test_job',{'job_id':JOB},raise_on_error=False)
   self.assertTrue(result.is_error,mode)
   text=' '.join(x.text for x in result.content if hasattr(x,'text'))
   self.assertIn('effects_may_have_occurred=true',text,mode)
   self.assertNotIn('private-test-marker',text)
   self.assertEqual(self.server._candidate_runtime.plans,{})
 async def test_JE002_missing_forged_or_mixed_effect_plan_rejected(self):
  import copy
  for kind in ('missing','empty','version','kind','mixed','uppercase'):
   p=copy.deepcopy(PREPARE)
   if kind=='missing':p.pop('effects')
   if kind=='empty':p['effects']=[]
   if kind=='version':p['effects'][0]['version']=True
   if kind=='kind':p['effects'][0]['kind']='asset_load_callbacks'
   if kind=='mixed':p['targets'].append('Scenes')
   if kind=='uppercase':p['targets'][0]='TestJobs/'+JOB.upper()
   n=len(self.peer.events);result=await self.client.call_tool('agent_prepare',p,raise_on_error=False)
   self.assertTrue(result.is_error,kind);self.assertEqual(len(self.peer.events),n)
 async def test_JE003_unapproved_other_job_wait_and_coercion_rejected(self):
  self.assertTrue((await self.client.call_tool('get_test_job',{'job_id':JOB},raise_on_error=False)).is_error)
  for args in ({'job_id':'a'*32},{'job_id':JOB,'wait_timeout':1},{'job_id':JOB,'include_details':'false'}, {'job_id':JOB.upper()}, {'jobId':JOB}):
   await self.ready();n=sum(e['params']['kind']=='execute' for e in self.peer.events)
   result=await self.client.call_tool('get_test_job',args,raise_on_error=False)
   self.assertTrue(result.is_error,str(args));self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),n)
 async def test_JE004_native_failure_stop_and_other_session_not_success(self):
  await self.ready()
  async with Client(self.server) as other:self.assertTrue((await other.call_tool('get_test_job',{'job_id':JOB},raise_on_error=False)).is_error)
  self.peer.execute_response={'success':False,'error':'job_persistence_unconfirmed','data':{'read_only':False,'effects_may_have_occurred':True}}
  result=await self.client.call_tool('get_test_job',{'job_id':JOB},raise_on_error=False)
  self.assertFalse(result.data['success'])
  self.assertEqual(result.data['data'],{'read_only':False,'effects_may_have_occurred':True})
  self.assertEqual(self.server._candidate_runtime.plans,{})
  self.peer.execute_response=None;await self.ready();await self.client.call_tool('agent_stop',{'task_id':'job-task'})
  self.assertTrue((await self.client.call_tool('get_test_job',{'job_id':JOB},raise_on_error=False)).is_error)
if __name__=='__main__':unittest.main()
