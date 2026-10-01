"""Construction ownership contracts; no model calls, deterministic AIAgent double."""
import asyncio
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
HERMES=Path(sys.argv.pop(1)).resolve(strict=True)
sys.path[:0]=[str(HERMES),str(ROOT/'clients'),str(ROOT/'tests')]
from tools.registry import registry
from model_tools import get_tool_definitions
class Peer:
    def __init__(self):self.session=Session();self.stopped=0
    async def shutdown(self):self.stopped+=1;self.session=None
class Session:
    async def list_tools(self):return SimpleNamespace(tools=[SimpleNamespace(name='agent_status',description='status',input_schema={'type':'object','properties':{}})],next_cursor=None)
class Agent:
    made=[]
    def __init__(self,**kw):
        from model_tools import get_tool_definitions
        self.session_id=kw['session_id'];self.enabled_toolsets=kw['enabled_toolsets']
        self.tools=get_tool_definitions(enabled_toolsets=self.enabled_toolsets,quiet_mode=True)
        self.valid_tool_names={t['function']['name'] for t in self.tools}
        self.closed=0;self.options=kw;self.made.append(self)
    def close(self):self.closed+=1
class ConstructionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue((ROOT/'clients/hermes_conversation.py').is_file(),'missing_native_conversation_builder')
        from hermes_conversation import conversation
        self.conversation=conversation;Agent.made=[]
        self.stub=patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Agent)});self.stub.start()
        self.baseline=set(registry.get_all_tool_names())
    async def asyncTearDown(self):
        self.stub.stop();self.assertEqual(set(registry.get_all_tool_names()),self.baseline)
    async def test_HC001_native_toolset_constructor_and_owned_close(self):
        peer=Peer()
        async with self.conversation(peer,include=('agent_status',),options={'model':'fixture-only'}) as agent:
            self.assertTrue(agent.session_id.startswith('vrc-'))
            self.assertEqual(agent.tools,get_tool_definitions(enabled_toolsets=agent.enabled_toolsets,quiet_mode=True))
            raw=get_tool_definitions(enabled_toolsets=agent.enabled_toolsets,quiet_mode=True,skip_tool_search_assembly=True)
            self.assertEqual(len(raw),1)
            self.assertTrue(raw[0]['function']['name'].startswith('vrc_'))
            self.assertEqual(agent.valid_tool_names,{t['function']['name'] for t in agent.tools})
            self.assertEqual(peer.stopped,0)
        self.assertEqual(peer.stopped,1);self.assertEqual(agent.closed,1)

    async def test_HC002_changed_snapshot_or_identity_refused_and_closed(self):
        for kind in ('identity','schema','names','toolsets'):
            class Changed(Agent):
                def __init__(self,**kw):
                    super().__init__(**kw)
                    if kind=='identity':self.session_id='wrong'
                    if kind=='schema':self.tools=self.tools+[{'type':'function','function':{'name':'extra'}}]
                    if kind=='names':self.valid_tool_names.add('extra')
                    if kind=='toolsets':self.enabled_toolsets=['all']
            peer=Peer()
            with patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Changed)}):
                with self.assertRaisesRegex(RuntimeError,'candidate_construction_mismatch'):
                    async with self.conversation(peer,include=('agent_status',),options={}):self.fail('unsafe_agent_yielded')
            self.assertEqual(peer.stopped,1);self.assertEqual(Agent.made[-1].closed,1)

    async def test_HC003_partial_constructor_is_closed_without_exception_text(self):
        class Broken(Agent):
            def __init__(self,**kw):
                super().__init__(**kw)
                raise ValueError('test-private-constructor-marker')
        peer=Peer()
        with patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Broken)}):
            with self.assertRaisesRegex(RuntimeError,'candidate_construction_failed') as caught:
                async with self.conversation(peer,include=('agent_status',),options={}):self.fail('yielded')
        self.assertNotIn('test-private-constructor-marker',str(caught.exception))
        self.assertEqual(Agent.made[-1].closed,1);self.assertEqual(peer.stopped,1)

    async def test_HC004_cancelled_constructor_waits_and_closes_late_agent(self):
        import threading
        entered=threading.Event();release=threading.Event()
        class Slow(Agent):
            def __init__(self,**kw):
                entered.set();release.wait(3);super().__init__(**kw)
        peer=Peer()
        async def enter():
            async with self.conversation(peer,include=('agent_status',),options={}):self.fail('cancelled_yield')
        with patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Slow)}):
            task=asyncio.create_task(enter())
            self.assertTrue(await asyncio.to_thread(entered.wait,2))
            task.cancel();await asyncio.sleep(.03)
            try:self.assertFalse(task.done(),'constructor_abandoned')
            finally:release.set()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(Agent.made[-1].closed,1);self.assertEqual(peer.stopped,1)

    async def test_HC005_cached_native_schemas_are_detached_before_first_turn(self):
        async with self.conversation(Peer(),include=('agent_status',),options={}) as agent:
            cached=get_tool_definitions(enabled_toolsets=agent.enabled_toolsets,quiet_mode=True)
            original=cached[0]['function']['description']
            try:
                agent.tools[0]['function']['description']='local-only-snapshot'
                self.assertEqual(cached[0]['function']['description'],original,'shared_native_cache_mutated')
            finally:cached[0]['function']['description']=original

    async def test_HC006_early_failure_cleanup_has_owned_identity(self):
        identities=[]
        class Early:
            def __init__(self,**kw):raise ValueError('early')
            def close(self):identities.append(getattr(self,'session_id',None))
        with patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Early)}):
            with self.assertRaisesRegex(RuntimeError,'candidate_construction_failed'):
                async with self.conversation(Peer(),include=('agent_status',),options={}):self.fail('yielded')
        self.assertEqual(len(identities),1)
        self.assertIsInstance(identities[0],str);self.assertTrue(identities[0].startswith('vrc-'))

    async def test_HC007_host_options_cannot_replace_ownership_or_history(self):
        for key in ('session_id','enabled_toolsets','disabled_toolsets','prefill_messages'):
            peer=Peer();count=len(Agent.made)
            with self.assertRaisesRegex(ValueError,'candidate_construction_options'):
                async with self.conversation(peer,include=('agent_status',),options={key:'foreign'}):self.fail('yielded')
            self.assertEqual(peer.stopped,1);self.assertEqual(len(Agent.made),count)

    async def test_HC008_two_live_conversations_keep_disjoint_ids_and_snapshots(self):
        first=Peer();second=Peer()
        async with self.conversation(first,include=('agent_status',),options={}) as a:
            snapshot=json.dumps(a.tools,sort_keys=True)
            async with self.conversation(second,include=('agent_status',),options={}) as b:
                self.assertNotEqual(a.session_id,b.session_id)
                self.assertNotEqual(a.enabled_toolsets,b.enabled_toolsets)
            self.assertEqual(second.stopped,1);self.assertEqual(first.stopped,0)
            self.assertEqual(json.dumps(a.tools,sort_keys=True),snapshot)

    async def test_HC009_repeated_cancellation_waits_for_owned_cleanup(self):
        entered=asyncio.Event();release=asyncio.Event();inside=asyncio.Event()
        peer=Peer()
        async def stop():entered.set();await release.wait();peer.stopped+=1;peer.session=None
        peer.shutdown=stop
        async def use():
            async with self.conversation(peer,include=('agent_status',),options={}):
                inside.set();await asyncio.Event().wait()
        task=asyncio.create_task(use());await inside.wait();task.cancel()
        await entered.wait();task.cancel();await asyncio.sleep(.03)
        try:self.assertFalse(task.done(),'cleanup_abandoned_by_second_cancel')
        finally:release.set()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(peer.stopped,1);self.assertEqual(Agent.made[-1].closed,1)

    async def test_HC010_mismatched_constructor_never_cleans_foreign_session(self):
        seen=[]
        for fail in (False,True):
            class Changed(Agent):
                def __init__(self,**kw):
                    super().__init__(**kw);self.session_id='foreign-session'
                    if fail:raise ValueError('fixture-constructor-failure')
                def close(self):seen.append(self.session_id);super().close()
            with patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Changed)}):
                with self.assertRaises(RuntimeError):
                    async with self.conversation(Peer(),include=('agent_status',),options={}):self.fail('yielded')
        self.assertEqual(len(seen),2)
        self.assertTrue(all(i.startswith('vrc-') for i in seen),'foreign_cleanup_identity')

    async def test_HC011_peer_cleanup_failure_still_closes_agent_and_is_not_success(self):
        peer=Peer()
        async def stop():peer.stopped+=1;peer.session=None;raise RuntimeError('fixture-close-failed')
        peer.shutdown=stop
        with self.assertRaisesRegex(RuntimeError,'fixture-close-failed'):
            async with self.conversation(peer,include=('agent_status',),options={}) as agent:pass
        self.assertEqual(peer.stopped,1);self.assertEqual(agent.closed,1)

    async def test_HC012_claimed_binding_constructed_once_without_rebinding(self):
        import hermes_conversation as module
        from hermes_binding import bind
        self.assertTrue(hasattr(module,'bound_conversation'),'missing_claimed_binding_constructor')
        peer=Peer()
        binding=await bind(peer,registry,conversation_id='trusted-chat-generation',include=('agent_status',))
        async with module.bound_conversation(binding,options={}) as agent:
            self.assertEqual(agent.session_id,'trusted-chat-generation')
            snapshot=binding.snapshot()
            with self.assertRaisesRegex(ValueError,'candidate_construction_used'):
                async with module.bound_conversation(binding,options={}):self.fail('reused')
            self.assertEqual(binding.snapshot(),snapshot)
            self.assertEqual(peer.stopped,0)
        self.assertEqual(peer.stopped,1)
        self.assertEqual(agent.closed,1)

if __name__=='__main__':unittest.main(verbosity=2)
