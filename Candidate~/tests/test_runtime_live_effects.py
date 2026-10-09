"""Real SDK and candidate runtime; Unity peer is a declared test double."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_runtime as f
from test_runtime_job_effects import JobPeer
from fastmcp import Client
from transport.plugin_hub import PluginHub

CASES=[
 ('manage_asset','get_info','AssetReads/Assets/a.asset',{'action':'get_info','path':'Assets/a.asset','generate_preview':False},['asset_load_callbacks']),
 ('manage_asset','search','AssetReads/Assets/Scope',{'action':'search','path':'Assets/Scope','page_size':1,'page_number':1,'generate_preview':False},['asset_load_callbacks']),
 ('manage_prefabs','get_info','PrefabReads/Assets/a.prefab',{'action':'get_info','prefab_path':'Assets/a.prefab'},['asset_load_callbacks']),
 ('manage_prefabs','get_hierarchy','PrefabReads/Assets/a.prefab',{'action':'get_hierarchy','prefab_path':'Assets/a.prefab'},['asset_load_callbacks','prefab_contents_callbacks']),
 ('get_tests','discover','TestDiscovery/EditMode',{'mode':'EditMode'},['test_discovery_callbacks']),
]
class RuntimeLiveEffects(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.server=f.create_server();self.client=await self.enterAsyncContext(Client(self.server));self.peer=JobPeer()
  await PluginHub._registry.register(f.CONNECTION,'NOT-UNITY',f.PROJECT,'FIXTURE');PluginHub._connections[f.CONNECTION]=self.peer
 async def asyncTearDown(self):
  await self.client.__aexit__(None,None,None)
  self.assertFalse(self.server._candidate_runtime.sessions)
  self.assertFalse(PluginHub._pending)
  for sid in list(await PluginHub._registry.list_sessions()):
   PluginHub._connections.pop(sid,None);await PluginHub._registry.unregister(sid)
 def plan(self,case):
  name,action,target,args,effects=case
  return {'task_id':'effects-task','operations':[{'command':name,'action':action}], 'targets':[target],'ttl_seconds':60,'effects':[{'kind':e,'version':1} for e in effects]}
 def data(self,case):
  name,action,target,args,effects=case
  receipt={'kind':effects[-1],'version':1,'read_only':False,'all_mutations_observed':False,'callback_effects_path_bounded':False}
  if name=='manage_prefabs':receipt.update(load_started=action=='get_hierarchy',unload_started=action=='get_hierarchy',cleanup_confirmed=True)
  elif name=='get_tests':receipt['cleanup_confirmed']=True
  else:receipt.update(observed_at_utc='2026-10-08T15:00:00Z',pagination_consistency='live_not_snapshot')
  return {'candidate_effects':receipt,'tests':[['A','Suite.A','Suite/A','EditMode']]} if name=='get_tests' else {'candidate_effects':receipt,'fixture_only':True}
 async def ready(self,case):
  response=await self.client.call_tool('agent_prepare',self.plan(case),raise_on_error=False)
  self.assertFalse(response.is_error,str(response))
  self.peer.approved=True;self.peer.execute_data=self.data(case)
 async def test_LE001_all_five_live_effect_routes_and_explicit_manifests(self):
  tools={x.name:x for x in await self.client.list_tools()}
  for case in CASES:
   name,action,target,args,effects=case
   self.assertIn(name,tools)
   self.assertIs(tools[name].annotations.readOnlyHint,False)
   self.assertIs(tools[name].annotations.idempotentHint,False)
   await self.ready(case)
   self.assertEqual(self.peer.events[-1]['params']['body'],{k:v for k,v in self.plan(case).items() if k!='task_id'})
   result=await self.client.call_tool(name,args,raise_on_error=False)
   self.assertFalse(result.is_error,str(result));self.assertTrue(result.data['success'])
   self.assertEqual(result.data['data']['candidate_effects'],self.data(case)['candidate_effects'])
   wire={ {'generate_preview':'generatePreview','page_number':'pageNumber','page_size':'pageSize','prefab_path':'prefabPath'}.get(k,k):v for k,v in args.items()}
   self.assertEqual(self.peer.events[-1]['params']['body'],{'command':name,'params':wire})
 async def test_LE002_invalid_effects_and_mixed_scope_never_reach_unity(self):
  for case in CASES:
   for field in ('missing','bool','kind','mixed','target'):
    p=self.plan(case)
    if field=='missing':p.pop('effects')
    if field=='bool':p['effects'][0]['version']=True
    if field=='kind':p['effects'][0]['kind']='arbitrary_callbacks'
    if field=='mixed':p['operations'].append({'command':'manage_scene','action':'get_active'})
    if field=='target':p['targets'].append('Scenes')
    n=len(self.peer.events);r=await self.client.call_tool('agent_prepare',p,raise_on_error=False)
    self.assertTrue(r.is_error,(case,field));self.assertEqual(len(self.peer.events),n)
 async def test_LE003_unapproved_invalid_arguments_and_cross_session_denied(self):
  for case in CASES:
   name,action,target,args,effects=case
   r=await self.client.call_tool(name,args,raise_on_error=False);self.assertTrue(r.is_error)
   for invalid in (dict(args,unexpected=True),dict(args,action='delete') if name!='get_tests' else {'mode':'editmode'},dict(args,path='Assets/../secret') if name=='manage_asset' else dict(args,run=True)):
    await self.ready(case);n=sum(e['params']['kind']=='execute' for e in self.peer.events)
    r=await self.client.call_tool(name,invalid,raise_on_error=False);self.assertTrue(r.is_error)
    self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),n)
   await self.ready(case)
   async with Client(self.server) as other:self.assertTrue((await other.call_tool(name,args,raise_on_error=False)).is_error)
   await self.client.call_tool('agent_stop',{'task_id':'effects-task'})
 async def test_LE004_missing_or_forged_receipt_revokes_and_discloses(self):
  for case in CASES:
   for invalid in ('missing','pure','cleanup'):
    await self.ready(case)
    if invalid=='missing':self.peer.execute_data.pop('candidate_effects')
    elif invalid=='pure':self.peer.execute_data['candidate_effects']['read_only']=True
    else:self.peer.execute_data['candidate_effects']['cleanup_confirmed']=False
    r=await self.client.call_tool(case[0],case[3],raise_on_error=False);self.assertTrue(r.is_error)
    self.assertIn('effects_may_have_occurred=true',' '.join(c.text for c in r.content if hasattr(c,'text')))
    self.assertFalse(self.server._candidate_runtime.plans)
 async def test_LE005_no_refresh_preview_execute_or_retry_routes(self):
  for args in ({'action':'search','path':'Assets/Scope','generate_preview':False,'page_number':True,'page_size':1},
               {'action':'search','path':'Assets/Scope','generate_preview':False,'page_number':1,'page_size':51},
               {'action':'get_info','path':'Assets/a.asset','generate_preview':True},
               {'action':'get_info','path':'Assets/a.asset','generate_preview':'false'},
               {'action':'get_info','path':'Assets/CON.asset','generate_preview':False}):
   await self.ready(CASES[0]);n=len(self.peer.events)
   self.assertTrue((await self.client.call_tool('manage_asset',args,raise_on_error=False)).is_error)
   self.assertEqual(len(self.peer.events),n)
if __name__=='__main__':unittest.main()
