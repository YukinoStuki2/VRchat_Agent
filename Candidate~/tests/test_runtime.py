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
    # Windows asyncio uses socket.socketpair's IPv4 loopback implementation.
    # Permit only events originating in that exact stdlib function, not arbitrary
    # loopback clients. No production code is exempt and DNS remains forbidden.
    if sys.platform == "win32" and event in {"socket.__new__", "socket.bind", "socket.connect"}:
        caller = sys._getframe(1)
        plumbing = {socket.socket.__init__.__code__, socket.socket.accept.__code__}
        while caller is not None and caller.f_code in plumbing:
            caller = caller.f_back
        if caller is not None and caller.f_code is socket.socketpair.__code__:
            if event == "socket.__new__" and args[1] == socket.AF_INET:
                return
            if event in {"socket.bind", "socket.connect"} and args[1][0] == "127.0.0.1":
                return
    if event == "socket.__new__" and args[1] != getattr(socket, "AF_UNIX", None):
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
        self.execute_data = {"fixture_only": True}
        self.execute_response = None

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
            response = {"success": self.approved, "data": self.execute_data}
            if self.execute_response is not None: response = self.execute_response
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


class NetworkGuardTests(unittest.TestCase):
    def test_RT018_stdlib_socketpair_only_no_inet_or_dns(self):
        left, right = socket.socketpair()
        try:
            left.sendall(b"self-pipe")
            self.assertEqual(right.recv(16), b"self-pipe")
        finally:
            left.close()
            right.close()
        for family in (socket.AF_INET, socket.AF_INET6):
            with self.assertRaises(PermissionError):
                socket.socket(family, socket.SOCK_STREAM)
        with self.assertRaises(PermissionError):
            socket.getaddrinfo("example.invalid", 443)
        for address in (("127.0.0.1", 80), ("203.0.113.1", 443)):
            for event in ("socket.connect", "socket.bind", "socket.sendto"):
                with self.assertRaises(PermissionError):
                    no_network(event, (None, address))


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

    async def test_RT020_scene_rejects_mutations_coercion_and_scope_inheritance(self):
        prepare = {'task_id':'scene-task','operations':[{'command':'manage_scene','action':'get_active'}],
                   'targets':['Scenes'],'ttl_seconds':60}
        for args in ({'action':'save'}, {'action':'load'}, {'action':'create'}, {'action':'validate'},
                     {'action':'get_hierarchy'}, {'action':'scene_view_frame'}, {'action':'GET_ACTIVE'},
                     {'action':'get_active '}, {'action':True}, {'action':'get_active','path':'Assets/Else.unity'},
                     {'action':'get_active','auto_repair':False}, {'action':'get_active','cursor':0},
                     {'action':'get_loaded_scenes'}):
            await self.client.call_tool('agent_prepare', prepare)
            self.peer.approved=True
            before=len([e for e in self.peer.events if e['params']['kind']=='execute'])
            result=await self.client.call_tool('manage_scene',args,raise_on_error=False)
            self.assertTrue(result.is_error, repr(args))
            self.assertEqual(before,len([e for e in self.peer.events if e['params']['kind']=='execute']))
        for target in ('scenes','Scenes/Other','Assets/Fixture.unity','Console'):
            bad=await self.client.call_tool('agent_prepare',{**prepare,'targets':[target]},raise_on_error=False)
            self.assertTrue(bad.is_error)
        await self.client.call_tool('agent_prepare',PREPARE)
        self.assertTrue((await self.client.call_tool('manage_scene',{'action':'get_active'},raise_on_error=False)).is_error)
        await self.client.call_tool('agent_prepare',prepare)
        async with Client(self.server) as other:
            self.assertTrue((await other.call_tool('manage_scene',{'action':'get_active'},raise_on_error=False)).is_error)

    async def test_RT021_scene_preflight_never_queries_ungranted_state_or_refresh(self):
        from candidate_runtime import scene_read_preflight
        from fastmcp.exceptions import ToolError
        from unittest.mock import patch, AsyncMock
        with self.assertRaises(ToolError):
            await scene_read_preflight(None)
        await self.client.call_tool('agent_prepare',{'task_id':'scene-task',
            'operations':[{'command':'manage_scene','action':'get_active'}],'targets':['Scenes'],'ttl_seconds':60})
        self.peer.approved=True
        with patch('services.resources.editor_state.get_editor_state',new=AsyncMock()) as state, \
             patch('services.tools.refresh_unity.refresh_unity',new=AsyncMock()) as refresh:
            result=await self.client.call_tool('manage_scene',{'action':'get_active'})
            self.assertTrue(result.data['success'])
            state.assert_not_awaited()
            refresh.assert_not_awaited()

    async def test_RT035_package_info_native_only_no_upm_or_aliases(self):
        from services.tools.manage_packages import manage_packages
        prepare={'task_id':'package-metadata','operations':[{'command':'manage_packages','action':'get_package_info'}],'targets':['ProjectMetadata'],'ttl_seconds':60}
        args={'action':'get_package_info','package':'com.unity.ugui'}
        result=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
        self.assertFalse(result.is_error,'installed-package operation missing')
        self.assertIs((await self.server.get_tool('manage_packages')).fn,manage_packages)
        self.peer.approved=True
        result=await self.client.call_tool('manage_packages',args)
        self.assertTrue(result.structured_content['success'])
        self.assertEqual(self.peer.events[-1]['params']['body'],{'command':'manage_packages','params':args})
        for bad in ({'action':a,'package':'com.unity.ugui'} for a in ('list_packages','search_packages','status','ping','add_package','remove_package','resolve_packages','embed_package','list_registries','add_registry','remove_registry','GET_PACKAGE_INFO')):
            await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
            before=sum(e['params']['kind']=='execute' for e in self.peer.events)
            self.assertTrue((await self.client.call_tool('manage_packages',bad,raise_on_error=False)).is_error)
            self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)
        for bad in ({**args,'force':False},{**args,'query':None},{'action':'get_package_info'},*({**args,'package':p} for p in ('com.unity.ugui@1.0.0','https://example.invalid/pkg','file:../pkg','COM.unity.ugui',' com.unity.ugui','com..ugui','com.unity/ugui','x'*215,None,True))):
            await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
            before=sum(e['params']['kind']=='execute' for e in self.peer.events)
            self.assertTrue((await self.client.call_tool('manage_packages',bad,raise_on_error=False)).is_error)
            self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)
        for target in ('Scenes','EditorMetadata','Console',CONTROLLER):
            self.assertTrue((await self.client.call_tool('agent_prepare',{**prepare,'targets':[target]},raise_on_error=False)).is_error)
        await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
        self.peer.execute_response={'success':False,'error':'plan_paused','data':{'status':'paused','reason':'plan_paused','plan_id':'fixture-plan-'+str(self.peer.sequence)}}
        paused=await self.client.call_tool('manage_packages',args,raise_on_error=False)
        self.assertTrue(paused.is_error)
        self.assertEqual(paused.structured_content['error'],'plan_paused')
        self.peer.execute_response=None
        self.assertTrue((await self.client.call_tool('manage_packages',args)).structured_content['success'])
        await self.client.call_tool('agent_stop',{'task_id':'package-metadata'})
        self.assertTrue((await self.client.call_tool('manage_packages',args,raise_on_error=False)).is_error)

    async def test_RT034_menu_metadata_native_refresh_is_not_asset_refresh(self):
        from services.resources.menu_items import get_menu_items
        prepare={'task_id':'menu-metadata','operations':[{'command':'get_menu_items','action':'read'}],'targets':['EditorMetadata'],'ttl_seconds':60}
        result=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
        self.assertFalse(result.is_error,'menu metadata operation missing')
        self.assertIs((await self.server.get_tool('get_menu_items')).fn,get_menu_items)
        self.peer.approved=True;self.peer.execute_data=['Assets/Create','Tools/Fixture']
        result=await self.client.call_tool('get_menu_items',{})
        self.assertEqual(result.structured_content['result']['data'],self.peer.execute_data)
        self.assertEqual(self.peer.events[-1]['params']['body'],{'command':'get_menu_items','params':{'refresh':True,'search':''}})
        for bad in ({'refresh':True},{'search':'Assets'},{'action':'read'},{'execute':'Tools/Fixture'}):
            await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
            before=sum(e['params']['kind']=='execute' for e in self.peer.events)
            self.assertTrue((await self.client.call_tool('get_menu_items',bad,raise_on_error=False)).is_error)
            self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)
        for target in ('ProjectMetadata','Scenes','Console',CONTROLLER):
            self.assertTrue((await self.client.call_tool('agent_prepare',{**prepare,'targets':[target]},raise_on_error=False)).is_error)
        await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
        self.peer.execute_response={'success':False,'error':'plan_paused','data':{'status':'paused','reason':'plan_paused','plan_id':'fixture-plan-'+str(self.peer.sequence)}}
        before=sum(e['params']['kind']=='stop' for e in self.peer.events)
        self.assertTrue((await self.client.call_tool('get_menu_items',{},raise_on_error=False)).is_error)
        self.assertEqual(sum(e['params']['kind']=='stop' for e in self.peer.events),before)
        self.peer.execute_response=None
        self.assertTrue((await self.client.call_tool('get_menu_items',{})).structured_content['result']['success'])
        await self.client.call_tool('agent_stop',{'task_id':'menu-metadata'})
        self.assertTrue((await self.client.call_tool('get_menu_items',{},raise_on_error=False)).is_error)

    async def test_RT033_editor_metadata_native_facades_and_scope(self):
        from services.resources.selection import get_selection
        from services.resources.windows import get_windows
        from services.resources.active_tool import get_active_tool
        from services.resources.prefab_stage import get_prefab_stage
        rows=[('get_selection',get_selection,{'activeObject':None,'activeGameObject':None,'activeTransform':None,'activeInstanceID':0,'count':0,'objects':[],'gameObjects':[],'assetGUIDs':[]}),
              ('get_windows',get_windows,[]),
              ('get_active_tool',get_active_tool,{'activeTool':'Move','isCustom':False,'pivotMode':'Center','pivotRotation':'Global','handleRotation':{'x':0.0,'y':0.0,'z':0.0},'handlePosition':{'x':0.0,'y':0.0,'z':0.0}}),
              ('get_prefab_stage',get_prefab_stage,{'isOpen':False,'assetPath':None,'prefabRootName':None,'mode':None,'isDirty':False})]
        for name,reader,data in rows:
            prepare={'task_id':'editor-metadata','operations':[{'command':name,'action':'read'}],'targets':['EditorMetadata'],'ttl_seconds':60}
            prepared=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
            self.assertFalse(prepared.is_error,'editor metadata missing')
            self.assertIs((await self.server.get_tool(name)).fn,reader)
            self.peer.approved=True;self.peer.execute_data=data
            result=await self.client.call_tool(name,{})
            self.assertEqual(result.structured_content['result']['data'],data)
            self.assertEqual(self.peer.events[-1]['params']['body'],{'command':name,'params':{}})
            for target in ('ProjectMetadata','Scenes','Console',CONTROLLER,'EditorMetadata/'):
                self.assertTrue((await self.client.call_tool('agent_prepare',{**prepare,'targets':[target]},raise_on_error=False)).is_error)
            for bad in ({'refresh':True},{'action':'read'},{'path':'Assets/Other.prefab'},{'select':True}):
                await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
                before=sum(e['params']['kind']=='execute' for e in self.peer.events)
                self.assertTrue((await self.client.call_tool(name,bad,raise_on_error=False)).is_error)
                self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)
            await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
            self.peer.execute_response={'success':False,'error':'plan_paused','data':{'status':'paused','reason':'plan_paused','plan_id':'fixture-plan-'+str(self.peer.sequence)}}
            before=sum(e['params']['kind']=='stop' for e in self.peer.events)
            self.assertTrue((await self.client.call_tool(name,{},raise_on_error=False)).is_error)
            self.assertEqual(sum(e['params']['kind']=='stop' for e in self.peer.events),before)
            self.peer.execute_response=None
            self.assertTrue((await self.client.call_tool(name,{})).structured_content['result']['success'])
            await self.client.call_tool('agent_stop',{'task_id':'editor-metadata'})
            self.assertTrue((await self.client.call_tool(name,{},raise_on_error=False)).is_error)

    async def test_RT032_project_resource_pause_receipt_survives_typed_error(self):
        prepare={'task_id':'metadata-pause','operations':[{'command':'get_tags','action':'read'}],
                 'targets':['ProjectMetadata'],'ttl_seconds':60}
        await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
        self.peer.execute_data=['Untagged']
        response={'success':False,'error':'plan_paused','data':{'status':'paused','reason':'plan_paused','plan_id':'fixture-plan-1'}}
        self.peer.execute_response=response
        paused=await self.client.call_tool('get_tags',{},raise_on_error=False)
        self.assertTrue(paused.is_error,'typed resource pause must remain a rejected call')
        self.assertFalse(any(e['params']['kind']=='stop' for e in self.peer.events),'valid pause must not revoke')
        self.peer.execute_response=None
        good=await self.client.call_tool('get_tags',{})
        self.assertTrue(good.structured_content['result']['success'])
        self.peer.execute_response={**response,'data':{**response['data'],'plan_id':'foreign-plan'}}
        await self.client.call_tool('get_tags',{},raise_on_error=False)
        self.assertTrue(any(e['params']['kind']=='stop' for e in self.peer.events),'invalid pause must revoke')
        self.peer.execute_response=None
        self.assertTrue((await self.client.call_tool('get_tags',{},raise_on_error=False)).is_error)

    async def test_RT031_project_metadata_native_facades_scoped_no_args(self):
        from services.resources.project_info import get_project_info
        from services.resources.tags import get_tags
        from services.resources.layers import get_layers
        rows=[('get_project_info',get_project_info,{'projectRoot':'/Fixture','projectName':'Fixture','unityVersion':'2022.3','platform':'StandaloneWindows64','assetsPath':'/Fixture/Assets'}),
              ('get_tags',get_tags,['Untagged','Player']),('get_layers',get_layers,{'0':'Default','5':'UI'})]
        for name,native,data in rows:
            prepare={'task_id':'metadata-task','operations':[{'command':name,'action':'read'}],
                     'targets':['ProjectMetadata'],'ttl_seconds':60}
            prepared=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
            self.assertFalse(prepared.is_error,'metadata not admitted')
            self.assertIs((await self.server.get_tool(name)).fn,native)
            self.peer.execute_data=data;self.peer.approved=True
            result=await self.client.call_tool(name,{})
            self.assertEqual(set(result.structured_content),{'result'})
            payload=result.structured_content['result']
            self.assertTrue(payload['success'])
            self.assertEqual(payload['data'],data)
            self.assertEqual(self.peer.events[-1]['params']['body'],{'command':name,'params':{}})
            for bad in ({'action':'read'},{'refresh':True},{'path':'Assets'},{'approved':True}):
                await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
                before=sum(e['params']['kind']=='execute' for e in self.peer.events)
                self.assertTrue((await self.client.call_tool(name,bad,raise_on_error=False)).is_error)
                self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)
            for target in ('Scenes','Console',CONTROLLER,'ProjectMetadata/','EditorMetadata'):
                self.assertTrue((await self.client.call_tool('agent_prepare',{**prepare,'targets':[target]},raise_on_error=False)).is_error)
            await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
            await self.client.call_tool('agent_stop',{'task_id':'metadata-task'})
            self.assertTrue((await self.client.call_tool(name,{},raise_on_error=False)).is_error)
        self.assertEqual(await self.client.list_resources(),[])
        self.assertEqual(await self.client.list_resource_templates(),[])

    async def test_RT030_animator_exact_native_read_and_denials(self):
        from services.tools.manage_animation import manage_animation
        for action in ('animator_get_info','animator_get_parameter'):
            args={'action':action,'target':'11','search_method':'by_id'}
            if action=='animator_get_parameter':args['properties']={'parameter_name':'Speed'}
            prepare={'task_id':'animator-task','operations':[{'command':'manage_animation','action':action}],
                     'targets':['Scenes'],'ttl_seconds':60}
            prepared=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
            self.assertFalse(prepared.is_error,'animator read missing')
            self.assertIs((await self.server.get_tool('manage_animation')).fn,manage_animation)
            self.peer.approved=True
            result=await self.client.call_tool('manage_animation',args)
            self.assertTrue(result.structured_content['success'])
            wire={'action':action,'target':'11','searchMethod':'by_id'}
            if 'properties' in args:wire['properties']=args['properties']
            self.assertEqual(self.peer.events[-1]['params']['body'],{'command':'manage_animation','params':wire})
            await self.client.call_tool('agent_stop',{'task_id':'animator-task'})
            self.assertTrue((await self.client.call_tool('manage_animation',args,raise_on_error=False)).is_error)
            bad=[{**args,'target':v} for v in (11,True,'0','-1','011','+11','2147483648','Assets/a.prefab','Root')]
            bad += [{**args,'search_method':'by_name'},{**args,'controller_path':CONTROLLER},{**args,'action':'animator_play'}]
            bad += [{**args,'properties':v} for v in ({'parameterName':'Speed'},'{"parameter_name":"Speed"}',{'parameter_name':'Speed','value':1},None,{'parameter_name':''})]
            if action=='animator_get_info':bad.append({**args,'properties':{'parameter_name':'Speed'}})
            for params in bad:
                await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
                before=sum(e['params']['kind']=='execute' for e in self.peer.events)
                self.assertTrue((await self.client.call_tool('manage_animation',params,raise_on_error=False)).is_error,repr(params))
                self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)
            await self.client.call_tool('agent_prepare',PREPARE);self.peer.approved=True
            self.assertTrue((await self.client.call_tool('manage_animation',args,raise_on_error=False)).is_error)

    async def test_RT028_native_object_resource_facades_exact_wire(self):
        from services.resources.gameobject import get_gameobject, get_gameobject_components
        rows=[('get_gameobject',get_gameobject,{'instance_id':'11'},{'instanceID':11}),
              ('get_gameobject_components',get_gameobject_components,
               {'instance_id':'11','page_size':2,'include_properties':False},
               {'instanceID':11,'pageSize':2,'cursor':0,'includeProperties':False})]
        for name,native,args,wire in rows:
            with self.subTest(name=name):
                prepare={'task_id':'object-task','operations':[{'command':name,'action':'read'}],
                         'targets':['Scenes'],'ttl_seconds':60}
                prepared=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
                self.assertFalse(prepared.is_error,'native object operation missing')
                tool=await self.server.get_tool(name)
                self.assertIs(tool.fn,native,'must reuse native resource coroutine, not a new reader')
                self.peer.approved=True
                result=await self.client.call_tool(name,args)
                self.assertTrue(result.structured_content['success'])
                self.assertEqual(self.peer.events[-1]['params']['body'],{'command':name,'params':wire})
                await self.client.call_tool('agent_stop',{'task_id':'object-task'})
                self.assertTrue((await self.client.call_tool(name,args,raise_on_error=False)).is_error)

    async def test_RT029_object_facades_reject_properties_coercion_and_scope(self):
        rows=[('get_gameobject',{'instance_id':'11'}),
              ('get_gameobject_components',{'instance_id':'11','page_size':2,'include_properties':False})]
        for name,args in rows:
            prepare={'task_id':'object-task','operations':[{'command':name,'action':'read'}],
                     'targets':['Scenes'],'ttl_seconds':60}
            bad=[{**args,'instance_id':v} for v in (11,True,None,'0','-1','+11','011','11.0','2147483648','11 ','Assets/a.prefab')]
            bad += [{**args,'id':11},{**args,'action':'read'},{**args,'component_name':'Camera'}]
            bad += [{k:v for k,v in args.items() if k!=key} for key in args]
            if name.endswith('_components'):
                bad += [{**args,'include_properties':v} for v in (True,0,'false',None)]
                bad += [{**args,'page_size':v} for v in (0,101,True,2.0,'2')]
                bad += [{**args,'cursor':v} for v in (-1,1000001,True,0.0,'0')]
            for params in bad:
                await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
                before=sum(e['params']['kind']=='execute' for e in self.peer.events)
                result=await self.client.call_tool(name,params,raise_on_error=False)
                self.assertTrue(result.is_error,repr(params))
                self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)
            await self.client.call_tool('agent_prepare',PREPARE);self.peer.approved=True
            self.assertTrue((await self.client.call_tool(name,args,raise_on_error=False)).is_error)
            self.assertTrue((await self.client.call_tool('agent_prepare',{**prepare,'targets':['Console']},raise_on_error=False)).is_error)

    async def test_RT036_find_component_resolution_is_closed_before_native(self):
        tool=next(t for t in await self.client.list_tools() if t.name=='find_gameobjects')
        self.assertIn('by_component已禁用',tool.description)
        prepare={'task_id':'resolver-risk','operations':[{'command':'find_gameobjects','action':'find'}],
                 'targets':['Scenes'],'ttl_seconds':60}
        for term in ('Probe.Component, ReadOnlyProbeMissingAssembly','Transform','UnityEngine.Transform',
                     'Probe.Generic`1[[Probe.Value, ReadOnlyProbeMissingAssembly]]'):
            await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
            before=sum(e['params']['kind']=='execute' for e in self.peer.events)
            result=await self.client.call_tool('find_gameobjects',{'search_term':term,
                'search_method':'by_component','include_inactive':True,'page_size':2},raise_on_error=False)
            self.assertTrue(result.is_error,'by_component can enter native type resolution')
            self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before)

    async def test_RT026_find_native_read_no_refresh_exact_wire_and_stop(self):
        from unittest.mock import patch, AsyncMock
        prepare={'task_id':'find-task','operations':[{'command':'find_gameobjects','action':'find'}],
                 'targets':['Scenes'],'ttl_seconds':60}
        args={'search_term':'Root','search_method':'by_name','include_inactive':True,'page_size':2}
        async with Client(self.server) as client:
            with patch('services.resources.editor_state.get_editor_state',new=AsyncMock(side_effect=AssertionError('ungranted editor read'))), \
                 patch('services.tools.refresh_unity.refresh_unity',new=AsyncMock(side_effect=AssertionError('ungranted refresh'))):
                await client.call_tool('agent_prepare',prepare)
                self.peer.approved=True
                result=await client.call_tool('find_gameobjects',args)
                self.assertFalse(result.is_error)
                body=self.peer.events[-1]['params']['body']
                self.assertEqual(body,{'command':'find_gameobjects','params':{'searchTerm':'Root','searchMethod':'by_name','includeInactive':True,'pageSize':2,'cursor':0}})
                await client.call_tool('agent_stop',{'task_id':'find-task'})
                with self.assertRaises(Exception): await client.call_tool('find_gameobjects',args)
                self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),1)

    async def test_RT027_find_rejects_coercion_aliases_and_unbound_preflight(self):
        from candidate_runtime import scene_read_preflight
        from types import SimpleNamespace
        with self.assertRaises(Exception): await scene_read_preflight(SimpleNamespace(session_id='foreign'))
        prepare={'task_id':'find-task','operations':[{'command':'find_gameobjects','action':'find'}],
                 'targets':['Scenes'],'ttl_seconds':60}
        args={'search_term':'Root','search_method':'by_name','include_inactive':True,'page_size':2}
        bad=[{**args,'page_size':v} for v in (True,'2',2.0,0,101)]
        bad += [{**args,'include_inactive':v} for v in (False,'true',1,None)]
        bad += [{**args,'cursor':v} for v in (True,'0',-1,1000001)]
        bad += [{**args,'search_term':v} for v in ('',' Root','Root\n','x'*513)]
        bad += [{**args,'search_method':'by_id','search_term':v} for v in ('0','+11','011','11.0','2147483648','Assets/a.prefab')]
        bad += [{**args,'action':'find'},{**args,'target':'Root'},{**args,'search_method':'BY_NAME'}]
        bad += [{k:v for k,v in args.items() if k!=key} for key in args]
        async with Client(self.server) as client:
            for params in bad:
                await client.call_tool('agent_prepare',prepare);self.peer.approved=True
                before=sum(e['params']['kind']=='execute' for e in self.peer.events)
                with self.assertRaises(Exception): await client.call_tool('find_gameobjects',params)
                self.assertEqual(sum(e['params']['kind']=='execute' for e in self.peer.events),before,params)

    async def test_RT025_scene_validate_requires_explicit_no_repair_and_exact_scope(self):
        from unittest.mock import patch, AsyncMock
        prepare={'task_id':'validate-task','operations':[{'command':'manage_scene','action':'validate'}],
                 'targets':['Scenes'],'ttl_seconds':60}
        args={'action':'validate','auto_repair':False}
        prepared=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
        self.assertFalse(prepared.is_error, 'safe native validate scope missing')
        self.assertFalse((await self.client.call_tool('manage_scene',args)).data['success'])
        await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
        with patch('services.resources.editor_state.get_editor_state',new=AsyncMock()) as state, \
             patch('services.tools.refresh_unity.refresh_unity',new=AsyncMock()) as refresh:
            result=await self.client.call_tool('manage_scene',args)
            self.assertTrue(result.data['success'])
            self.assertEqual(self.peer.events[-1]['params']['body'],
                {'command':'manage_scene','params':{'action':'validate','autoRepair':False}})
            state.assert_not_awaited();refresh.assert_not_awaited()
        for bad in ({'action':'validate'},*[{'action':'validate','auto_repair':v} for v in (True,0,1,'false',None)],
                    {**args,'path':'Assets/Other.unity'},{**args,'cursor':0},{**args,'autoRepair':False}):
            await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
            before=len(self.peer.events)
            self.assertTrue((await self.client.call_tool('manage_scene',bad,raise_on_error=False)).is_error,repr(bad))
            self.assertFalse(any(e['params']['kind']=='execute' for e in self.peer.events[before:]))
        await self.client.call_tool('agent_prepare',{**prepare,'operations':[{'command':'manage_scene','action':'get_active'}]})
        self.peer.approved=True
        self.assertTrue((await self.client.call_tool('manage_scene',args,raise_on_error=False)).is_error)
        await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
        await self.client.call_tool('agent_stop',{'task_id':prepare['task_id']})
        self.assertTrue((await self.client.call_tool('manage_scene',args,raise_on_error=False)).is_error)

    async def test_RT024_nine_read_manifest_matches_final_gate_capacity(self):
        reads=[('manage_packages',{'action':'get_package_info','package':'com.unity.ugui'}),('get_menu_items',{}),('get_selection',{}),('get_windows',{}),('get_active_tool',{}),('get_prefab_stage',{}),('get_project_info',{}),('get_tags',{}),('get_layers',{}),('manage_animation',READ),
               ('manage_animation',{'action':'animator_get_info','target':'11','search_method':'by_id'}),
               ('manage_animation',{'action':'animator_get_parameter','target':'11','search_method':'by_id','properties':{'parameter_name':'Speed'}}),
               ('manage_material',{'action':'get_material_info','material_path':MATERIAL}),
               ('read_console',{'action':'get','page_size':2,'format':'json'}),
               ('manage_scene',{'action':'get_active'}),
               ('manage_scene',{'action':'get_build_settings'}),
               ('manage_scene',{'action':'get_loaded_scenes'}),
               ('manage_scene',{'action':'get_hierarchy','page_size':2}),
               ('manage_scene',{'action':'validate','auto_repair':False}),
               ('get_gameobject',{'instance_id':'11'}),
               ('get_gameobject_components',{'instance_id':'11','page_size':2,'include_properties':False}),
               ('find_gameobjects',{'search_term':'Root','search_method':'by_name','include_inactive':True,'page_size':2})]
        operations=[{'command':name,'action':args.get('action','find' if name=='find_gameobjects' else 'read')} for name,args in reads]
        prepare={**PREPARE,'operations':operations,'targets':[CONTROLLER,MATERIAL,'Console','Scenes','ProjectMetadata','EditorMetadata']}
        for name,args in reads:
            self.assertTrue((await self.client.call_tool(name,args,raise_on_error=False)).is_error)
        self.assertEqual(self.peer.events,[])
        for name,args in reads:
            pending=await self.client.call_tool('agent_prepare',prepare)
            self.assertEqual(pending.data['data']['status'],'pending')
            self.assertEqual(self.peer.events[-1]['params']['body'],{k:v for k,v in prepare.items() if k!='task_id'})
            denied=await self.client.call_tool(name,args,raise_on_error=False)
            payload=denied.structured_content['result'] if name in ('get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items') else denied.structured_content
            self.assertFalse(payload['success'],'pending must not approve any read')
        await self.client.call_tool('agent_prepare',prepare)
        self.peer.approved=True  # Peer substitute; real final gate is covered by NS008.
        before=len(self.peer.events)
        for name,args in reads:
            self.peer.execute_data=[] if name in ('get_tags','get_windows','get_menu_items') else {} if name in ('get_layers','get_selection','get_active_tool','get_prefab_stage','get_menu_items') else {'fixture_only':True}
            result=await self.client.call_tool(name,args)
            payload=result.structured_content['result'] if name in ('get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items') else result.structured_content
            self.assertTrue(payload['success'])
        executed=[e['params']['body'] for e in self.peer.events[before:] if e['params']['kind']=='execute']
        self.assertEqual([(e['command'],e['params'].get('action','find' if e['command']=='find_gameobjects' else 'read')) for e in executed],
                         [(r['command'],r['action']) for r in operations])
        await self.client.call_tool('agent_stop',{'task_id':prepare['task_id']})
        before=len(self.peer.events)
        for name,args in reads:
            self.assertTrue((await self.client.call_tool(name,args,raise_on_error=False)).is_error)
        self.assertEqual(len(self.peer.events),before)
        for invalid in ([],operations+[operations[0]],operations[:-1]+[operations[0]],
                        operations[:-1]+[{'command':'manage_scene','action':'save'}]):
            result=await self.client.call_tool('agent_prepare',{**prepare,'operations':invalid},raise_on_error=False)
            self.assertTrue(result.is_error,'invalid nine-operation manifest accepted')
        self.assertEqual(len(self.peer.events),before,'invalid manifest reached peer')

    async def test_RT023_hierarchy_rejects_coercion_unbounded_and_cross_scope(self):
        prepare={'task_id':'hierarchy-task','operations':[{'command':'manage_scene','action':'get_hierarchy'}],
                 'targets':['Scenes'],'ttl_seconds':60}
        normal={'action':'get_hierarchy','page_size':2}
        invalid=[{'page_size':0},{'page_size':101},{'page_size':True},{'page_size':'2'},
                 {'cursor':-1},{'cursor':1000001},{'cursor':'0'},{'cursor':False},
                 {'parent':'Root/Child'},{'parent':'-123'},{'parent':0},{'parent':True},
                 {'parent':None},{'parent':2147483648},{'parent':-2147483649},
                 {'include_transform':'true'},{'max_nodes':5000},{'max_depth':50},
                 {'path':'Assets/Other.unity'},{'action':'load'},{'scene_view_target':1}]
        for change in invalid:
            with self.subTest(change=change):
                await self.client.call_tool('agent_prepare',prepare);self.peer.approved=True
                before=len([e for e in self.peer.events if e['params']['kind']=='execute'])
                self.assertTrue((await self.client.call_tool('manage_scene',{**normal,**change},raise_on_error=False)).is_error)
                self.assertEqual(before,len([e for e in self.peer.events if e['params']['kind']=='execute']))
        await self.client.call_tool('agent_prepare',{**prepare,'operations':[{'command':'manage_scene','action':'get_active'}]})
        self.peer.approved=True
        self.assertTrue((await self.client.call_tool('manage_scene',normal,raise_on_error=False)).is_error)

    async def test_RT022_hierarchy_native_paging_and_integer_parent(self):
        prepare={'task_id':'hierarchy-task','operations':[{'command':'manage_scene','action':'get_hierarchy'}],
                 'targets':['Scenes'],'ttl_seconds':60}
        result=await self.client.call_tool('agent_prepare',prepare,raise_on_error=False)
        self.assertFalse(result.is_error, 'hierarchy capability missing')
        self.peer.approved=True
        for args in ({'action':'get_hierarchy','page_size':2},
                     {'action':'get_hierarchy','page_size':3,'cursor':2,'parent':-123,'include_transform':True}):
            result=await self.client.call_tool('manage_scene',args,raise_on_error=False)
            self.assertFalse(result.is_error)
            self.assertTrue(result.data['success'],repr(result.data))
            expected={'action':'get_hierarchy','pageSize':args['page_size']}
            for key,wire in [('cursor','cursor'),('parent','parent'),('include_transform','includeTransform')]:
                if key in args:expected[wire]=args[key]
            self.assertEqual(self.peer.events[-1]['params']['body'],{'command':'manage_scene','params':expected})
        self.assertEqual([e['params']['body']['command'] for e in self.peer.events if e['params']['kind']=='execute'],['manage_scene']*2)

    async def test_RT019_scene_metadata_uses_native_wrapper_and_exact_scene_scope(self):
        actions = ['get_active', 'get_build_settings', 'get_loaded_scenes']
        prepare = {'task_id':'scene-task', 'operations':[
            {'command':'manage_scene','action':a} for a in actions],
            'targets':['Scenes'], 'ttl_seconds':60}
        prepared = await self.client.call_tool('agent_prepare', prepare, raise_on_error=False)
        self.assertFalse(prepared.is_error, 'explicit native scene metadata scope missing')
        self.peer.approved = True
        for action in actions:
            result = await self.client.call_tool('manage_scene', {'action':action}, raise_on_error=False)
            self.assertFalse(result.is_error)
            self.assertTrue(result.data['success'], repr(result.data))
            self.assertEqual(self.peer.events[-1]['params']['body'],
                {'command':'manage_scene','params':{'action':action}})
        executed = [e['params']['body']['command'] for e in self.peer.events if e['params']['kind']=='execute']
        self.assertEqual(executed, ['manage_scene'] * 3, 'preflight must not send editor-state/refresh commands')
        await self.client.call_tool('agent_stop', {'task_id':'scene-task'})
        self.assertTrue((await self.client.call_tool('manage_scene', {'action':'get_active'}, raise_on_error=False)).is_error)

    async def test_RT016_console_rejects_clear_coercion_and_unbounded_reads(self):
        prepare={'task_id':'console-task','operations':[{'command':'read_console','action':'get'}],
                 'targets':['Console'],'ttl_seconds':60}
        normal={'action':'get','page_size':20,'format':'json'}
        invalid=[{'action':'clear'},{'action':'GET'},{'page_size':True},{'page_size':'20'},
                 {'page_size':0},{'page_size':101},{'cursor':-1},{'cursor':1000001},{'cursor':'0'},
                 {'include_stacktrace':'true'},{'types':['all']},{'types':['error','error']},
                 {'types':'["error"]'},{'filter_text':None},{'filter_text':'x'*513},
                 {'count':10},{'format':'plain'},{'approved':True}]
        for change in invalid:
            with self.subTest(change=change):
                await self.client.call_tool('agent_prepare',prepare)
                self.peer.approved=True
                before=len([e for e in self.peer.events if e['params']['kind']=='execute'])
                result=await self.client.call_tool('read_console',{**normal,**change},raise_on_error=False)
                self.assertTrue(result.is_error)
                self.assertEqual(len([e for e in self.peer.events if e['params']['kind']=='execute']),before)
        for target in ('Console/Other','console','Assets/Console','Console '):
            bad=await self.client.call_tool('agent_prepare',{**prepare,'targets':[target]},raise_on_error=False)
            self.assertTrue(bad.is_error)

    async def test_RT017_console_cannot_inherit_asset_or_other_session_approval(self):
        normal={'action':'get','page_size':10,'format':'json'}
        await self.client.call_tool('agent_prepare',PREPARE)
        self.peer.approved=True
        denied=await self.client.call_tool('read_console',normal,raise_on_error=False)
        self.assertTrue(denied.is_error)
        await self.client.call_tool('agent_prepare',{'task_id':'console-task',
            'operations':[{'command':'read_console','action':'get'}],'targets':['Console'],'ttl_seconds':60})
        async with Client(self.server) as other:
            result=await other.call_tool('read_console',normal,raise_on_error=False)
            self.assertTrue(result.is_error)
        self.assertFalse((await self.client.call_tool('read_console',normal)).is_error)
        await self.client.call_tool('agent_stop',{'task_id':'console-task'})
        self.assertTrue((await self.client.call_tool('read_console',normal,raise_on_error=False)).is_error)

    async def test_RT015_console_get_traverses_native_handler_with_explicit_scope(self):
        args={'task_id':'console-task','operations':[{'command':'read_console','action':'get'}],
              'targets':['Console'],'ttl_seconds':60}
        prepared=await self.client.call_tool('agent_prepare',args,raise_on_error=False)
        self.assertFalse(prepared.is_error, 'explicit Console read scope missing')
        self.peer.approved=True  # Unity-only approval is separately tested in compiled C#.
        result=await self.client.call_tool('read_console',{'action':'get','page_size':20,
            'cursor':0,'format':'json','include_stacktrace':True},raise_on_error=False)
        self.assertFalse(result.is_error, 'native console reader missing')
        self.assertTrue(result.data['success'])
        body=self.peer.events[-1]['params']['body']
        self.assertEqual(body,{'command':'read_console','params':{'action':'get',
            'types':['error','warning','log'],'count':10,'pageSize':20,'cursor':0,
            'format':'json','includeStacktrace':True}})

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
        self.assertEqual(names, {'agent_status', 'agent_catalog', 'agent_prepare', 'agent_stop', 'manage_animation', 'manage_material', 'read_console', 'manage_scene', 'find_gameobjects', 'get_gameobject', 'get_gameobject_components','get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items','manage_packages',
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
