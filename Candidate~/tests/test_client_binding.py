"""Signed principal reaches the Unity approval identity. Peer is a fixture, not Unity."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import unittest
import tempfile

WIRE_DLL = None  # Only a fresh-build verifier may supply this.
DOTNET = None

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'native/src'), str(ROOT/'tests')]
from fastmcp import Client
from test_runtime_unity_auth import UnityAuthTests
from test_runtime_lifecycle import PREPARE, READ
from test_runtime_material import MANIFEST


class ClientBindingTests(unittest.IsolatedAsyncioTestCase):
    fixture = UnityAuthTests.fixture
    connect = UnityAuthTests.connect
    register = UnityAuthTests.register

    @asynccontextmanager
    async def running(self):
        async with self.fixture() as (url, tokens, server):
            async with self.connect(url, tokens['unity']) as peer:
                connection = await self.register(peer)
                self.events = []
                async with self.core_peer(connection) as exchange:
                    self.exchange = exchange
                    async def respond():
                        async for raw in peer:
                            message = json.loads(raw)
                            if message['type'] == 'ping':
                                await peer.send(json.dumps({'type':'pong','session_id':connection}))
                                continue
                            self.events.append(message)
                            kind = message['params']['kind']
                            data = ({'status':'pending','plan_id':'fixture-plan-'+str(len(self.events))}
                                    if kind == 'prepare' else {'status':'stopped'} if kind == 'stop'
                                    else {'fixture_only':True})
                            result = (await exchange({'request':message['params'],'route':message['name']})) if exchange else {'success':True,'data':data}
                            await peer.send(json.dumps({'type':'command_result','id':message['id'],'result':result}))
                    responder = asyncio.create_task(respond())
                    try:
                        yield url.replace('ws:', 'http:').removesuffix('/hub/plugin')+'/mcp', tokens, server._candidate_runtime
                    finally:
                        responder.cancel()
                        await asyncio.gather(responder, return_exceptions=True)

    @asynccontextmanager
    async def core_peer(self, connection):
        if not getattr(self, 'use_core', False):
            yield None
            return
        self.assertTrue(WIRE_DLL and Path(WIRE_DLL).is_file() and DOTNET,
                        'fresh-build verifier must supply the compiled production gates')
        from test_bootstrap_runtime import child_environment
        import time
        with tempfile.TemporaryDirectory(prefix='candidate-client-core-') as home:
            started=time.monotonic();trace=[]
            process = await asyncio.create_subprocess_exec(str(DOTNET), str(WIRE_DLL),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=home, env={**child_environment(home), 'TMPDIR':home,'TEMP':home,'TMP':home,'VRC_FIXTURE_TRACE':'1'})
            async def capture_errors():
                other=[]
                async for line in process.stderr:
                    if line.strip() in {b'VRC_WIRE_PHASE:'+phase for phase in (b'main',b'fixture',b'ready',b'reply',b'eof')}:
                        trace.append({'phase':line.decode().strip().split(':')[1], 'elapsed_ms':round((time.monotonic()-started)*1000)})
                    else:other.append(line)
                return b''.join(other)
            errors = asyncio.create_task(capture_errors())
            lock = asyncio.Lock()
            async def exchange(message):
                async with lock:
                    process.stdin.write((json.dumps(message)+'\n').encode())
                    await process.stdin.drain()
                    raw = await asyncio.wait_for(process.stdout.readline(), 3)
                    self.assertTrue(raw, 'compiled gate exited')
                    return json.loads(raw)
            try:
                sys.path.insert(0,str(ROOT))
                from launcher.candidate_launch import START_TIMEOUT
                started_message=await asyncio.wait_for(process.stdout.readline(), START_TIMEOUT)
                self.assertEqual(json.loads(started_message),{'fixture_started':True})
                self.assertTrue((await exchange({'fixture_connection':connection}))['fixture_ready'])
                yield exchange
            finally:
                process.stdin.close()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
                    self.fail('compiled gate required safety kill')
                finally:
                    error = await errors
                    print(json.dumps({'fixture_startup_trace':trace,'returncode':process.returncode}))
                self.assertEqual(process.returncode,0,error.decode())
                self.assertFalse(error)
                self.assertEqual(list(Path(home).iterdir()),[], 'compiled fixture failed to remove owned files')
        self.assertFalse(Path(home).exists())

    async def test_CB001_signed_principal_and_sdk_session_both_reach_unity(self):
        async with self.running() as (url, tokens, runtime):
            async with Client(url, auth=tokens['mcp']) as client:
                await client.call_tool('agent_status', {})
                sdk_session = client.transport.get_session_id()
                self.assertEqual(self.events[-1]['params']['client_id'],
                    json.dumps(['fixture-client',sdk_session],separators=(',',':')),
                    'Unity approval sees only an opaque session, not its verified principal')
            self.assertEqual(runtime.sessions, {})


    async def test_CB002_session_exit_stops_the_same_authenticated_plan_identity(self):
        async with self.running() as (url, tokens, runtime):
            async with Client(url, auth=tokens['mcp']) as client:
                await client.call_tool('agent_prepare', PREPARE)
                prepared = self.events[-1]['params']
            async with asyncio.timeout(3):
                while not runtime.lifecycle_results:
                    await asyncio.sleep(.01)
            self.assertTrue(runtime.lifecycle_results[-1]['unity_confirmed'],
                            'closing SDK context lost the authenticated plan identity')
            stopped = [event['params'] for event in self.events if event['params']['kind'] == 'stop']
            self.assertEqual(len(stopped), 1)
            self.assertEqual(stopped[0]['client_id'], prepared['client_id'])
            self.assertEqual(stopped[0]['plan_id'], prepared['plan_id'] or runtime.lifecycle_results[-1]['plan_id'])

    async def test_CB003_material_and_read_plans_share_only_the_same_verified_session(self):
        async with self.running() as (url, tokens, runtime):
            async with Client(url, auth=tokens['mcp']) as client:
                await client.call_tool('agent_status', {})
                identity = self.events[-1]['params']['client_id']
                result = await client.call_tool('material_prepare', MANIFEST)
                plan = result.data['data']['plan_id']
                self.assertEqual(self.events[-1]['params']['client_id'], identity,
                                 'material approval lost the verified client identity')
                stopped = await client.call_tool('material_stop',
                    {'task_id':MANIFEST['task_id'],'plan_id':plan})
                self.assertTrue(stopped.data['success'])
                self.assertEqual(self.events[-1]['params']['client_id'], identity)
                await client.call_tool('material_prepare', MANIFEST)
            async with asyncio.timeout(3):
                while not runtime.lifecycle_results:
                    await asyncio.sleep(.01)
            self.assertTrue(runtime.lifecycle_results[-1]['unity_confirmed'])
            self.assertEqual(self.events[-1]['params']['client_id'], identity)
            self.assertEqual(runtime.material.history, {})

    async def test_CB004_authentication_failure_registers_no_session_or_callback(self):
        from types import SimpleNamespace
        from contextlib import AsyncExitStack
        from unittest.mock import patch
        from fastmcp.exceptions import ToolError
        from candidate_runtime import Runtime
        runtime = Runtime('fixture-project', authenticated=True)
        session = SimpleNamespace(_exit_stack=AsyncExitStack())
        ctx = SimpleNamespace(session_id='fixture-sdk-session', session=session)
        with patch('fastmcp.server.dependencies.get_access_token', return_value=None):
            with self.assertRaisesRegex(ToolError, 'authenticated_client_required'):
                runtime.bind_session(ctx)
        self.assertEqual(runtime.sessions, {})
        self.assertEqual(len(session._exit_stack._exit_callbacks), 0)

    async def test_CB005_same_sdk_session_cannot_change_signed_principal(self):
        from types import SimpleNamespace
        from contextlib import AsyncExitStack
        from unittest.mock import patch
        from fastmcp.exceptions import ToolError
        from candidate_runtime import Runtime
        class Session: pass
        session = Session()
        session._exit_stack = AsyncExitStack()
        ctx = SimpleNamespace(session_id='fixture-sdk-session', session=session)
        runtime = Runtime('fixture-project', authenticated=True)
        try:
            with patch('fastmcp.server.dependencies.get_access_token',
                       return_value=SimpleNamespace(client_id='fixture-client')):
                identity = runtime.bind_session(ctx)
            with patch('fastmcp.server.dependencies.get_access_token',
                       return_value=SimpleNamespace(client_id='fixture-client-b')):
                with self.assertRaisesRegex(ToolError, 'session_identity_changed'):
                    runtime.bind_session(ctx)
            self.assertEqual(len(session._exit_stack._exit_callbacks), 1)
        finally:
            await session._exit_stack.aclose()
        self.assertEqual(runtime.sessions, {})

    async def test_CB006_two_principals_and_two_sessions_of_one_principal_never_alias(self):
        async with self.running() as (url, tokens, runtime):
            async with Client(url, auth=tokens['mcp']) as a, \
                       Client(url, auth=tokens['mcp-b']) as b, \
                       Client(url, auth=tokens['mcp']) as a2:
                identities = []
                for client,principal in ((a,'fixture-client'),(b,'fixture-client-b'),(a2,'fixture-client')):
                    await client.call_tool('agent_prepare', PREPARE)
                    identity = self.events[-1]['params']['client_id']
                    self.assertEqual(json.loads(identity),[principal,client.transport.get_session_id()])
                    identities.append(identity)
                self.assertEqual(len(set(identities)), 3)
                self.assertEqual(len(runtime.plans), 3)
                before = len(self.events)
                forged = await a.call_tool('agent_prepare', {**PREPARE,'client_id':identities[1]}, raise_on_error=False)
                self.assertTrue(forged.is_error)
                self.assertEqual(len(self.events),before)
                self.assertIn(b.transport.get_session_id(),runtime.plans)
            self.assertEqual(runtime.sessions,{})
            self.assertEqual(runtime.session_identities,{})
            for token in tokens.values():
                self.assertNotIn(token,json.dumps(self.events))

    async def test_CB007_compiled_gates_approve_exact_client_and_stop_without_rollback(self):
        self.use_core = True
        async with self.running() as (url, tokens, runtime):
            async with Client(url, auth=tokens['mcp-b']) as b:
                async with Client(url, auth=tokens['mcp']) as a:
                    pa = (await a.call_tool('agent_prepare', PREPARE)).data['data']
                    pb = (await b.call_tool('agent_prepare', PREPARE)).data['data']
                    plans = (await self.exchange({'fixture_local_plans':True}))['fixture_plans']
                    self.assertEqual(len(plans),2)
                    self.assertEqual({tuple(json.loads(p['client_id'])) for p in plans},
                        {('fixture-client',a.transport.get_session_id()),('fixture-client-b',b.transport.get_session_id())})
                    self.assertTrue((await self.exchange({'fixture_approve_exact':pa}))['fixture_approved'])
                    self.assertTrue((await a.call_tool('manage_material',READ)).data['success'])
                    foreign = await b.call_tool('manage_material',READ,raise_on_error=False)
                    self.assertTrue(foreign.is_error or foreign.data.get('success') is False)
                    # A rejected unapproved read revokes B, not A; prepare/approve B separately.
                    pb = (await b.call_tool('agent_prepare',PREPARE)).data['data']
                    self.assertTrue((await self.exchange({'fixture_approve_exact':pb}))['fixture_approved'])
                    material = {**MANIFEST,'source':'Assets/source.mat','candidate':'Assets/candidate.mat',
                                'operations':['copy','edit'],'references':[]}
                    pm = (await a.call_tool('material_prepare',material)).data['data']
                    route = 'vrchat_agent_material_dispatch'
                    self.assertTrue((await self.exchange({'route':route,'fixture_approve_exact':pm}))['fixture_approved'])
                    for action,arguments in [('copy',{}),('edit',{'property':'_Value','value':.625})]:
                        result = await a.call_tool('material_execute',{'task_id':material['task_id'],
                            'plan_id':pm['plan_id'],'action':action,'arguments':arguments})
                        self.assertTrue(result.data['success'])
                    before = await self.exchange({'fixture_bytes':True})
                    self.assertEqual(before,{'source':'original','candidate':'0.625','writes':2})
                    stolen = await b.call_tool('material_stop',{'task_id':material['task_id'],
                        'plan_id':pm['plan_id']},raise_on_error=False)
                    self.assertTrue(stolen.is_error)
                # A's SDK DELETE stops both exact plans after request authentication is gone.
                async with asyncio.timeout(4):
                    while len(runtime.lifecycle_results)<2: await asyncio.sleep(.01)
                receipts=list(runtime.lifecycle_results)[-2:]
                self.assertTrue(all(r['unity_confirmed'] for r in receipts))
                plans=(await self.exchange({'fixture_local_plans':True}))['fixture_plans']
                self.assertEqual([p['plan_id'] for p in plans],[pb['plan_id']])
                self.assertEqual((await self.exchange({'route':route,'fixture_local_plans':True}))['fixture_plans'],[])
                self.assertEqual(await self.exchange({'fixture_bytes':True}),before,'stop must not roll back')
                self.assertTrue((await b.call_tool('manage_material',READ)).data['success'])
            self.assertEqual(runtime.sessions,{})
            self.assertEqual(runtime.session_identities,{})

if __name__ == '__main__': unittest.main(verbosity=2)
