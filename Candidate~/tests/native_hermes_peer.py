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

async def main():
    # Source path is test-operator-selected, never exposed as a Candidate tool.
    source = Path(sys.argv[1]).resolve(strict=True)
    sys.path.insert(0, str(source))
    from tools.mcp_tool import MCPServerTask
    logging.disable(logging.CRITICAL)
    doc = json.loads(sys.stdin.readline())
    interactive = doc.get('mode') == 'approved-task'
    assert doc.get('mode') in (None, 'approved-task')
    allowed = (['agent_status','agent_prepare','agent_stop','manage_material',
                'material_prepare','material_execute','material_stop'] if interactive
               else ['agent_status','agent_stop'])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=doc['certificate'])
    token = os.environ.pop('VRCHAT_AGENT_TEST_TOKEN')
    config = {'url': doc['endpoint'], 'headers': {'Authorization': 'Bearer '+token},
        'ssl_verify': context, 'strict_redirect_headers': True, 'connect_timeout': 8,
        'tools': {'include': allowed, 'resources': False, 'prompts': False},
        'sampling': {'enabled': False},
        'elicitation': {'enabled': False}}
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
