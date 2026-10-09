"""Candidate plugin policy with real Hermes hook manager; gateway adapter double."""
import asyncio
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
HERMES=Path(sys.argv.pop(1)).resolve(strict=True)
sys.path[:0]=[str(HERMES),str(ROOT/'clients')]
from gateway.session import SessionSource
from gateway.platforms.base import MessageEvent
from gateway.config import Platform
from hermes_cli.plugins import PluginManager,PluginContext,PluginManifest

class Context:
    def __init__(self,settings):self.settings=settings;self.hooks={};self.tasks=[];self.unload=[]
    def get_config(self,key,default=None):return self.settings.get(key,default)
    def register_hook(self,key,fn):self.hooks[key]=fn
    def on_unload(self,fn):self.unload.append(fn)
    def spawn_task(self,coro,**kw):
        task=asyncio.create_task(coro);self.tasks.append(task);return task

class Gateway:
    def __init__(self):self.authorized=True;self.sent=[];self.resolutions=0
    def _is_user_authorized_for_source(self,source):return self.authorized
    def _adapter_for_source(self,source):return self
    def _thread_metadata_for_source(self,source,message_id):return {}
    async def send(self,chat_id,content,**kw):self.sent.append((chat_id,content));return SimpleNamespace(success=True)
    def _resolve_session_agent_runtime(self,**kwargs):
        self.resolutions+=1;return 'fixture',{'api_key':'fixture','provider':'fixture'}

class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue((ROOT/'clients/hermes_gateway.py').is_file(),'missing_gateway_plugin')
        self.module=importlib.import_module('hermes_gateway')
        self.home=tempfile.TemporaryDirectory(prefix='vrc-plugin-');self.addCleanup(self.home.cleanup)
        self.path=Path(self.home.name)/'receiver.sock'
        self.ctx=Context({'socket':str(self.path),'owners':[{'platform':'telegram','user':'owner','chat':'chat-a','profile':None,'thread':None}], 'include':['agent_status']})
        self.gateway=Gateway()
        self.plugin=self.module.GatewayPlugin(self.ctx)
    def event(self,text='/vrc 开始',**kw):
        data=dict(platform=Platform.TELEGRAM,user_id='owner',chat_id='chat-a',chat_type='dm');data.update(kw)
        return MessageEvent(text=text,source=SessionSource(**data))
    async def wait_for(self,predicate):
        async with asyncio.timeout(4):
            while not predicate():await asyncio.sleep(.01)
    async def asyncTearDown(self):
        await self.plugin.close()
        await asyncio.gather(*self.ctx.tasks,return_exceptions=True)
        self.assertFalse(self.path.exists())
    async def test_GP001_owner_auth_and_explicit_manual_start(self):
        self.assertFalse(self.path.exists())
        self.assertIsNone(self.plugin.dispatch(event=self.event('普通聊天'),gateway=self.gateway))
        for kw in ({'user_id':'other'},{'chat_id':'other'},{'chat_type':'group'},{'profile':'other'},{'thread_id':'other'},{'is_bot':True}):
            self.assertEqual(self.plugin.dispatch(event=self.event(**kw),gateway=self.gateway)['action'],'skip')
            self.assertFalse(self.path.exists());self.assertEqual(self.ctx.tasks,[])
        self.gateway.authorized=False
        self.plugin.dispatch(event=self.event(),gateway=self.gateway)
        self.assertEqual(self.ctx.tasks,[])
        self.gateway.authorized=True
        self.assertEqual(self.plugin.dispatch(event=self.event('/VRC 开始'),gateway=self.gateway)['action'],'skip')
        await self.wait_for(lambda:self.path.exists() and bool(self.gateway.sent))
        self.assertEqual(self.gateway.resolutions,0,'start/list must not resolve model credentials')
        self.plugin.dispatch(event=self.event('/vrc 关闭'),gateway=self.gateway)
        await self.wait_for(lambda:not self.path.exists())

    async def test_GP002_stop_reset_revoke_before_queue_or_model_dispatch(self):
        route=('telegram','owner','chat-a',None,None)
        calls=[]
        self.plugin.host=SimpleNamespace(chats={route:object()},request_stop=lambda value:calls.append(value))
        try:
            for text in ('/stop','/new','/reset','/vrc 停止'):
                self.plugin.pending=set(range(8))
                result=self.plugin.dispatch(event=self.event(text),gateway=self.gateway)
                self.assertEqual(calls[-1:] ,[route],text+' failed to revoke')
                if text!='/vrc 停止':self.assertIsNone(result)
            self.assertEqual(len(calls),4)
        finally:self.plugin.host=None;self.plugin.pending.clear()

    async def test_GP003_native_manager_hook_and_unload_own_receiver(self):
        from unittest.mock import patch
        manager=PluginManager()
        manifest=PluginManifest(name='vrc-fixture',version='0.1.0')
        ctx=PluginContext(manifest,manager)
        with patch.object(ctx,'get_config',self.ctx.get_config):
            plugin=self.module.GatewayPlugin(ctx)
        try:
            results=manager.invoke_hook('pre_gateway_dispatch',event=self.event(),gateway=self.gateway)
            self.assertEqual(results,[{'action':'skip','reason':'candidate_private_command'}])
            await self.wait_for(lambda:self.path.exists())
            task=plugin.runner
            self.assertTrue(manager.unload('vrc-fixture'))
            await asyncio.gather(task,return_exceptions=True)
            self.assertFalse(self.path.exists())
            self.assertEqual(manager.invoke_hook('pre_gateway_dispatch',event=self.event(),gateway=self.gateway),[])
        finally:
            await plugin.close()
            manager.unload('vrc-fixture')

    async def test_GP004_unload_revokes_before_async_cleanup(self):
        route=('telegram','owner','chat-a',None,None);calls=[]
        self.plugin.host=SimpleNamespace(chats={route:object()},request_stop=calls.append)
        try:
            self.plugin.request_close()
            self.assertEqual(calls,[route])
        finally:self.plugin.host=None

    async def test_GP005_relocated_plugin_loads_without_sys_path_mutation(self):
        import importlib.util
        from unittest.mock import patch
        build=ROOT/'distribution/hermes_plugin.py'
        self.assertTrue(build.is_file(),'missing_plugin_assembler')
        spec=importlib.util.spec_from_file_location('candidate_plugin_build',build)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        files=module.collect(ROOT)
        folder=Path(self.home.name)/'relocated-plugin';folder.mkdir()
        for name,data in files.items():(folder/name).write_bytes(data)
        manifest=PluginManifest(name='vrchat-agent-candidate',version='0.2.0-preview.1',path=str(folder),source='user')
        manager=PluginManager()
        before=list(sys.path)
        plugin_module=manager._load_directory_module(manifest)
        self.assertEqual(sys.path,before)
        ctx=PluginContext(manifest,manager)
        with patch.object(ctx,'get_config',self.ctx.get_config):
            plugin=plugin_module.register(ctx)
        try:
            self.assertTrue(plugin.__class__.__module__.startswith(plugin_module.__name__+'.'))
            self.assertFalse(self.path.exists())
            manager.invoke_hook('pre_gateway_dispatch',event=self.event(),gateway=self.gateway)
            await self.wait_for(lambda:self.path.exists() and plugin.host is not None)
            self.assertTrue(plugin.host.__class__.__module__.startswith(plugin_module.__name__+'.'))
            task=plugin.runner;manager.unload(manifest.name)
            await asyncio.gather(task,return_exceptions=True)
            self.assertFalse(self.path.exists());self.assertEqual(sys.path,before)
        finally:
            await plugin.close();manager.unload(manifest.name)

    async def test_GP006_native_discovery_is_opt_in_and_uses_profile_settings(self):
        import importlib.util,json,os
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('candidate_plugin_build',ROOT/'distribution/hermes_plugin.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        home=Path(self.home.name)/'isolated-profile';home.mkdir()
        folder=home/'plugins/vrchat-agent-candidate';folder.mkdir(parents=True)
        for name,data in module.collect(ROOT).items():(folder/name).write_bytes(data)
        settings={'plugins':{'enabled':[], 'entries':{'vrchat-agent-candidate':{'settings':self.ctx.settings}}}}
        (home/'config.yaml').write_text(json.dumps(settings))
        manager=PluginManager(scope_key=str(home))
        with patch.dict(os.environ,{'HERMES_SAFE_MODE':'0'}):
            try:
                manager.discover_and_load()
                self.assertFalse(manager._plugins['vrchat-agent-candidate'].enabled)
                self.assertFalse(self.path.exists())
                settings['plugins']['enabled']=['vrchat-agent-candidate']
                (home/'config.yaml').write_text(json.dumps(settings))
                manager.discover_and_load(force=True)
                loaded=manager._plugins['vrchat-agent-candidate']
                self.assertTrue(loaded.enabled,loaded.error)
                self.assertEqual(loaded.hooks_registered,['pre_gateway_dispatch'])
                self.assertFalse(self.path.exists())
                manager.invoke_hook('pre_gateway_dispatch',event=self.event(),gateway=self.gateway)
                await self.wait_for(lambda:self.path.exists() and bool(self.gateway.sent))
                manager.unload('vrchat-agent-candidate')
                await self.wait_for(lambda:not self.path.exists())
            finally:manager.unload()

    async def test_GP007_one_receiver_cannot_mix_operator_identities(self):
        settings={**self.ctx.settings,'owners':self.ctx.settings['owners']+[
            {'platform':'telegram','user':'other-owner','chat':'chat-b','profile':None,'thread':None}]}
        ctx=Context(settings);plugin=self.module.GatewayPlugin(ctx)
        try:
            plugin.dispatch(event=self.event(),gateway=self.gateway)
            self.assertEqual(ctx.tasks,[],"mixed owners could see or claim one another's pending offers")
            self.assertFalse(self.path.exists())
        finally:
            await plugin.close();await asyncio.gather(*ctx.tasks,return_exceptions=True)

    async def test_GP008_exact_plugin_payload_passes_native_scan(self):
        import importlib.util
        from tools.plugin_guard import scan_plugin
        spec=importlib.util.spec_from_file_location('candidate_plugin_scan',ROOT/'distribution/hermes_plugin.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        folder=Path(self.home.name)/'scanned-plugin';folder.mkdir()
        for name,data in module.collect(ROOT).items():(folder/name).write_bytes(data)
        result=scan_plugin(folder)
        self.assertEqual(result.verdict,'safe',[(f.file,f.line,f.pattern_id) for f in result.findings])
        self.assertEqual(result.findings,[])

    async def test_GP009_native_source_snapshot_preserves_exact_route_and_trust(self):
        from unittest.mock import patch
        calls=[];expected=('telegram','owner','chat-a','work','topic')
        self.plugin.routes={expected}
        self.plugin.host=SimpleNamespace(chats={},request_stop=calls.append)
        try:
            # Real Hermes serialization, not a replacement source dictionary.
            source=self.event(profile='work',thread_id='topic').source
            with patch.object(source,'to_dict',wraps=source.to_dict) as snapshot:
                self.plugin.dispatch(event=MessageEvent(text='/stop',source=source),gateway=self.gateway)
                self.assertEqual(calls,[expected])
                snapshot.assert_called_once_with()
            for changes in ({'user_id':'other'},{'chat_id':'other'},{'profile':None},
                            {'profile':'other'},{'thread_id':None},{'thread_id':'other'},
                            {'chat_type':'group'},{'is_bot':True},{'profile_route_rejected':True}):
                before=len(calls)
                event=self.event('/stop',**({'profile':'work','thread_id':'topic'}|changes))
                self.plugin.dispatch(event=event,gateway=self.gateway)
                self.assertEqual(len(calls),before,changes)
            self.gateway.authorized=False
            self.plugin.dispatch(event=self.event('/stop',profile='work',thread_id='topic'),gateway=self.gateway)
            self.assertEqual(calls,[expected])
            self.gateway.authorized=True
            self.plugin.routes={('telegram','owner','chat-a',None,None)}
            for profile in ('',False,0):
                self.plugin.dispatch(event=self.event('/stop',profile=profile),gateway=self.gateway)
                self.assertEqual(calls,[expected],'lossy profile serialization must not admit a default route')
            self.plugin.dispatch(event=self.event('/stop'),gateway=self.gateway)
            self.assertEqual(calls[-1],('telegram','owner','chat-a',None,None))
            self.assertEqual(self.ctx.tasks,[])
            self.assertEqual(self.gateway.resolutions,0)
        finally:self.plugin.host=None

    async def test_GP010_source_serialization_failure_is_closed(self):
        from unittest.mock import patch
        calls=[]
        self.plugin.host=SimpleNamespace(chats={},request_stop=calls.append)
        try:
            source=self.event().source
            for failure in (RuntimeError('fixture serialization failure'),):
                with patch.object(source,'to_dict',side_effect=failure):
                    self.plugin.dispatch(event=MessageEvent(text='/stop',source=source),gateway=self.gateway)
                    self.assertEqual(calls,[])
            with patch.object(source,'to_dict',return_value={}):
                self.plugin.dispatch(event=MessageEvent(text='/stop',source=source),gateway=self.gateway)
                self.assertEqual(calls,[])
            self.assertEqual(self.ctx.tasks,[])
        finally:self.plugin.host=None

if __name__=='__main__':unittest.main(verbosity=2)
