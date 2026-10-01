"""Host chat ownership with native registry and protocol/agent doubles. No LLM."""
import asyncio
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
HERMES=Path(sys.argv.pop(1)).resolve(strict=True)
sys.path[:0]=[str(HERMES),str(ROOT/'clients'),str(ROOT/'tests'),str(ROOT/'runtime')]
from tools.registry import registry
from model_tools import get_tool_definitions
from tls_context import issue_tls_material
from mcp import types
import time

class Peer:
    def __init__(self):self.session=self;self.closed=False
    async def list_tools(self):
        return types.ListToolsResult(tools=[types.Tool(name='agent_status',description='Unity',inputSchema={'type':'object'})])
    async def call_tool(self,name,arguments):
        return types.CallToolResult(content=[],structuredContent={'success':True,'data':{'read_only':True,'project_id':'fixture-project'}})
    async def shutdown(self):self.closed=True;self.session=None

class Agent:
    made=[]
    def __init__(self,**kw):
        self.session_id=kw['session_id'];self.enabled_toolsets=kw['enabled_toolsets']
        self.tools=get_tool_definitions(enabled_toolsets=self.enabled_toolsets,quiet_mode=True)
        self.valid_tool_names={t['function']['name'] for t in self.tools}
        self.closed=False;self.calls=[];self.interrupted=False;Agent.made.append(self)
    def run_conversation(self,**kw):
        self.calls.append(kw)
        return {'final_response':'fixture reply','messages':[{'role':'user','content':kw['user_message']},{'role':'assistant','content':'fixture reply'}]}
    def interrupt(self,*args):self.interrupted=True
    def close(self):self.closed=True

class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue((ROOT/'clients/hermes_chat.py').is_file(),'missing_chat_owner')
        self.module=importlib.import_module('hermes_chat')
        self.home=tempfile.TemporaryDirectory(prefix='vrc-chat-');self.addCleanup(self.home.cleanup)
        self.path=Path(self.home.name)/'receiver.sock';self.peers=[];self.writers=[];Agent.made=[]
        self.baseline=set(registry.get_all_tool_names())
        async def connect(**kwargs):
            p=Peer();self.peers.append(p);return p
        self.patches=[patch('hermes_connection.connect',connect),patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Agent)})]
        for p in self.patches:p.start()
        self.route=('fixture-platform','owner','chat-a',None,None)
        self.replies=[]
        async def reply(text):self.replies.append(text)
        self.reply=reply
    async def asyncTearDown(self):
        for w in self.writers:w.close();await w.wait_closed()
        for p in reversed(self.patches):p.stop()
        self.assertTrue(all(p.closed for p in self.peers))
        self.assertTrue(all(a.closed for a in Agent.made))
        self.assertFalse(self.path.exists())
        self.assertEqual(set(registry.get_all_tool_names()),self.baseline)
    async def offer(self,host):
        tls=issue_tls_material()
        doc={'version':1,'project':'fixture-project','role':'hermes','port':18443,'server_port':18443,
             'certificate':tls.certificate.decode(),'pin':tls.pin,'bearer':'fixture-memory-secret','expires_at':int(time.time())+60}
        r,w=await asyncio.open_unix_connection(str(self.path));self.writers.append(w)
        w.write(json.dumps(doc).encode()+b'\n');await w.drain()
        receipt=json.loads(await r.readline());return r,w,receipt['id']
    async def wait_for(self,predicate):
        async with asyncio.timeout(4):
            while not predicate():await asyncio.sleep(.01)
    async def test_HG001_explicit_claim_new_chat_and_stop(self):
        async with self.module.ChatHost(self.path,include=('agent_status',)) as host:
            r,w,key=await self.offer(host)
            self.assertEqual(Agent.made,[],'offer must not start conversation')
            await host.command(self.route,'绑定 '+key,options={'model':'fixture'},reply=self.reply)
            await self.wait_for(lambda:len(Agent.made)==1 and bool(self.replies))
            a=Agent.made[0];self.assertTrue(a.session_id.startswith('vrc-'))
            await host.command(self.route,'问 status',options={},reply=self.reply)
            self.assertEqual(self.replies[-1],'fixture reply')
            self.assertEqual(a.calls[0]['user_message'],'status')
            await host.command(self.route,'停止',options={},reply=self.reply)
            self.assertTrue(a.closed);self.assertTrue(self.peers[0].closed)
            self.assertEqual(json.loads(await r.readline()),{'kind':'closed','clean':True})
            self.assertEqual(host.receiver.offers(),[])

    async def test_HG002_source_loss_and_two_chats_do_not_cross_bind(self):
        async with self.module.ChatHost(self.path,include=('agent_status',)) as host:
            r,w,key=await self.offer(host)
            second=('fixture-platform','owner','chat-b',None,None)
            r2,w2,key2=await self.offer(host)
            await host.command(self.route,'绑定 '+key,options={},reply=self.reply)
            await host.command(second,'绑定 '+key2,options={},reply=self.reply)
            a,b=Agent.made
            self.assertNotEqual(a.session_id,b.session_id)
            await host.command(self.route,'绑定 '+key2,options={},reply=self.reply)
            self.assertEqual(len(Agent.made),2)
            w.write(b'stop\n');await w.drain();await r.readline()
            await self.wait_for(lambda:a.closed)
            self.assertFalse(b.closed)
            self.assertNotIn(self.route,host.chats)
            await host.command(second,'停止',options={},reply=self.reply)
            await r2.readline()

    async def test_HG003_constructor_failure_withdraws_the_delivery(self):
        class Broken(Agent):
            def __init__(self,**kw):
                super().__init__(**kw);raise RuntimeError('private-constructor-marker')
        async with self.module.ChatHost(self.path,include=('agent_status',)) as host:
            r,w,key=await self.offer(host)
            with patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Broken)}):
                await host.command(self.route,'绑定 '+key,options={},reply=self.reply)
            self.assertEqual(host.receiver.offers(),[],'failed_agent_left_source_live')
            self.assertNotIn('private-constructor-marker',''.join(self.replies))
            self.assertTrue(Agent.made[0].closed)

    async def test_HG004_foreign_claim_failure_preserves_original_chat(self):
        async with self.module.ChatHost(self.path,include=('agent_status',)) as host:
            r,w,key=await self.offer(host)
            await host.command(self.route,'绑定 '+key,options={},reply=self.reply)
            other=('fixture-platform','owner','chat-b',None,None)
            await host.command(other,'绑定 '+key,options={},reply=self.reply)
            self.assertFalse(Agent.made[0].closed)
            self.assertFalse(self.peers[0].closed)
            self.assertIn(self.route,host.chats)
            self.assertNotIn(other,host.chats)

    async def test_HG005_stop_revokes_before_waiting_for_inflight_model(self):
        import threading
        entered=threading.Event();release=threading.Event()
        class Slow(Agent):
            def run_conversation(self,**kw):
                entered.set();release.wait(4);return super().run_conversation(**kw)
        with patch.dict(sys.modules,{'run_agent':SimpleNamespace(AIAgent=Slow)}):
            async with self.module.ChatHost(self.path,include=('agent_status',)) as host:
                r,w,key=await self.offer(host)
                await host.command(self.route,'绑定 '+key,options={},reply=self.reply)
                ask=asyncio.create_task(host.command(self.route,'问 slow',options={},reply=self.reply))
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                await host.command(self.route,'问 concurrent',options={},reply=self.reply)
                self.assertIn('不会并发',''.join(self.replies))
                stop=asyncio.create_task(host.command(self.route,'停止',options={},reply=self.reply))
                await self.wait_for(lambda:Agent.made[0].interrupted)
                try:
                    self.assertTrue(self.peers[0].closed,'MCP must revoke before model joins')
                    stop.cancel();stop.cancel();await asyncio.sleep(.02)
                    self.assertFalse(stop.done())
                    self.assertFalse(Agent.made[0].closed)
                finally:release.set()
                with self.assertRaises(asyncio.CancelledError):await stop
                await ask
                self.assertTrue(Agent.made[0].closed)
                self.assertNotIn('fixture reply',self.replies,'late model result must be suppressed')

if __name__=='__main__':unittest.main(verbosity=2)
