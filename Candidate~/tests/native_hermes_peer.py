"""Isolated installed-Hermes MCP engine probe; no agent/model turn or config write."""
import asyncio
import json
import logging
import os
from pathlib import Path
import ssl
import sys

async def main():
    # Source path is test-operator-selected, never exposed as a Candidate tool.
    source = Path(sys.argv[1]).resolve(strict=True)
    sys.path.insert(0, str(source))
    from tools.mcp_tool import MCPServerTask
    logging.disable(logging.CRITICAL)
    doc = json.loads(sys.stdin.readline())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=doc['certificate'])
    token = os.environ.pop('VRCHAT_AGENT_TEST_TOKEN')
    config = {'url': doc['endpoint'], 'headers': {'Authorization': 'Bearer '+token},
        'ssl_verify': context, 'strict_redirect_headers': True, 'connect_timeout': 8,
        'tools': {'include': ['agent_status', 'agent_stop']}, 'resources': {'enabled': False},
        'prompts': {'enabled': False}, 'sampling': {'enabled': False},
        'elicitation': {'enabled': False}}
    peer = MCPServerTask('candidate-native-test')
    try:
        await asyncio.wait_for(peer.start(config), 12)
        assert peer.session is not None
        catalog = await peer.session.list_tools()
        names = sorted(x.name for x in catalog.tools)
        assert 'agent_status' in names
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
