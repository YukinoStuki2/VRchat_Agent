"""Real SDK/loopback abandonment. Only Unity responder is a labelled fixture."""
import asyncio
import json
from unittest.mock import patch

import httpx
import test_runtime_lifecycle as fixtures


class IdleTests(fixtures.LifecycleHarness):
    async def post(self, http, method, params=None, identity: int | None=1):
        body = {'jsonrpc': '2.0', 'method': method}
        if identity is not None:
            body['id'] = identity
        if params is not None:
            body['params'] = params
        response = await http.post(self.url, json=body)
        self.assertNotEqual(response.status_code, 429, '429: stop without retry')
        return response

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:300])
        if response.headers.get('content-type', '').startswith('application/json'):
            return response.json()['result']
        messages = [json.loads(line[6:]) for line in response.text.splitlines()
                    if line.startswith('data: ')]
        self.assertEqual(len(messages), 1)
        return messages[0]['result']

    async def initialize(self, http):
        response = await self.post(http, 'initialize', {'protocolVersion': '2025-03-26',
            'capabilities': {}, 'clientInfo': {'name': 'NOT-A-REAL-CLIENT', 'version': 'fixture'}})
        self.result(response)
        sid = response.headers['mcp-session-id']
        http.headers['mcp-session-id'] = sid
        http.headers['mcp-protocol-version'] = '2025-03-26'
        self.assertEqual((await self.post(http, 'notifications/initialized', identity=None)).status_code, 202)
        return sid

    async def test_IDLE003_ping_keeps_session_not_task_authorization(self):
        with patch('candidate_runtime.SESSION_IDLE_TIMEOUT', .3, create=True):
            async with self.running():
                async with httpx.AsyncClient(trust_env=False, timeout=3,
                        headers={'Accept': 'application/json, text/event-stream'}) as http:
                    sid = await self.initialize(http)
                    prepared = self.result(await self.post(http, 'tools/call',
                        {'name': 'agent_prepare', 'arguments': {**fixtures.PREPARE, 'ttl_seconds': .4}}, 2))
                    plan_id = prepared['structuredContent']['data']['plan_id']
                    for counter in range(7):
                        await asyncio.sleep(.1)
                        self.result(await self.post(http, 'ping', identity=counter+3))
                    self.assertIn(sid, self.runtime.sessions)
                    denied = self.result(await self.post(http, 'tools/call',
                        {'name': 'manage_material', 'arguments': fixtures.READ}, 20))
                    self.assertTrue(denied['isError'])
                    self.assertIn('plan_not_current', str(denied))
                    self.assertNotIn(sid, self.runtime.plans)
                    await self.wait_for_stop(plan_id)
                    self.assertEqual((await http.delete(self.url)).status_code, 200)

    async def test_DCON002_same_project_reconnect_does_not_inherit_grant(self):
        import websockets
        async with self.running():
            async with httpx.AsyncClient(trust_env=False, timeout=3,
                    headers={'Accept': 'application/json, text/event-stream'}) as http:
                sid = await self.initialize(http)
                self.result(await self.post(http, 'tools/call',
                    {'name': 'agent_prepare', 'arguments': fixtures.PREPARE}, 2))
                url = self.url.replace('http:', 'ws:').removesuffix('/mcp') + '/hub/plugin'
                async with websockets.connect(url, proxy=None) as replacement:
                    self.assertEqual(json.loads(await replacement.recv())['type'], 'welcome')
                    await replacement.send(json.dumps({'type': 'register',
                        'project_name': 'NOT-UNITY-Replacement', 'project_hash': fixtures.PROJECT,
                        'unity_version': 'FIXTURE'}))
                    new_sid = json.loads(await replacement.recv())['session_id']
                    self.assertNotEqual(new_sid, self.connection_id)
                    deadline = asyncio.get_running_loop().time() + 1
                    while sid in self.runtime.plans and asyncio.get_running_loop().time() < deadline:
                        await asyncio.sleep(.02)
                    self.assertNotIn(sid, self.runtime.plans,
                        'native eviction left the prior connection plan current')
                    self.assertEqual((await http.delete(self.url)).status_code, 200)

    async def test_DCON001_lost_unity_socket_revokes_bound_plans_immediately(self):
        from transport.plugin_hub import PluginHub
        async with self.running():
            async with httpx.AsyncClient(trust_env=False, timeout=3,
                    headers={'Accept': 'application/json, text/event-stream'}) as http:
                sid = await self.initialize(http)
                self.result(await self.post(http, 'tools/call',
                    {'name': 'agent_prepare', 'arguments': fixtures.PREPARE}, 2))
                await PluginHub._connections[self.connection_id].close(code=1001)
                deadline = asyncio.get_running_loop().time() + 1
                while sid in self.runtime.plans and asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(.02)
                self.assertNotIn(sid, self.runtime.plans,
                    'Unity disconnect retained local plan until unrelated SDK timeout')
                receipt = list(self.runtime.lifecycle_results)[-1]
                self.assertTrue(receipt['local_revoked'])
                self.assertFalse(receipt['unity_confirmed'])
                self.assertEqual(receipt['reason'], 'unity_connection_closed')
                self.assertEqual((await http.delete(self.url)).status_code, 200)

    async def test_IDLE002_expiry_during_read_stops_exact_unity_plan(self):
        with patch('candidate_runtime.SESSION_IDLE_TIMEOUT', .3, create=True):
            async with self.running():
                async with httpx.AsyncClient(trust_env=False, timeout=3,
                        headers={'Accept': 'application/json, text/event-stream'}) as http:
                    sid = await self.initialize(http)
                    prepared = self.result(await self.post(http, 'tools/call',
                        {'name': 'agent_prepare', 'arguments': fixtures.PREPARE}, 2))
                    plan_id = prepared['structuredContent']['data']['plan_id']
                    self.hold_kind = 'execute'
                    self.release.clear()
                    pending = asyncio.create_task(self.post(http, 'tools/call',
                        {'name': 'manage_material', 'arguments': fixtures.READ}, 3))
                    try:
                        await asyncio.wait_for(self.entered.wait(), 1)
                        # Keep native execution outstanding past SDK inactivity.
                        await asyncio.sleep(.5)
                        self.assertNotIn(sid, self.runtime.plans)
                        self.release.set()
                        try:
                            stops = await self.wait_for_stop(plan_id, 2)
                        except TimeoutError:
                            self.fail('idle cancellation dropped plan before precise Unity stop')
                        self.assertEqual(len(stops), 1)
                        self.assertEqual(stops[0]['params']['client_id'], sid)
                    finally:
                        self.release.set()
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)

    async def test_IDLE001_abandoned_session_is_revoked_without_delete(self):
        # Only shorten the SDK policy deadline, not its clock or transport.
        with patch('candidate_runtime.SESSION_IDLE_TIMEOUT', .3, create=True):
            async with self.running():
                async with httpx.AsyncClient(trust_env=False, timeout=3,
                        headers={'Accept': 'application/json, text/event-stream'}) as http:
                    sid = await self.initialize(http)
                    prepared = self.result(await self.post(http, 'tools/call',
                        {'name': 'agent_prepare', 'arguments': fixtures.PREPARE}, 2))
                    self.assertFalse(prepared.get('isError', False))
                    plan_id = prepared['structuredContent']['data']['plan_id']
                    self.assertIn(sid, self.runtime.plans)
                    # No DELETE, GET retry, or further traffic until deadline.
                    deadline = asyncio.get_running_loop().time() + 2
                    while sid in self.runtime.plans and asyncio.get_running_loop().time() < deadline:
                        await asyncio.sleep(.02)
                    self.assertNotIn(sid, self.runtime.plans,
                        'abandoned SDK session retained its local authorization')
                    stops = await self.wait_for_stop(plan_id)
                    self.assertEqual(len(stops), 1)
                    self.assertEqual(stops[0]['params']['client_id'], sid)
                    self.assertNotIn(sid, self.runtime.sessions)
                    # SDK, not our own fake session table, rejects the old identity.
                    self.assertEqual((await self.post(http, 'ping', identity=3)).status_code, 404)
