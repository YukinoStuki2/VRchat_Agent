"""Hermes adapter contracts: real native registry, deterministic peer doubles.
Run with the installed Hermes Python and source path; no agent/model/network.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
HERMES = Path(sys.argv.pop(1)).resolve(strict=True)
sys.path[:0] = [str(HERMES), str(ROOT / 'clients')]
from tools.registry import ToolRegistry
from mcp.types import CallToolResult, TextContent

class Peer:
    def __init__(self):
        self.session = Session()
        self.shutdown_count = 0
    async def shutdown(self):
        self.shutdown_count += 1
        self.session = None

class Session:
    def __init__(self):
        self.calls = []
    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=n, description=n,
            input_schema={'type':'object', 'properties':{}})
            for n in ('agent_status', 'agent_stop')], next_cursor=None)
    async def call_tool(self, name, args):
        self.calls.append((name, args))
        from mcp.types import CallToolResult, TextContent
        return CallToolResult(content=[TextContent(type='text',text='ok')], is_error=False)

class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue((ROOT/'clients/hermes_binding.py').is_file(), 'missing_session_bound_adapter')
        from hermes_binding import bind
        self.bind = bind
        self.registry = ToolRegistry()
        self.bindings = []
    async def asyncTearDown(self):
        for binding in self.bindings:
            await binding.close()
    async def make(self, peer=None, **kwargs):
        binding = await self.bind(peer or Peer(), self.registry,
            conversation_id='chat-a', include=('agent_status',), **kwargs)
        self.bindings.append(binding)
        return binding
    async def dispatch(self, binding, args=None, **context):
        name = binding.snapshot()[0]['function']['name']
        value = await asyncio.to_thread(self.registry.dispatch, name, args or {}, **context)
        return json.loads(value)
    async def test_HA001_exact_copy_snapshot_and_native_dispatch(self):
        peer = Peer(); session = peer.session
        binding = await self.make(peer)
        snap = binding.snapshot()
        self.assertEqual(len(snap), 1)
        name = snap[0]['function']['name']
        self.assertEqual(self.registry.get_all_tool_names(), [name])
        snap[0]['function']['parameters']['properties']['spoof'] = {}
        self.assertNotIn('spoof', binding.snapshot()[0]['function']['parameters']['properties'])
        value = await self.dispatch(binding, session_id='chat-a')
        self.assertFalse(value['mcp']['isError'])
        self.assertEqual(session.calls, [('agent_status', {})])
        await binding.close()
        self.assertEqual(self.registry.get_all_tool_names(), [])
        self.assertEqual(peer.shutdown_count, 1)

    async def test_HA002_runtime_conversation_only_and_stale_handler_denied(self):
        peer=Peer(); session=peer.session; binding=await self.make(peer)
        name=binding.snapshot()[0]['function']['name']
        entry=self.registry.get_entry(name)
        for context in ({},{'session_id':'chat-b'},{'task_id':'chat-a'}):
            result=await self.dispatch(binding, {'session_id':'chat-a'}, **context)
            self.assertEqual(result['error'], 'candidate_wrong_conversation')
        self.assertEqual(session.calls, [])
        await binding.close()
        result=json.loads(await asyncio.to_thread(entry.handler, {}, session_id='chat-a'))
        self.assertEqual(result['error'], 'candidate_binding_closed')
        self.assertEqual(session.calls, [])
        await binding.close(); self.assertEqual(peer.shutdown_count, 1)

    async def test_HA003_peer_session_replacement_never_rebinds(self):
        peer=Peer(); original=peer.session; binding=await self.make(peer)
        peer.session=Session()
        result=await self.dispatch(binding, session_id='chat-a')
        self.assertEqual(result.get('error'), 'candidate_session_changed')
        self.assertEqual(original.calls, [])
        self.assertEqual(peer.session.calls, [])

    async def test_HA004_close_cancels_inflight_and_waits_exact_peer(self):
        peer=Peer(); session=peer.session; started=asyncio.Event(); cancelled=asyncio.Event()
        async def blocked(name,args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        session.call_tool=blocked
        binding=await self.make(peer)
        pending=asyncio.create_task(self.dispatch(binding, session_id='chat-a'))
        try:
            await asyncio.wait_for(started.wait(),2)
            await asyncio.wait_for(binding.close(),2)
            self.assertTrue(cancelled.is_set(), 'inflight_request_not_cancelled')
            value=await asyncio.wait_for(pending,2)
            self.assertEqual(value.get('error'),'candidate_call_interrupted')
            self.assertTrue(value.get('outcome_unknown'))
            self.assertEqual(peer.shutdown_count,1)
        finally:
            pending.cancel()
            await asyncio.gather(pending,return_exceptions=True)

    async def test_HA005_transport_error_redacted_and_remote_error_preserved(self):
        peer=Peer(); session=peer.session; binding=await self.make(peer)
        async def error(name,args):
            raise RuntimeError('test-only-private-marker')
        session.call_tool=error
        with self.assertNoLogs('tools.registry',level='ERROR'):
            value=await self.dispatch(binding, session_id='chat-a')
        self.assertEqual(value.get('error'),'candidate_transport_failed')
        self.assertTrue(value.get('outcome_unknown'))
        self.assertNotIn('test-only-private-marker',json.dumps(value))
        peer2=Peer(); binding2=await self.make(peer2)
        async def remote_error(name,args):
            from mcp.types import CallToolResult, TextContent
            return CallToolResult(is_error=True,content=[TextContent(type='text',text='denied')])
        peer2.session.call_tool=remote_error
        value=await self.dispatch(binding2, session_id='chat-a')
        self.assertEqual(value.get('error'),'candidate_remote_error')
        self.assertTrue(value['mcp']['isError'])
        self.assertEqual(value['mcp']['content'][0]['text'],'denied')

    async def test_HA006_invalid_binding_catalog_and_partial_register_cleanup(self):
        for include in ((), ['agent_status'], ('agent_status','agent_status'), ('absent',)):
            peer=Peer()
            with self.assertRaises(ValueError):
                await self.bind(peer,self.registry,conversation_id='chat-a',include=include)
            self.assertEqual(peer.shutdown_count,1)
            self.assertEqual(self.registry.get_all_tool_names(),[])
        for conversation in ('',None,12,'x'*513):
            peer=Peer()
            with self.assertRaises(ValueError):
                await self.bind(peer,self.registry,conversation_id=conversation,include=('agent_status',))
            self.assertEqual(peer.shutdown_count,1)
        class FailingRegistry(ToolRegistry):
            def register(self, **kwargs):
                super().register(**kwargs)
                if len(self.get_all_tool_names())==2:
                    raise ValueError('test_registration_failed_after_write')
        registry=FailingRegistry(); peer=Peer()
        with self.assertRaises(ValueError):
            await self.bind(peer,registry,conversation_id='chat-a',include=('agent_status','agent_stop'))
        self.assertEqual(registry.get_all_tool_names(),[])
        self.assertEqual(peer.shutdown_count,1)

    async def test_HA007_cancel_resistant_reply_never_reports_success_after_close(self):
        peer=Peer(); started=asyncio.Event()
        original=peer.session.call_tool
        async def resistant(name,args):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return await original(name,args)
        peer.session.call_tool=resistant
        binding=await self.make(peer)
        pending=asyncio.create_task(self.dispatch(binding,session_id='chat-a'))
        await asyncio.wait_for(started.wait(),2)
        await binding.close()
        result=await pending
        self.assertEqual(result.get('error'),'candidate_call_interrupted')
        self.assertTrue(result.get('outcome_unknown'))

    async def test_HA008_late_close_preserves_other_registration_and_generation(self):
        first=await self.make(); old=first.snapshot()[0]['function']['name']
        old_entry=self.registry.get_entry(old)
        second=await self.make()
        self.assertNotEqual(first.snapshot(),second.snapshot())
        sentinel=lambda args,**kwargs:'{"sentinel":true}'
        self.registry.register(name=old,toolset=old_entry.toolset,
            schema=old_entry.schema,handler=sentinel,scope=self.registry.current_scope_key())
        newer=self.registry.get_entry(old)
        await first.close(); await first.close()
        self.assertIs(self.registry.get_entry(old),newer)
        value=await self.dispatch(second,session_id='chat-a')
        self.assertFalse(value['mcp']['isError'])
        self.registry.restore_registration(old,newer,None,scope=self.registry.current_scope_key())

    async def test_HA009_cancelled_close_waiter_does_not_cancel_shared_cleanup(self):
        peer=Peer(); entered=asyncio.Event(); release=asyncio.Event()
        async def shutdown():
            peer.shutdown_count+=1; entered.set(); await release.wait(); peer.session=None
        peer.shutdown=shutdown
        binding=await self.make(peer)
        closer=asyncio.create_task(binding.close())
        await entered.wait(); closer.cancel()
        with self.assertRaises(asyncio.CancelledError):await closer
        other=asyncio.create_task(binding.close())
        await asyncio.sleep(0)
        self.assertFalse(other.done())
        release.set(); await other
        self.assertEqual(peer.shutdown_count,1)
        self.assertEqual(self.registry.get_all_tool_names(),[])

    async def test_HA010_timeout_cancels_request_and_revokes_binding(self):
        import hermes_binding
        from unittest.mock import patch
        peer=Peer(); entered=asyncio.Event(); stopped=asyncio.Event()
        async def blocked(name,args):
            entered.set()
            try: await asyncio.Event().wait()
            finally: stopped.set()
        peer.session.call_tool=blocked; binding=await self.make(peer)
        with patch.object(hermes_binding,'CALL_TIMEOUT',0.05,create=True):
            result=await asyncio.wait_for(self.dispatch(binding,session_id='chat-a'),2)
        self.assertEqual(result.get('error'),'candidate_call_timeout')
        self.assertTrue(result.get('outcome_unknown'))
        await binding.close()
        self.assertTrue(stopped.is_set())
        self.assertEqual(peer.shutdown_count,1)
        self.assertEqual(self.registry.get_all_tool_names(),[])

    async def test_HA011_duplicate_peer_refused_without_stopping_owner(self):
        peer=Peer(); binding=await self.make(peer)
        with self.assertRaisesRegex(ValueError,'candidate_peer_already_bound'):
            await self.bind(peer,self.registry,conversation_id='chat-b',include=('agent_stop',))
        self.assertEqual(peer.shutdown_count,0)
        self.assertFalse((await self.dispatch(binding,session_id='chat-a'))['mcp']['isError'])

    async def test_HA012_loop_args_and_catalog_fail_closed(self):
        peer=Peer(); session=peer.session; binding=await self.make(peer)
        name=binding.snapshot()[0]['function']['name']
        local=json.loads(self.registry.dispatch(name,{},session_id='chat-a'))
        self.assertEqual(local.get('error'),'candidate_dispatch_loop_unavailable')
        for args in ([1], {'value':float('nan')}, {'value':object()}):
            value=json.loads(await asyncio.to_thread(self.registry.dispatch,name,args,session_id='chat-a'))
            self.assertEqual(value.get('error'),'candidate_arguments_invalid')
        self.assertEqual(session.calls,[])
        for kind in ('duplicate','paginated','changed','absent'):
            peer=Peer(); original=peer.session.list_tools
            async def catalog():
                result=await original()
                if kind=='duplicate':result.tools.append(result.tools[0])
                if kind=='paginated':result.next_cursor='not-complete'
                if kind=='changed':peer.session=Session()
                if kind=='absent':result.tools=[]
                return result
            peer.session.list_tools=catalog
            with self.assertRaisesRegex(ValueError,'candidate_catalog_invalid'):
                await self.bind(peer,self.registry,conversation_id='chat-a',include=('agent_status',))
            self.assertEqual(peer.shutdown_count,1)

    async def test_HA013_name_collision_preserves_existing_entry(self):
        import hermes_binding
        from unittest.mock import patch
        generation='a'*32; name='vrc_'+generation+'_0'
        sentinel=lambda args,**kwargs:'{"sentinel":true}'
        self.registry.register(name=name,toolset='other',schema={'name':name},handler=sentinel)
        entry=self.registry.get_entry(name);peer=Peer()
        with patch.object(hermes_binding.secrets,'token_hex',return_value=generation):
            with self.assertRaisesRegex(ValueError,'candidate_registration_collision'):
                await self.bind(peer,self.registry,conversation_id='chat-a',include=('agent_status',))
        self.assertIs(self.registry.get_entry(name),entry)
        self.assertEqual(peer.shutdown_count,1)
        self.registry.restore_registration(name,entry,None)

    async def test_HA014_native_slotted_peer_without_weakref(self):
        class SlottedPeer:
            __slots__=('session','shutdown_count')
            def __init__(self):self.session=Session();self.shutdown_count=0
            async def shutdown(self):self.session=None;self.shutdown_count+=1
        peer=SlottedPeer(); binding=await self.make(peer)
        self.assertFalse((await self.dispatch(binding,session_id='chat-a'))['mcp']['isError'])
        with self.assertRaisesRegex(ValueError,'candidate_peer_already_bound'):
            await self.bind(peer,self.registry,conversation_id='chat-b',include=('agent_status',))
        await binding.close();self.assertEqual(peer.shutdown_count,1)

    async def test_HA015_registry_cleanup_failure_still_stops_peer(self):
        peer=Peer();binding=await self.make(peer)
        original=self.registry.restore_registration
        def broken(*args,**kwargs):raise RuntimeError('test_cleanup_failure')
        self.registry.restore_registration=broken
        try:
            with self.assertRaisesRegex(RuntimeError,'test_cleanup_failure'):await binding.close()
            self.assertEqual(peer.shutdown_count,1)
        finally:
            self.registry.restore_registration=original
            for name,entry in binding._entries:original(name,entry,None,scope=binding._scope)
            self.bindings.remove(binding)  # Failed cleanup remains failed, not a green retry.

    async def test_HA016_native_dispatch_preserves_raw_json_types_and_schema(self):
        from tools.registry import registry
        from model_tools import handle_function_call
        from jsonschema import Draft202012Validator
        self.registry=registry
        peer=Peer();session=peer.session
        original={'type':'object','properties':{
            'flag':{'type':'boolean'},'count':{'type':'integer'},'fraction':{'type':'number'},
            'rows':{'type':'array','items':{'type':'object','properties':{'enabled':{'type':'boolean'}}}},
            'nested':{'type':'object','properties':{'rows':{'type':'array','items':{'type':'object'}}}},
            'optional':{'anyOf':[{'type':'integer'},{'type':'null'}]}},'additionalProperties':False}
        async def catalog():
            return SimpleNamespace(tools=[SimpleNamespace(name='agent_status',description='fixture raw types',input_schema=original)],next_cursor=None)
        session.list_tools=catalog
        binding=await self.make(peer);name=binding.snapshot()[0]['function']['name']
        samples=[{'flag':'false'},{'count':'1'},{'fraction':'1.25'},{'rows':'[]'},
            {'rows':'[{}]'},{'rows':['{}']},{'rows':{}},{'nested':'{}'},
            {'nested':{'rows':['{}']}},{'optional':'null'},{'optional':'1'},
            {'flag':False,'count':1,'fraction':1.25,'rows':[{'enabled':True}],'optional':None}]
        exported=binding.snapshot()[0]['function']['parameters']
        Draft202012Validator.check_schema(exported)
        for raw in samples:
            with self.subTest(raw=raw):
                self.assertEqual(Draft202012Validator(original).is_valid(raw),Draft202012Validator(exported).is_valid(raw),'schema meanings changed')
                before=json.loads(json.dumps(raw))
                response=await asyncio.to_thread(handle_function_call,name,json.loads(json.dumps(raw)),session_id='chat-a',enabled_tools=[name])
                self.assertIn('mcp',json.loads(response))
                self.assertEqual(session.calls[-1],('agent_status',before),'native host coerced raw arguments before candidate authority')

if __name__ == '__main__':
    unittest.main(verbosity=2)
