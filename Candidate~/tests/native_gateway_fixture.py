"""TEST ONLY: real copied plugin/manager; platform authorization/replies are doubles.
No message delivery, real model request, user configuration, or account login.
"""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT=Path(__file__).resolve().parents[1]

@asynccontextmanager
async def gateway_fixture(path, include):
    from gateway.session import SessionSource
    from gateway.platforms.base import MessageEvent
    from gateway.config import Platform
    from hermes_cli.plugins import PluginManager
    from hermes_constants import get_hermes_home
    home=get_hermes_home()
    config=home/'config.yaml'
    # Isolated verifier already created this exact public-only model hint.
    assert config.read_text()=='model:\n  context_length: 131072\n'
    name='vrchat-agent-candidate'
    folder=home/'plugins'/name;folder.mkdir(parents=True)
    spec=importlib.util.spec_from_file_location('native_candidate_plugin_build',ROOT/'distribution/hermes_plugin.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for filename,data in module.collect(ROOT).items():(folder/filename).write_bytes(data)
    config.write_text(json.dumps({'model':{'context_length':131072},'plugins':{'enabled':[name],
        'entries':{name:{'settings':{'socket':str(path),'include':list(include),
        'owners':[{'platform':'telegram','user':'fixture-owner','chat':'fixture-chat','profile':None,'thread':None}]}}}}}))
    source=SessionSource(platform=Platform.TELEGRAM,user_id='fixture-owner',chat_id='fixture-chat',chat_type='dm')
    route=('telegram','fixture-owner','fixture-chat',None,None)
    class Gateway:
        def __init__(self):self.sent=[]
        def _is_user_authorized_for_source(self,source):return source.user_id=='fixture-owner'
        def _adapter_for_source(self,source):return self
        def _thread_metadata_for_source(self,source,message_id):return {}
        async def send(self,chat_id,content,**kw):
            assert chat_id=='fixture-chat'
            self.sent.append(content);return SimpleNamespace(success=True)
        def _resolve_session_agent_runtime(self,**kwargs):
            return 'gpt-4.1',{'provider':'openai','api_mode':'chat_completions',
                'base_url':'https://candidate-model.invalid/v1','api_key':'fixture-only-not-a-credential',
                'skip_memory':True,'skip_background_review':True,'skip_context_files':True,'save_trajectories':False}
    gateway=Gateway();manager=PluginManager(scope_key=str(home));before=list(sys.path)
    manifest=manager._parse_manifest(folder/'plugin.yaml',folder,'user','')
    assert manifest is not None
    manager._load_plugin(manifest)
    loaded=manager._plugins[name]
    assert loaded.enabled and not loaded.error and loaded.hooks_registered==['pre_gateway_dispatch']
    assert sys.path==before and not path.exists()
    plugin=manager._hooks['pre_gateway_dispatch'][0].__self__
    async def command(text):
        n=len(gateway.sent)
        result=manager.invoke_hook('pre_gateway_dispatch',event=MessageEvent(text='/vrc '+text,source=source),gateway=gateway)
        assert result==[{'action':'skip','reason':'candidate_private_command'}]
        async with asyncio.timeout(12):
            while len(gateway.sent)==n or plugin.pending:await asyncio.sleep(.01)
        return gateway.sent[-1]
    try:
        assert (await command('开始')).startswith('接收入口已开启')
        assert plugin.host is not None
        yield SimpleNamespace(host=plugin.host,command=command,route=route,plugin=plugin)
    finally:
        manager.unload(name)
        await plugin.close()
        assert not path.exists() and sys.path==before
