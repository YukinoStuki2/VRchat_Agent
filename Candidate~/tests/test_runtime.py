"""REAL SDK/factory/handlers/PluginHub; only Unity WebSocket PEER is a fixture.
No Unity execution, local UI approval, evidence or filesystem safety is proved here.
"""
import atexit
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

HOME = tempfile.TemporaryDirectory(prefix="candidate-runtime-test-")
atexit.register(HOME.cleanup)
os.environ.update(HOME=HOME.name, XDG_DATA_HOME=HOME.name,
                  UNITY_MCP_LOG_DIR=HOME.name, UNITY_MCP_DISABLE_TELEMETRY="1",
                  DISABLE_TELEMETRY="1", FASTMCP_CHECK_FOR_UPDATES="off",
                  UNITY_MCP_SKIP_STARTUP_CONNECT="1")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "native/src")]

def no_network(event, args):
    if event == "socket.__new__" and args[1] != socket.AF_UNIX:
        raise PermissionError("RUNTIME FIXTURE: network forbidden")
    if event in {"socket.connect", "socket.bind", "socket.sendto", "socket.sendmsg",
                 "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
        raise PermissionError("RUNTIME FIXTURE: network forbidden")
sys.addaudithook(no_network)

from fastmcp import Client
from transport.plugin_hub import PluginHub
from core.config import config
from starlette.websockets import WebSocketState

PROJECT = "0123456789abcdef0123456789abcdef"
CONNECTION = "fixture-unity-connection-A"
CONTROLLER = "Assets/Fixture.controller"
MATERIAL = "Assets/Fixture.mat"
READ = {"action": "controller_get_info", "controller_path": CONTROLLER}
PREPARE = {"task_id": "fixture-task", "operations": [
    {"command": "manage_animation", "action": "controller_get_info"},
    {"command": "manage_material", "action": "get_material_info"}],
    "targets": [CONTROLLER, MATERIAL], "ttl_seconds": 60}


def create_server():
    if importlib.util.find_spec("candidate_runtime") is not None:
        from candidate_runtime import create_server
        return create_server(PROJECT)
    # RED baseline: actual native factory, NOT a copied handler/server substitute.
    from main import create_mcp_server
    config.transport_mode = "http"
    config.telemetry_enabled = False
    return create_mcp_server(project_scoped_tools=True)


class UnityPeerFixture:
    """Explicit Unity peer substitute only; does not implement real approval."""
    client_state = application_state = WebSocketState.CONNECTED

    def __init__(self):
        self.events = []
        self.approved = False
        self.prepare_success = True
        self.hook = None
        self.sequence = 0

    async def send_json(self, payload):
        self.events.append(payload)
        envelope = payload["params"]
        kind = envelope.get("kind")
        if self.hook:
            await self.hook(payload)
        if kind == "prepare":
            self.sequence += 1
            response = {"success": self.prepare_success, "data": {
                "plan_id": "fixture-plan-" + str(self.sequence), "status": "pending"}}
        elif kind == "execute":
            response = {"success": self.approved, "data": {"fixture_only": True}}
            if not self.approved:
                response["error"] = "fixture_pending_not_approved"
        else:
            response = {"success": True, "data": {"status": "fixture-local-disabled"}}
        # Fixed native dispatcher wraps SuccessResponse/ErrorResponse this way.
        # Original fixture source and assertions preserved in runtime-fix evidence.
        from transport.models import CommandResultMessage
        await PluginHub._handle_command_result(object.__new__(PluginHub),
            CommandResultMessage(id=payload['id'], result={'status': 'success', 'result': response}))

    async def close(self, **kwargs):
        pass


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = create_server()
        self.client = await self.enterAsyncContext(Client(self.server))
        self.peer = UnityPeerFixture()
        await PluginHub._registry.register(CONNECTION, "NOT-UNITY", PROJECT, "FIXTURE")
        PluginHub._connections[CONNECTION] = self.peer

    async def asyncTearDown(self):
        self.assertEqual(PluginHub._pending, {}, "native pending leak")
        for sid in list(await PluginHub._registry.list_sessions()):
            PluginHub._connections.pop(sid, None)
            await PluginHub._registry.unregister(sid)
        self.assertEqual(await PluginHub._registry.list_sessions(), {})
        self.assertEqual(PluginHub._connections, {})

    async def test_RT014_catalog_rejects_unbounded_or_coerced_arguments(self):
        for args in ({'limit':0},{'limit':21},{'limit':True},{'limit':'2'},
                     {'offset':-1},{'offset':1.5},{'offset':True},{'offset':'0'},
                     {'offset':100000},{'path':'/etc/passwd'},{'action':'approve'}):
            with self.subTest(args=args):
                result=await self.client.call_tool('agent_catalog',args,raise_on_error=False)
                self.assertTrue(result.is_error,'invalid paging accepted')
        self.assertEqual(self.peer.events,[])

    async def test_RT013_catalog_is_complete_paginated_and_inert(self):
        await PluginHub._registry.unregister(CONNECTION)
        PluginHub._connections.pop(CONNECTION)
        rows=[]
        offset=0
        while True:
            result=await self.client.call_tool('agent_catalog', {'offset':offset,'limit':11}, raise_on_error=False)
            self.assertFalse(result.is_error, 'candidate catalog missing')
            data=result.data
            self.assertIs(data['permission_grant'], False)
            self.assertIs(data['product_ready'], False)
            self.assertEqual(data['offset'],offset)
            self.assertEqual(data['returned'],len(data['tools']))
            rows.extend(data['tools'])
            if data['next_offset'] is None:break
            self.assertEqual(data['next_offset'],offset+len(data['tools']))
            offset=data['next_offset']
        expected=json.loads((ROOT/'catalog/native-inventory.json').read_text(encoding='utf-8'))
        self.assertEqual(data['total'],len(rows))
        self.assertEqual([x['name'] for x in rows],[x['name'] for x in expected['tools']])
        self.assertEqual(len(rows),len({x['name'] for x in rows}))
        self.assertTrue(all(x['enabled_by_catalog'] is False and x['default_decision']=='deny' for x in rows))
        self.assertEqual(self.peer.events,[])
        self.assertEqual(self.server._candidate_runtime.plans,{})
        self.assertEqual(self.server._candidate_runtime.material.plans,{})

    async def test_RT001_status_traverses_real_sdk_factory_hub(self):
        result = await self.client.call_tool("agent_status", {}, raise_on_error=False)
        self.assertFalse(result.is_error, "agent_status missing in real candidate")
        self.assertTrue(result.data["success"])
        wire = self.peer.events[0]
        self.assertEqual(wire["name"], "vrchat_agent_dispatch")
        self.assertEqual(set(wire["params"]), {"protocol", "kind", "project_id", "client_id",
                                             "connection_id", "task_id", "plan_id", "body"})
        self.assertEqual(wire["params"]["protocol"], 1)
        self.assertEqual(wire["params"]["kind"], "status")
        self.assertEqual(wire["params"]["body"], {})
        self.assertEqual(wire["params"]["project_id"], PROJECT)
        self.assertEqual(wire["params"]["connection_id"], CONNECTION)
        self.assertTrue(wire["params"]["client_id"])
        self.assertEqual(wire["params"]["task_id"], "")
        self.assertEqual(wire["params"]["plan_id"], "")


    async def test_RT002_prepare_pending_read_and_stop_follow_native_path(self):
        prepared = await self.client.call_tool('agent_prepare', PREPARE, raise_on_error=False)
        self.assertFalse(prepared.is_error, 'agent_prepare is missing')
        self.assertEqual(prepared.data['data']['status'], 'pending')
        denied = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertFalse(denied.data['success'], 'pending does not auto approve')
        # Any native refusal/failure closes mapping. Explicit new fixture plan
        # is now required, matching contract; RT012 verifies no silent reuse.
        prepared = await self.client.call_tool('agent_prepare', PREPARE)
        self.peer.approved = True  # Explicit peer fixture, never runtime approval.
        result = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertTrue(result.data['success'])
        wire = self.peer.events[-1]
        self.assertEqual(wire['name'], 'vrchat_agent_dispatch')
        self.assertEqual(wire['params']['plan_id'], prepared.data['data']['plan_id'])
        self.assertEqual(wire['params']['body'], {'command': 'manage_animation',
                        'params': {'action': 'controller_get_info', 'controllerPath': CONTROLLER}})
        stopped = await self.client.call_tool('agent_stop', {'task_id': 'fixture-task'}, raise_on_error=False)
        self.assertTrue(stopped.data['success'])
        before = len(self.peer.events)
        again = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertTrue(again.is_error)
        self.assertEqual(len(self.peer.events), before)


    async def test_RT003_bool_ttl_is_not_coerced_to_one_second(self):
        before = len(self.peer.events)
        result = await self.client.call_tool('agent_prepare', {**PREPARE, 'ttl_seconds': True}, raise_on_error=False)
        self.assertTrue(result.is_error)
        self.assertEqual(len(self.peer.events), before)

    async def test_RT004_stop_during_final_prepare_check_does_not_restore_plan(self):
        from unittest.mock import patch
        entered, release = asyncio.Event(), asyncio.Event()
        original = PluginHub._registry.list_sessions

        async def pause_after_unity_prepare():
            sessions = await original()
            if self.peer.events and self.peer.events[-1]['params']['kind'] == 'prepare':
                entered.set()
                await release.wait()
            return sessions

        with patch.object(PluginHub._registry, 'list_sessions', pause_after_unity_prepare):
            pending = asyncio.create_task(self.client.call_tool('agent_prepare', PREPARE, raise_on_error=False))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                stopped = await self.client.call_tool('agent_stop', {'task_id': 'fixture-task'}, raise_on_error=False)
                self.assertTrue(stopped.data['success'])
            finally:
                release.set()
            prepared = await pending
        self.assertTrue(prepared.is_error, 'stop during final await must invalidate prepare')
        before = len(self.peer.events)
        read = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertTrue(read.is_error)
        self.assertEqual(len(self.peer.events), before)


    async def test_RT005_rejected_replacement_cannot_keep_old_plan(self):
        await self.client.call_tool('agent_prepare', PREPARE)
        bad = await self.client.call_tool('agent_prepare', {**PREPARE, 'ttl_seconds': True}, raise_on_error=False)
        self.assertTrue(bad.is_error)
        before = len(self.peer.events)
        read = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertTrue(read.is_error)
        self.assertEqual(len(self.peer.events), before)

    async def test_RT006_stop_while_prepare_waits_for_initial_connection(self):
        from unittest.mock import patch
        entered, release = asyncio.Event(), asyncio.Event()
        original = PluginHub._registry.list_sessions
        async def pause_initial():
            sessions = await original()
            entered.set()
            await release.wait()
            return sessions
        with patch.object(PluginHub._registry, 'list_sessions', pause_initial):
            pending = asyncio.create_task(self.client.call_tool('agent_prepare', PREPARE, raise_on_error=False))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                stopped = await self.client.call_tool('agent_stop', {'task_id': 'fixture-task'}, raise_on_error=False)
                self.assertTrue(stopped.data['success'])
            finally:
                release.set()
            prepared = await pending
        self.assertTrue(prepared.is_error)
        self.assertEqual(self.peer.events, [], 'stopped prepare must not reach Unity')

    async def test_RT007_surface_and_unmanaged_paths_are_closed(self):
        names = {t.name for t in await self.client.list_tools()}
        self.assertEqual(names, {'agent_status', 'agent_catalog', 'agent_prepare', 'agent_stop', 'manage_animation', 'manage_material',
            'material_prepare', 'material_execute', 'material_status', 'material_stop'})
        for name, args in [('agent_approve', {}), ('execute_custom_tool', {}),
                           ('manage_animation', {**READ, 'client_id': 'fake'}),
                           ('manage_animation', {**READ, 'action': 'controller_create'}),
                           ('agent_status', {'approved': True})]:
            with self.subTest(name=name, args=args):
                result = await self.client.call_tool(name, args, raise_on_error=False)
                self.assertTrue(result.is_error)
        with self.assertRaises(Exception):
            await PluginHub.send_command(CONNECTION, 'manage_animation', {'action': 'controller_get_info'})
        self.assertEqual(self.peer.events, [])
        self.assertEqual(PluginHub._pending, {})

    async def test_RT008_fresh_client_cannot_inherit_and_material_handler_is_native(self):
        material = 'Assets/Avatar/Read.mat'
        await self.client.call_tool('agent_prepare', {**PREPARE,
            'operations': [{'command': 'manage_material', 'action': 'get_material_info'}], 'targets': [material]})
        self.peer.approved = True
        async with Client(self.server) as other:
            denied = await other.call_tool('manage_material', {'action': 'get_material_info', 'material_path': material}, raise_on_error=False)
            self.assertTrue(denied.is_error)
        result = await self.client.call_tool('manage_material', {'action': 'get_material_info', 'material_path': material})
        self.assertTrue(result.data['success'])
        self.assertEqual(self.peer.events[-1]['params']['body'], {'command': 'manage_material',
            'params': {'action': 'get_material_info', 'materialPath': material}})

    async def test_RT009_reconnect_cannot_reuse_old_plan(self):
        await self.client.call_tool('agent_prepare', PREPARE)
        PluginHub._connections.pop(CONNECTION)
        await PluginHub._registry.unregister(CONNECTION)
        await PluginHub._registry.register('fixture-connection-B', 'NOT-UNITY', PROJECT, 'FIXTURE')
        PluginHub._connections['fixture-connection-B'] = self.peer
        before = len(self.peer.events)
        result = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertTrue(result.is_error or result.data['success'] is False)
        self.assertEqual(len(self.peer.events), before)
        self.assertEqual(PluginHub._pending, {})


    async def test_RT010_http_app_has_no_raw_rest_route(self):
        import httpx
        runtime = importlib.import_module('candidate_runtime')
        self.assertTrue(hasattr(runtime, 'create_app'), 'missing real HTTP entry')
        app = runtime.create_app(self.server)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
            for path in ('/api/command', '/api/tools', '/execute', '/approve'):
                response = await client.post(path, json={'command': 'manage_animation'})
                self.assertEqual(response.status_code, 404, path)
        paths = [getattr(r, 'path', None) for r in app.routes]
        self.assertIn('/hub', paths)
        self.assertIn('/mcp', paths)


    async def test_RT012_native_error_invalidates_current_mapping(self):
        await self.client.call_tool('agent_prepare', PREPARE)
        async def fail_execute(payload):
            if payload['params']['kind'] == 'execute':
                self.peer.approved = False
        self.peer.hook = fail_execute
        failure = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertFalse(failure.data['success'])
        before = len(self.peer.events)
        again = await self.client.call_tool('manage_animation', READ, raise_on_error=False)
        self.assertTrue(again.is_error, 'native failure must require a new plan')
        self.assertEqual(len(self.peer.events), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
