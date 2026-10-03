"""Isolated installed-Hermes MCP engine probe; no agent/model turn or config write."""
import asyncio
import json
import logging
import os
from pathlib import Path
import ssl
import sys

async def registry_probe(config, allowed):
    # This module only runs in the verifier's newly created Hermes process/home.
    # Do not call global shutdown inside a user's gateway or shared process.
    import importlib.metadata
    from tools import mcp_tool
    from tools.registry import registry
    name='candidate-native-test'
    assert not mcp_tool.get_registered_mcp_server_names()
    baseline=set(registry.get_all_tool_names())
    config.update(lazy=False, trust='full')  # fixed test server, not task approval
    expected={mcp_tool.mcp_prefixed_tool_name(name,raw) for raw in allowed}
    result={'native':'hermes','mcp_version':importlib.metadata.version('mcp'),
            'registry_verified':False,'pass_ids':[],
            'test_server_trust':'full; fixed fixture only, not task approval'}
    try:
        registered=await asyncio.to_thread(mcp_tool.register_mcp_servers,{name:config})
        actual=set(registry.get_all_tool_names())-baseline
        if not set(registered)==actual==expected:
            print(json.dumps({'registry_diagnostic':{'returned':sorted(registered),'added':sorted(actual),'expected':sorted(expected),
                'registered_servers':sorted(mcp_tool.get_registered_mcp_server_names())}}),flush=True)
        assert set(registered)==actual==expected
        assert set(registry.get_tool_names_for_toolset('mcp-'+name))==expected
        assert {registry.get_schema(n)['name'] for n in expected}==expected
        result['tools']=sorted(actual);result['pass_ids'].append('HR001')
        async def dispatch(raw,args):
            value=await asyncio.to_thread(registry.dispatch,mcp_tool.mcp_prefixed_tool_name(name,raw),args)
            return json.loads(value) if isinstance(value,str) else value
        denied=await dispatch('material_prepare',{})
        assert type(denied) is dict and 'Unknown tool:' in denied.get('error','')
        result['pass_ids'].append('HR002')
        status=await dispatch('agent_status',{})
        if 'expected_project_not_connected' not in status.get('error',''):
            print(json.dumps({'registry_diagnostic':{'phase':'status','keys':sorted(status),
                'expected_error_seen': 'expected_project_not_connected' in json.dumps(status),
                'error_type':type(status.get('error')).__name__,
                'error_safe_categories':[x for x in ('Unknown tool','not connected','trust','approval','event loop','timeout','Invalid','NameError','TypeError') if x in json.dumps(status)]}}),flush=True)
        assert 'expected_project_not_connected' in status.get('error','')
        stopped=await dispatch('agent_stop',{'task_id':'no-approved-plan'})
        expected_stop={'success':True,'data':{'status':'locally_stopped','unity_confirmed':False}}
        assert set(stopped)=={'result','structuredContent'}
        assert stopped['structuredContent']==json.loads(stopped['result'])==expected_stop
        result['missing_unity_refused']=True;result['unapproved_stop_local_only']=True
        result['pass_ids'].append('HR003')
        again=await asyncio.to_thread(mcp_tool.register_mcp_servers,{name:config})
        assert set(again)==expected and set(registry.get_all_tool_names())-baseline==expected
        result['pass_ids'].append('HR004')
        # Characterize documented native semantics: disabled/reconfigured existing
        # names are NOT revocation. Never use this API as a credential rotation.
        disabled={**config,'enabled':False,'tools':{'include':[], 'resources':False, 'prompts':False}}
        unchanged=await asyncio.to_thread(mcp_tool.register_mcp_servers,{name:disabled})
        assert set(unchanged)==expected and set(registry.get_all_tool_names())-baseline==expected
        result['existing_name_not_reconfigured']=True
    finally:
        await asyncio.to_thread(mcp_tool.shutdown_mcp_servers)
        config['headers'].clear()
    assert not mcp_tool.get_registered_mcp_server_names()
    assert set(registry.get_all_tool_names())==baseline
    assert mcp_tool._mcp_loop is None or not mcp_tool._mcp_loop.is_running()
    stale=await dispatch('agent_stop',{'task_id':'no-approved-plan'})
    assert 'Unknown tool:' in stale.get('error','')
    result['pass_ids'].extend(['HR005','HR006'])
    result['registry_verified']=True;result['shutdown_complete']=True
    print(json.dumps(result),flush=True)

async def owned_shutdown_probe(config):
    """Two independent native owners in one isolated process; not an installed receiver."""
    from tools import mcp_tool
    from tools.registry import registry
    from mcp.shared.exceptions import MCPError
    from mcp_types import CONNECTION_CLOSED
    import importlib.metadata
    assert not mcp_tool.get_registered_mcp_server_names()
    baseline=set(registry.get_all_tool_names())
    observer_name='candidate-unrelated-probe'
    observer_token=os.environ.pop('VRCHAT_AGENT_TEST_PROBE_TOKEN')
    observer_config={**config,'headers':{'Authorization':'Bearer '+observer_token},
        'tools':{'include':['agent_status'],'resources':False,'prompts':False},
        'lazy':False,'trust':'full'}
    observer_tool=mcp_tool.mcp_prefixed_tool_name(observer_name,'agent_status')
    owned=mcp_tool.MCPServerTask('candidate-owned-generation-1')
    replacement=mcp_tool.MCPServerTask('candidate-owned-generation-2')
    result={'native':'hermes','mcp_version':importlib.metadata.version('mcp'),
        'owned_shutdown_verified':False,'pass_ids':[],
        'scope':'independently owned native task next to registered read-only service; same fixture endpoint, distinct sessions',
        'global_registry_removal_implemented':False}
    async def observer_ok():
        answer=await asyncio.to_thread(registry.dispatch,observer_tool,{})
        answer=json.loads(answer) if isinstance(answer,str) else answer
        assert 'expected_project_not_connected' in answer.get('error','')
        assert mcp_tool.get_registered_mcp_server_names()=={observer_name}
        assert set(registry.get_all_tool_names())==baseline|{observer_tool}
    async def owned_ok(peer):
        response=await peer.session.call_tool('agent_status',{})
        assert response.is_error and any('expected_project_not_connected' in getattr(x,'text','') for x in response.content)
    try:
        names=await asyncio.to_thread(mcp_tool.register_mcp_servers,{observer_name:observer_config})
        assert names==[observer_tool]
        schema_before=json.dumps(registry.get_schema(observer_tool),sort_keys=True)
        await asyncio.wait_for(owned.start(config),12)
        assert owned.session is not None
        await owned_ok(owned);await observer_ok()
        result['pass_ids'].append('HS001')
        previous_session=owned.session
        await owned.shutdown()
        assert owned.session is None and owned._task.done()
        await observer_ok()
        assert json.dumps(registry.get_schema(observer_tool),sort_keys=True)==schema_before
        result['pass_ids'].append('HS002')
        try:
            await asyncio.wait_for(previous_session.call_tool('agent_status',{}),3)
        except MCPError as exc:
            assert exc.code==CONNECTION_CLOSED
            result['closed_session_error_type']=type(exc).__name__
            result['closed_session_error_code']=exc.code
        else:
            raise AssertionError('closed_session_not_refused')
        result['pass_ids'].append('HS003')
        await asyncio.wait_for(replacement.start(config),12)
        fresh=replacement.session
        assert fresh is not None and fresh is not previous_session
        await owned.shutdown()  # Late/repeated close must remain bound to generation 1.
        assert replacement.session is fresh and not replacement._task.done()
        await owned_ok(replacement);await observer_ok()
        assert json.dumps(registry.get_schema(observer_tool),sort_keys=True)==schema_before
        await replacement.shutdown()
        assert replacement.session is None and replacement._task.done()
        result['pass_ids'].append('HS004')
    finally:
        try:
            await asyncio.gather(owned.shutdown(),replacement.shutdown())
        finally:
            # This is only final cleanup of this owned TEST process; never a
            # candidate disconnect implementation inside a user's shared gateway.
            await asyncio.to_thread(mcp_tool.shutdown_mcp_servers)
            config['headers'].clear();observer_config['headers'].clear()
    assert not mcp_tool.get_registered_mcp_server_names()
    assert set(registry.get_all_tool_names())==baseline
    result['owned_shutdown_verified']=True;result['shutdown_complete']=True
    print(json.dumps(result),flush=True)

async def binding_probe(config):
    """Exercise the shipped adapter through native dispatch, without a model turn."""
    from tools import mcp_tool
    from tools.registry import registry
    from model_tools import handle_function_call
    import importlib.metadata
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'clients'))
    from hermes_binding import bind
    assert not mcp_tool.get_registered_mcp_server_names()
    baseline=set(registry.get_all_tool_names())
    observer_name='candidate-binding-probe'
    observer_config={**config,'headers':{'Authorization':'Bearer '+os.environ.pop('VRCHAT_AGENT_TEST_PROBE_TOKEN')},
        'tools':{'include':['agent_status'],'resources':False,'prompts':False},'lazy':False,'trust':'full'}
    observer_tool=mcp_tool.mcp_prefixed_tool_name(observer_name,'agent_status')
    first=mcp_tool.MCPServerTask('candidate-binding-first')
    second=mcp_tool.MCPServerTask('candidate-binding-second')
    bindings=[]
    result={'native':'hermes','mcp_version':importlib.metadata.version('mcp'),
        'binding_verified':False,'pass_ids':[], 'model_turn':False}
    async def observer_ok():
        value=json.loads(await asyncio.to_thread(registry.dispatch,observer_tool,{}))
        assert 'expected_project_not_connected' in value.get('error','')
        assert mcp_tool.get_registered_mcp_server_names()=={observer_name}
    async def dispatch(name,args,session,names):
        # Installed normal dispatcher propagates runtime session_id separately
        # from model tool arguments; no hooks/middleware bypass flags are used.
        value=await asyncio.to_thread(handle_function_call,name,args,
            session_id=session,task_id='test-turn',enabled_tools=names)
        return json.loads(value)
    try:
        assert await asyncio.to_thread(mcp_tool.register_mcp_servers,{observer_name:observer_config})==[observer_tool]
        observer_schema=json.dumps(registry.get_schema(observer_tool),sort_keys=True)
        await first.start(config)
        one=await bind(first,registry,conversation_id='candidate-chat-a',include=('agent_status','agent_stop'))
        bindings.append(one)
        snapshot=one.snapshot();names=[t['function']['name'] for t in snapshot]
        assert len(names)==2 and set(registry.get_all_tool_names())==baseline|set(names)|{observer_tool}
        snapshot[0]['function']['description']='test mutation'
        assert one.snapshot()[0]['function']['description']!='test mutation'
        stale_entry=registry.get_entry(names[0]);result['pass_ids'].append('HB001')
        for session in (None,'candidate-chat-b'):
            denied=await dispatch(names[0],{'session_id':'candidate-chat-a'},session,names)
            assert denied.get('error')=='candidate_wrong_conversation'
        result['pass_ids'].append('HB002')
        status=await dispatch(names[0],{},'candidate-chat-a',names)
        assert status['error']=='candidate_remote_error' and status['mcp']['isError']
        assert 'expected_project_not_connected' in json.dumps(status['mcp'])
        stopped=await dispatch(names[1],{'task_id':'no-approved-plan'},'candidate-chat-a',names)
        assert not stopped['mcp']['isError'] and stopped['mcp']['structuredContent']['data']=={'status':'locally_stopped','unity_confirmed':False}
        await observer_ok();result['pass_ids'].append('HB003')
        await one.close()
        assert not set(names)&set(registry.get_all_tool_names())
        stale=json.loads(await asyncio.to_thread(stale_entry.handler,{},session_id='candidate-chat-a'))
        assert stale['error']=='candidate_binding_closed'
        absent=json.loads(await asyncio.to_thread(registry.dispatch,names[0],{},session_id='candidate-chat-a'))
        assert 'Unknown tool:' in absent['error']
        await observer_ok();result['pass_ids'].append('HB004')
        await second.start(config)
        two=await bind(second,registry,conversation_id='candidate-chat-b',include=('agent_status',))
        bindings.append(two);new_names=[t['function']['name'] for t in two.snapshot()]
        assert set(names).isdisjoint(new_names)
        await one.close()
        denied=await dispatch(new_names[0],{},'candidate-chat-a',new_names)
        assert denied.get('error')=='candidate_wrong_conversation'
        status=await dispatch(new_names[0],{},'candidate-chat-b',new_names)
        assert status['error']=='candidate_remote_error'
        await observer_ok()
        assert json.dumps(registry.get_schema(observer_tool),sort_keys=True)==observer_schema
        await two.close();result['pass_ids'].append('HB005')
        assert set(registry.get_all_tool_names())==baseline|{observer_tool}
    finally:
        try:
            for binding in bindings:await binding.close()
            await asyncio.gather(first.shutdown(),second.shutdown())
        finally:
            # Test process owns this observer; production adapter never uses global shutdown.
            await asyncio.to_thread(mcp_tool.shutdown_mcp_servers)
            config['headers'].clear();observer_config['headers'].clear()
    assert set(registry.get_all_tool_names())==baseline
    assert not mcp_tool.get_registered_mcp_server_names()
    result['binding_verified']=True;result['shutdown_complete']=True
    print(json.dumps(result),flush=True)

async def conversation_probe(config, fixed=None):
    """Real AIAgent construction/executor, fixture tool messages; never a model turn."""
    from urllib.parse import urlsplit
    from types import SimpleNamespace
    from tools import mcp_tool
    from tools.registry import registry
    from model_tools import get_tool_definitions
    import importlib.metadata
    from run_agent import AIAgent
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'clients'))
    from hermes_conversation import conversation
    transport_paths = {}
    if fixed is not None:
        import importlib, hashlib
        for module_name in ('mcp.client.streamable_http','mcp.client.session','mcp.shared.dispatcher','mcp.shared.jsonrpc_dispatcher',
                mcp_tool.sdk_httpx().__name__+'._client',mcp_tool.sdk_httpx().__name__+'._transports.default'):
            transport_paths[module_name] = Path(importlib.import_module(module_name).__file__)
    transport_hashes = {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in transport_paths.items()}
    endpoint=urlsplit(config['url']);network={'allowed':0,'denied':0,'denied_locations':[]}
    def blocked():
        import traceback
        network['denied']+=1
        network['denied_locations'].append([{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_stack(limit=36)])
    def guard(event,args):
        if event=='socket.getaddrinfo' and args[0] not in ('127.0.0.1',b'127.0.0.1'):
            blocked();raise RuntimeError('test_external_network_forbidden')
        if event=='socket.connect':
            address=args[1]
            if not isinstance(address,tuple) or address[:2]!=('127.0.0.1',endpoint.port):
                blocked();raise RuntimeError('test_nonfixture_connection_forbidden')
            network['allowed']+=1
    sys.addaudithook(guard)
    baseline=set(registry.get_all_tool_names());observer_name='candidate-conversation-observer'
    observer_config={**config,'headers':{'Authorization':'Bearer '+os.environ.pop('VRCHAT_AGENT_TEST_PROBE_TOKEN')},
        'tools':{'include':['agent_status'],'resources':False,'prompts':False},'lazy':False,'trust':'full'}
    observer_tool=mcp_tool.mcp_prefixed_tool_name(observer_name,'agent_status')
    first=mcp_tool.MCPServerTask('candidate-conversation-first');second=mcp_tool.MCPServerTask('candidate-conversation-second')
    options={'provider':'openai','model':'gpt-4.1','api_mode':'chat_completions',
        'base_url':'https://candidate-model.invalid/v1','api_key':'fixture-only-not-a-credential',
        'quiet_mode':True,'skip_memory':True,'skip_background_review':True,
        'skip_context_files':True,'save_trajectories':False,'max_iterations':1}
    result={'native':'hermes','mcp_version':importlib.metadata.version('mcp'),
        'conversation_verified':False,'pass_ids':[],'model_turn':False,'fixture_tool_messages':True}
    async def observer_ok():
        value=json.loads(await asyncio.to_thread(registry.dispatch,observer_tool,{}))
        assert 'expected_project_not_connected' in value.get('error','')
        assert mcp_tool.get_registered_mcp_server_names()=={observer_name}
    async def execute(agent,raw,args,bridge=None):
        call=SimpleNamespace(id='fixture-call',type='function',function=SimpleNamespace(
            name=bridge or 'tool_call',arguments=json.dumps(args if bridge else {'name':raw,'arguments':args})))
        message=SimpleNamespace(tool_calls=[call]);messages=[]
        await asyncio.to_thread(agent._execute_tool_calls,message,messages,agent.session_id)
        assert len(messages)==1 and messages[0]['role']=='tool'
        return json.loads(messages[0]['content'])
    try:
        assert await asyncio.to_thread(mcp_tool.register_mcp_servers,{observer_name:observer_config})==[observer_tool]
        if fixed is None:
            await first.start(config);await second.start(config)
        else:
            from hermes_connection import connect
            from unittest.mock import patch
            grant = dict(port=endpoint.port, certificate=fixed['certificate'],pin=fixed['pin'],
                expires_at=fixed['expires_at'], bearer=config['headers']['Authorization'].removeprefix('Bearer '))
            for invalid in ({**grant,'certificate':fixed['other_certificate'],'pin':fixed['other_pin']},
                            {**grant,'bearer':'candidate-invalid-bearer'}):
                try:
                    unexpected = await connect(**invalid)
                except RuntimeError as exc:
                    assert str(exc)=='candidate_connection_failed'
                else:
                    await unexpected.shutdown()
                    raise AssertionError('invalid_connection_admitted')
            # Invalid proxy environment must not be consulted by this connector.
            with patch.dict(os.environ, {'HTTPS_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':''}):
                first = await connect(**grant)
                second = await connect(**grant)
        async with conversation(first,include=('agent_status','agent_stop'),options=options) as a:
            assert isinstance(a,AIAgent)
            assert a.valid_tool_names=={'tool_search','tool_describe','tool_call'}
            raw_a=get_tool_definitions(enabled_toolsets=a.enabled_toolsets,quiet_mode=True,skip_tool_search_assembly=True)
            names_a=[v['function']['name'] for v in raw_a];assert len(names_a)==2
            original=json.dumps(a.tools,sort_keys=True);result['pass_ids'].append('HN001')
            status=await execute(a,names_a[0],{})
            assert status.get('error')=='candidate_remote_error' and status['mcp']['isError']
            stop=await execute(a,names_a[1],{'task_id':'no-approved-plan'})
            assert stop['mcp']['structuredContent']['data']=={'status':'locally_stopped','unity_confirmed':False}
            await observer_ok();result['pass_ids'].append('HN002')
            async with conversation(second,include=('agent_status',),options=options) as b:
                assert b.session_id!=a.session_id
                raw_b=get_tool_definitions(enabled_toolsets=b.enabled_toolsets,quiet_mode=True,skip_tool_search_assembly=True)
                assert len(raw_b)==1;name_b=raw_b[0]['function']['name']
                assert name_b not in names_a
                found_a=await execute(a,None,{'queries':['Unity']},bridge='tool_search')
                found_b=await execute(b,None,{'queries':['Unity']},bridge='tool_search')
                assert found_a['total_available']==2 and names_a[0] in found_a['tools']
                assert found_b['total_available']==1 and set(found_b['tools'])=={name_b}
                assert name_b not in json.dumps(found_a) and not any(n in json.dumps(found_b) for n in names_a)
                described=await execute(a,None,{'names':[names_a[0],name_b,observer_tool]},bridge='tool_describe')
                assert set(described['tools'])=={names_a[0]} and set(described['not_found'])=={name_b,observer_tool}
                denied_a=await execute(a,name_b,{})
                denied_b=await execute(b,names_a[0],{})
                assert denied_a.get('error') and denied_b.get('error')
                result['pass_ids'].append('HN003')
                status=await execute(b,name_b,{})
                assert status.get('error')=='candidate_remote_error'
                assert json.dumps(a.tools,sort_keys=True)==original
                await observer_ok()
            assert second.session is None and b.client is None
            assert json.dumps(a.tools,sort_keys=True)==original
            result['pass_ids'].append('HN004')
        assert first.session is None and a.client is None
        stale=await execute(a,names_a[0],{})
        assert stale.get('error')
        await observer_ok();result['pass_ids'].append('HN005')
        assert set(registry.get_all_tool_names())==baseline|{observer_tool}
        if fixed is not None:
            import time
            expiring = await connect(**{**grant,'expires_at':int(time.time())+2})
            try:
                await asyncio.wait_for(asyncio.shield(expiring._task),3)
                assert expiring.session is None and expiring.session_cleanup_confirmed
            finally:
                await expiring.shutdown()
    finally:
        try:await asyncio.gather(first.shutdown(),second.shutdown())
        finally:
            await asyncio.to_thread(mcp_tool.shutdown_mcp_servers)
            config['headers'].clear();observer_config['headers'].clear()
    assert set(registry.get_all_tool_names())==baseline
    assert network['denied']==0
    result['conversation_verified']=True;result['shutdown_complete']=True;result['network_guard']=network
    if fixed is not None:
        assert first.session_cleanup_confirmed and second.session_cleanup_confirmed
        result['fixed_connection_verified']=True
        result['pass_ids']=[value.replace('HN','HT') for value in result['pass_ids']]
        result['sdk_transport_not_MCPServerTask']=True
        result['pass_ids'].extend(['HT006','HT007'])
        result['pass_ids'].append('HT008')
        assert transport_hashes == {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in transport_paths.items()}
        result['transport_inputs'] = transport_hashes
        result['transport_inputs_unchanged'] = True
    print(json.dumps(result),flush=True)

async def handoff_approved_probe(doc, token, allowed):
    """Real stdio relay/UNIX IPC/TLS/native registry, but fixture host selection."""
    import tempfile
    from contextlib import AsyncExitStack
    from model_tools import handle_function_call
    from tools.registry import registry
    root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(root),str(root/'tests'),str(root/'clients')]
    from hermes_handoff import Receiver
    from native_gateway_fixture import gateway_fixture
    baseline=set(registry.get_all_tool_names())
    with tempfile.TemporaryDirectory(prefix='vrc-native-handoff-') as directory:
        path=Path(directory)/'receiver.sock'
        async with AsyncExitStack() as stack:
            fixture = await stack.enter_async_context(gateway_fixture(path,tuple(allowed))) if doc.get('chat') else None
            chat_host = fixture.host if fixture else None
            receiver = chat_host.receiver if chat_host else await stack.enter_async_context(Receiver(path))
            envelope={**doc['handoff'],'bearer':token}
            ssh_report={}
            if doc.get('ssh'):
                from handoff_ssh_fixture import ssh_relay
                relay=await stack.enter_async_context(ssh_relay(path,envelope,ssh_report))
            else:
                relay=await asyncio.create_subprocess_exec(sys.executable,'-B',str(root/'clients/hermes_handoff_relay.py'),str(path),
                    stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                relay.stdin.write(json.dumps(envelope).encode()+b'\n'); await relay.stdin.drain()
            envelope.clear(); token=None
            try:
                offered=json.loads(await asyncio.wait_for(relay.stdout.readline(),5))
                assert offered['kind']=='offered'
                try:
                    agent = None
                    if chat_host:
                        assert (await fixture.command('绑定 '+offered['id'])).startswith('已绑定新的专用会话')
                        chat = chat_host.chats[fixture.route]
                        agent = chat.agent
                        assert agent is not None and agent.__class__.__name__ == 'AIAgent'
                        binding = chat.binding
                    else:
                        binding=await receiver.claim(offered['id'],conversation_id='fixture-native-handoff',include=tuple(allowed))
                except BaseException:
                    if doc.get('ssh'):
                        await stack.aclose()
                        print(json.dumps({'handoff_diagnostic':ssh_report}),flush=True)
                    raise
                names={raw:entry['function']['name'] for raw,entry in zip(allowed,binding.snapshot())}
                while line:=await asyncio.to_thread(sys.stdin.readline):
                    request=json.loads(line);method=request['method'];params=request['params']
                    if method=='ready':
                        assert params=={}
                        value={'native':'hermes','tools':list(names),'handoff_pass_ids':['HJ001','HJ002']}
                    elif method=='call':
                        assert set(params)=={'tool','arguments'} and params['tool'] in names
                        name=names[params['tool']]
                        if agent is not None:
                            from types import SimpleNamespace
                            call=SimpleNamespace(id='fixture-call',type='function',function=SimpleNamespace(name='tool_call',
                                arguments=json.dumps({'name':name,'arguments':params['arguments']})))
                            messages=[]
                            await asyncio.to_thread(agent._execute_tool_calls,SimpleNamespace(tool_calls=[call]),messages,agent.session_id)
                            assert len(messages)==1 and messages[0]['role']=='tool'
                            text=messages[0]['content']
                            response,end=json.JSONDecoder().raw_decode(text)
                            suffix=text[end:].strip()
                            # Native executor appends a warning on deliberate repeated denial.
                            # Keep its guard enabled; accept no other trailing content.
                            assert not suffix or (suffix.startswith('[Tool loop warning: ') and suffix.endswith(']'))
                        else:
                            response=json.loads(await asyncio.to_thread(handle_function_call,name,params['arguments'],
                                session_id='fixture-native-handoff',enabled_tools=list(names.values())))
                        assert 'mcp' in response
                        value=response['mcp']
                    elif method=='shutdown':
                        assert params=={}
                        if chat_host:
                            assert (await fixture.command('停止')).startswith('已停止并关闭本轮连接')
                            assert agent.client is None and not chat_host.chats
                        else:
                            relay.stdin.write(b'stop\n'); await relay.stdin.drain()
                        assert json.loads(await asyncio.wait_for(relay.stdout.readline(),10))=={'kind':'closed','clean':True}
                        assert await asyncio.wait_for(relay.wait(),5)==0
                        assert not receiver.offers() and set(registry.get_all_tool_names())==baseline
                        assert binding._peer.session_cleanup_confirmed
                        await stack.aclose()
                        value={'shutdown_complete':True}
                        if doc.get('ssh'):
                            assert ssh_report['ssh_authenticated'] and ssh_report['ssh_descendants']['clean']
                            value['ssh']=ssh_report
                    else:
                        raise AssertionError('unknown_test_operation')
                    print(json.dumps({'id':request['id'],'result':value}),flush=True)
                    if method=='shutdown':break
            finally:
                relay.stdin.close()
                if relay.returncode is None:
                    try: await asyncio.wait_for(relay.wait(),10)
                    except TimeoutError: relay.kill();await relay.wait()
                if not doc.get('ssh'): assert await relay.stderr.read()==b''
        assert not path.exists()
    assert not Path(directory).exists() and set(registry.get_all_tool_names())==baseline


async def main():
    # Source path is test-operator-selected, never exposed as a Candidate tool.
    source = Path(sys.argv[1]).resolve(strict=True)
    sys.path.insert(0, str(source))
    from tools.mcp_tool import MCPServerTask
    logging.disable(logging.CRITICAL)
    doc = json.loads(sys.stdin.readline())
    interactive = doc.get('mode') == 'approved-task'
    assert doc.get('mode') in (None, 'approved-task')
    allowed = (['agent_status','agent_catalog','agent_prepare','agent_stop','manage_material','read_console',
                'material_prepare','material_execute','material_stop'] if interactive
               else ['agent_status','agent_stop'])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=doc['certificate'])
    token = os.environ.pop('VRCHAT_AGENT_TEST_TOKEN')
    if doc.get('handoff') is not None:
        assert interactive
        await handoff_approved_probe(doc,token,allowed)
        return
    config = {'url': doc['endpoint'], 'headers': {'Authorization': 'Bearer '+token},
        'ssl_verify': context, 'strict_redirect_headers': True, 'connect_timeout': 8,
        'tools': {'include': allowed, 'resources': False, 'prompts': False},
        'sampling': {'enabled': False},
        'elicitation': {'enabled': False}}
    if doc.get('conversation') is True:
        assert not interactive and not doc.get('registry') and not doc.get('owned') and not doc.get('binding')
        await conversation_probe(config, doc.get('fixed_connection'))
        return
    if doc.get('binding') is True:
        assert not interactive and not doc.get('registry') and not doc.get('owned')
        await binding_probe(config)
        return
    if doc.get('owned') is True:
        assert not interactive and not doc.get('registry')
        await owned_shutdown_probe(config)
        return
    if doc.get('registry') is True:
        assert not interactive
        await registry_probe(config,allowed)
        return
    peer = MCPServerTask('candidate-native-test')
    try:
        await asyncio.wait_for(peer.start(config), 12)
        assert peer.session is not None
        catalog = await peer.session.list_tools()
        names = sorted(x.name for x in catalog.tools)
        assert 'agent_status' in names
        if interactive:
            # Test-only control pipe: no approvals, model turns, or arbitrary tools.
            while line := await asyncio.to_thread(sys.stdin.readline):
                request = json.loads(line)
                assert set(request) == {'id','method','params'}
                method, params = request['method'], request['params']
                if method == 'ready':
                    assert params == {}
                    value = {'native':'hermes','tools':names}
                elif method == 'call':
                    assert set(params)=={'tool','arguments'} and params['tool'] in allowed
                    result = await peer.session.call_tool(params['tool'],params['arguments'])
                    value = {'isError':result.is_error,'structuredContent':result.structured_content,
                             'content':[item.model_dump(mode='json',by_alias=True) for item in result.content]}
                elif method == 'shutdown':
                    assert params == {}
                    await peer.shutdown()
                    value = {'shutdown_complete':peer.session is None and peer._task.done()}
                else:
                    raise AssertionError('unknown_test_operation')
                print(json.dumps({'id':request['id'],'result':value}),flush=True)
                if method == 'shutdown': break
        else:
            result = await peer.session.call_tool('agent_status', {})
            assert result.is_error and any('expected_project_not_connected' in getattr(x,'text','') for x in result.content)
            stopped = await peer.session.call_tool('agent_stop', {'task_id':'no-approved-plan'})
            assert not stopped.is_error
            data = stopped.structured_content
            assert data == {'success':True,'data':{'status':'locally_stopped','unity_confirmed':False}}
    finally:
        await peer.shutdown()
        config['headers'].clear()
    assert peer.session is None and peer._task.done()
    if interactive: return
    import importlib.metadata
    print(json.dumps({'mcp_version':importlib.metadata.version('mcp'),'native': 'hermes', 'tools': names, 'missing_unity_refused': True,
        'shutdown_complete': True, 'unapproved_stop_local_only': True}), flush=True)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except BaseException as exc:
        # Do not serialize exception values: upstream may echo request content.
        import traceback
        frames = [{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)]
        print(json.dumps({'error_type': type(exc).__name__, 'frames':frames}), flush=True)
        raise SystemExit(1)
