"""Local candidate runtime. Reuses real FastMCP, native handlers and PluginHub.

Unity is the separate final authority. No approval endpoint exists here. Only
audited reads are enabled; this is NOT the complete installable product.
"""
import asyncio
import json
import logging
import math
import re
import time
import weakref
from collections import deque
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import anyio
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from core.config import config
from transport.plugin_hub import PluginHub
from transport.plugin_registry import PluginRegistry
from services.tools.manage_animation import manage_animation
from services.tools.manage_material import manage_material
from services.tools.manage_packages import manage_packages
from services.tools.read_console import read_console
from services.tools.manage_scene import manage_scene
from services.tools.find_gameobjects import find_gameobjects
from services.resources.gameobject import get_gameobject, get_gameobject_components
from services.resources.project_info import get_project_info
from services.resources.tags import get_tags
from services.resources.layers import get_layers
from services.resources.selection import get_selection
from services.resources.windows import get_windows
from services.resources.active_tool import get_active_tool
from services.resources.prefab_stage import get_prefab_stage
from services.resources.menu_items import get_menu_items

_CURRENT: ContextVar[Any] = ContextVar('candidate_request', default=None)
SPECS = {
    'manage_animation': ('controller_get_info', 'controller_path', 'controllerPath', '.controller'),
    'manage_material': ('get_material_info', 'material_path', 'materialPath', '.mat'),
}
SCENE_ACTIONS = {'get_active', 'get_build_settings', 'get_loaded_scenes', 'get_hierarchy', 'validate'}
ANIMATOR_ACTIONS = {'animator_get_info', 'animator_get_parameter'}
OBJECT_TOOLS = {'get_gameobject', 'get_gameobject_components'}
PROJECT_TOOLS = {'get_project_info': get_project_info, 'get_tags': get_tags, 'get_layers': get_layers}
EDITOR_TOOLS = {'get_selection': get_selection, 'get_windows': get_windows, 'get_active_tool': get_active_tool, 'get_prefab_stage': get_prefab_stage, 'get_menu_items': get_menu_items}
METADATA_TOOLS = PROJECT_TOOLS | EDITOR_TOOLS
READ_TOOLS = SPECS.keys() | {'read_console', 'manage_scene', 'find_gameobjects', 'manage_packages'} | OBJECT_TOOLS | METADATA_TOOLS.keys()
CONTROLS = {'agent_status', 'agent_catalog', 'agent_prepare', 'agent_stop'}
# Native SDK session expiration, not a new heartbeat protocol. A quiet client
# must prepare/approve again after expiry; ping activity never extends plan TTL.
SESSION_IDLE_TIMEOUT = 60.0


def scene_params(args):
    if args.get('action') not in SCENE_ACTIONS:
        raise ToolError('operation_not_enabled')
    if args['action'] == 'validate':
        if set(args) != {'action', 'auto_repair'} or args['auto_repair'] is not False:
            raise ToolError('operation_not_enabled')
        return {'action': 'validate', 'autoRepair': False}
    if args['action'] != 'get_hierarchy':
        if set(args) != {'action'}:
            raise ToolError('unexpected_scene_arguments')
        return dict(args)
    if (not {'action', 'page_size'} <= set(args) or
            set(args) - {'action','page_size','cursor','parent','include_transform'} or
            type(args['page_size']) is not int or not 1 <= args['page_size'] <= 100):
        raise ToolError('invalid_hierarchy_page')
    if 'cursor' in args and (type(args['cursor']) is not int or not 0 <= args['cursor'] <= 1000000):
        raise ToolError('invalid_hierarchy_cursor')
    if 'parent' in args and (type(args['parent']) is not int or
            not -2147483648 <= args['parent'] <= 2147483647 or args['parent'] == 0):
        raise ToolError('hierarchy_requires_exact_instance_id')
    if 'include_transform' in args and type(args['include_transform']) is not bool:
        raise ToolError('invalid_hierarchy_transform')
    names={'page_size':'pageSize','include_transform':'includeTransform'}
    return {names.get(k,k):v for k,v in args.items()}


def find_params(args):
    required = {'search_term', 'search_method', 'include_inactive', 'page_size'}
    if not required <= args.keys() or args.keys() - required - {'cursor'}:
        raise ToolError('invalid_find_arguments')
    # Native type resolution may invoke AssemblyResolve/GetTypes callbacks.
    # Keep the whole by_component mode closed until a no-load route is audited.
    if args['search_method'] == 'by_component':
        raise ToolError('component_type_resolution_not_read_only')
    term = args['search_term']
    if (type(term) is not str or not 1 <= len(term) <= 512 or term != term.strip() or
            any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in term) or
            args['search_method'] not in ('by_name','by_tag','by_layer','by_path','by_id') or
            args['include_inactive'] is not True or type(args['page_size']) is not int or
            not 1 <= args['page_size'] <= 100 or type(args.get('cursor',0)) is not int or
            not 0 <= args.get('cursor',0) <= 1000000):
        raise ToolError('invalid_find_arguments')
    if args['search_method'] == 'by_id':
        try: number = int(term)
        except ValueError: raise ToolError('find_requires_exact_instance_id')
        if str(number) != term or number == 0 or not -2147483648 <= number <= 2147483647:
            raise ToolError('find_requires_exact_instance_id')
    return {'searchTerm':term,'searchMethod':args['search_method'],
            'includeInactive':True,'pageSize':args['page_size'],'cursor':args.get('cursor',0)}


def animator_params(args):
    action = args.get('action')
    keys = {'action', 'target', 'search_method'} | ({'properties'} if action == 'animator_get_parameter' else set())
    if action not in ANIMATOR_ACTIONS or set(args) != keys or args['search_method'] != 'by_id':
        raise ToolError('invalid_animator_arguments')
    object_params('get_gameobject', {'instance_id': args['target']})
    wire = {'action': action, 'target': args['target'], 'searchMethod': 'by_id'}
    if action == 'animator_get_parameter':
        props = args['properties']
        if type(props) is not dict or set(props) != {'parameter_name'}:
            raise ToolError('invalid_animator_parameter')
        value = props['parameter_name']
        if (type(value) is not str or not 1 <= len(value) <= 256 or
                any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in value)):
            raise ToolError('invalid_animator_parameter')
        wire['properties'] = props
    return wire


def object_params(name, args):
    required = {'instance_id'} | ({'page_size', 'include_properties'} if name == 'get_gameobject_components' else set())
    optional = {'cursor'} if name == 'get_gameobject_components' else set()
    if not required <= args.keys() or args.keys() - required - optional:
        raise ToolError('invalid_object_arguments')
    value = args['instance_id']
    if type(value) is not str or not 1 <= len(value) <= 11:
        raise ToolError('object_requires_exact_instance_id')
    try: number = int(value)
    except ValueError: raise ToolError('object_requires_exact_instance_id')
    if str(number) != value or number in (0, -1) or not -2147483648 <= number <= 2147483647:
        raise ToolError('object_requires_exact_instance_id')
    wire = {'instanceID': number}
    if name == 'get_gameobject_components':
        if (args['include_properties'] is not False or type(args['page_size']) is not int or
                not 1 <= args['page_size'] <= 100 or type(args.get('cursor', 0)) is not int or
                not 0 <= args.get('cursor', 0) <= 1000000):
            raise ToolError('component_properties_not_enabled')
        wire.update(pageSize=args['page_size'], cursor=args.get('cursor', 0), includeProperties=False)
    return wire


def package_params(args):
    value = args.get('package')
    if (set(args) != {'action', 'package'} or args['action'] != 'get_package_info' or
            type(value) is not str or len(value) > 214 or
            re.fullmatch(r'(?:[a-z0-9][a-z0-9_-]*\.)+[a-z0-9][a-z0-9_-]*', value) is None):
        raise ToolError('invalid_package_info_arguments')
    return dict(args)


def exact_id(value):
    if type(value) is not str or not 1 <= len(value) <= 128 or value != value.strip():
        raise ToolError('invalid_identity')
    if any(ord(c) < 32 for c in value):
        raise ToolError('invalid_identity')
    return value


def target_path(value):
    if (type(value) is not str or len(value) > 512 or not value.startswith('Assets/')
            or any(c in value for c in '\\:\x00')
            or any(p in ('', '.', '..') or p != p.strip() for p in value.split('/'))):
        raise ToolError('invalid_target')
    return value


def console_params(args):
    # Keep the native reader/schema; accept only bounded structured get/paging.
    required = {'action', 'page_size', 'format'}
    optional = {'types', 'cursor', 'filter_text', 'include_stacktrace'}
    if (not required <= args.keys() or args.keys() - required - optional or
            args['action'] != 'get' or args['format'] != 'json'):
        raise ToolError('operation_not_enabled')
    size, cursor = args['page_size'], args.get('cursor', 0)
    kinds = args.get('types', ['error', 'warning', 'log'])
    if (type(size) is not int or not 1 <= size <= 100 or type(cursor) is not int or
            not 0 <= cursor <= 1000000 or type(kinds) is not list or not 1 <= len(kinds) <= 3 or
            any(type(k) is not str or k not in {'error', 'warning', 'log'} for k in kinds) or
            len(set(kinds)) != len(kinds) or type(args.get('include_stacktrace', False)) is not bool):
        raise ToolError('invalid_console_page')
    wire = {'action': 'get', 'types': kinds, 'count': 10, 'pageSize': size,
            'format': 'json', 'includeStacktrace': args.get('include_stacktrace', False)}
    if 'cursor' in args:
        wire['cursor'] = cursor
    if 'filter_text' in args:
        text = args['filter_text']
        if type(text) is not str or len(text) > 512 or any(ord(c) < 32 for c in text):
            raise ToolError('invalid_console_filter')
        wire['filterText'] = text
    return wire


def snapshot(value):
    return json.loads(json.dumps(value, allow_nan=False))


@dataclass(frozen=True)
class Plan:
    task_id: str
    connection_id: str
    expires_at: float
    operations: frozenset
    targets: frozenset
    plan_id: str = ''
    approval_client: str = ''


@dataclass
class Invocation:
    owner: object
    client_id: str
    name: str
    arguments: dict
    plan: Plan | None = None
    active: bool = True
    cancelled: bool = False
    revoked_plan: Plan | None = None
    approval_client: str = ''
    paused_receipt: dict | None = None


class Runtime(Middleware):
    def __init__(self, project_id, *, authenticated=False):
        self.project_id = project_id
        self.authenticated = authenticated
        self.unity_required = False
        self.unity_ingress = None
        self.plans = {}
        self.preparing = {}
        self.sessions = {}
        self.session_identities = {}
        self.closed_sessions = weakref.WeakSet()
        self.lifecycle_results = deque(maxlen=128)
        from material_runtime import MaterialRuntime
        self.material = MaterialRuntime(self)

    def client_identity(self, ctx):
        if not self.authenticated:
            return ctx.session_id  # Explicit synthetic fixture mode only.
        from fastmcp.server.dependencies import get_access_token
        access = get_access_token()
        if access is None:
            raise ToolError('authenticated_client_required')
        # Canonical tuple: never infer a client brand from a bearer or self-report.
        identity = json.dumps([exact_id(access.client_id), exact_id(ctx.session_id)],
                              ensure_ascii=True, separators=(',', ':'))
        if len(identity) > 512:
            raise ToolError('invalid_identity')
        return identity

    def wire_client(self, invocation):
        if self.authenticated and not invocation.approval_client:
            raise ToolError('authenticated_client_required')
        return invocation.approval_client or invocation.client_id

    def bind_session(self, ctx):
        identity = self.client_identity(ctx)  # Authenticate before retaining SDK state.
        # Same SDK exit-stack mechanism used by FastMCP's stateful proxy.
        # Private SDK seam: pinned/tested, never substitute a caller identity.
        session, client = ctx.session, ctx.session_id
        if session in self.closed_sessions:
            raise ToolError('session_closed')
        if client in self.sessions:
            if self.sessions[client] is not session or self.session_identities.get(client) != identity:
                raise ToolError('session_identity_changed')
            return identity
        stack = getattr(session, '_exit_stack', None)
        if stack is None or not callable(getattr(stack, 'push_async_callback', None)):
            raise ToolError('session_lifecycle_unavailable')
        self.sessions[client] = session
        self.session_identities[client] = identity
        stack.push_async_callback(self.close_session, client, session)
        return identity

    async def close_session(self, client, session):
        if self.sessions.get(client) is not session:
            return
        self.closed_sessions.add(session)
        self.sessions.pop(client, None)
        self.session_identities.pop(client, None)
        self.material.history.pop(client, None)
        material_plan = self.material.plans.pop(client, None)
        material_pending = self.material.preparing.pop(client, None)
        if material_pending is not None:
            material_pending.cancelled = True
        pending = self.preparing.pop(client, None)
        if pending is not None:
            pending.cancelled = True
        plan = self.plans.pop(client, None)  # Revoke synchronously before network I/O.
        if plan is not None:
            await self.notify_stop(client, plan)
        if material_plan is not None:
            await self.notify_stop(client, material_plan, 'material_stop')

    async def notify_stop(self, client, plan, command='agent_stop'):
        receipt = {'client_id': client, 'local_revoked': True,
                   'unity_confirmed': False, 'reason': 'plan_identity_unavailable',
                   'command': command, 'task_id': plan.task_id, 'plan_id': plan.plan_id,
                   'connection_id': plan.connection_id}
        if plan.plan_id:
            invocation = Invocation(self, client, command, {}, plan, approval_client=plan.approval_client)
            token = _CURRENT.set(invocation)
            try:
                # A cancelled SDK session must not cancel its own revocation.
                # No retries/reconnects or raw exception data. TTL remains the
                # Unity backstop if this bounded acknowledgement fails.
                with anyio.move_on_after(2, shield=True) as scope:
                    result = await PluginHub.send_command(plan.connection_id, command, {})
                    receipt['unity_confirmed'] = (result.get('success') is True and
                        result.get('data', {}).get('status') == 'stopped')
                    receipt['reason'] = 'stopped' if receipt['unity_confirmed'] else 'unity_stop_rejected'
                if scope.cancel_called:
                    receipt['reason'] = 'unity_stop_timeout'
            except Exception:
                receipt['reason'] = 'unity_stop_unavailable'
            finally:
                invocation.active = False
                _CURRENT.reset(token)
        self.lifecycle_results.append(receipt)
        if not receipt['unity_confirmed']:
            logging.getLogger('vrchat_agent.lifecycle').warning(
                '本地权限已撤销；Unity撤权未确认（%s）；没有重试或回退。', receipt['reason'])

    def connection_closed(self, connection_id):
        self.material.connection_closed(connection_id)
        # Native on_disconnect/eviction runs this before yielding. No I/O or
        # automatic reconnect: the lost peer cannot provide a trustworthy ack.
        for client, pending in list(self.preparing.items()):
            if pending.plan is not None and pending.plan.connection_id == connection_id:
                pending.cancelled = True
                self.preparing.pop(client, None)
        for client, plan in list(self.plans.items()):
            if plan.connection_id == connection_id:
                self.plans.pop(client, None)
                self.lifecycle_results.append({'client_id': client, 'local_revoked': True,
                    'unity_confirmed': False, 'reason': 'unity_connection_closed'})

    def current(self):
        invocation = _CURRENT.get()
        if invocation is None or invocation.owner is not self or not invocation.active or invocation.cancelled:
            raise ToolError('request_not_bound')
        return invocation

    async def on_list_tools(self, context, call_next):
        from fastmcp.server.dependencies import get_access_token
        access = get_access_token()
        tools = await call_next(context)
        if access is not None and access.client_id.startswith('probe:'):
            return [tool for tool in tools if tool.name == 'agent_status']
        return tools

    async def on_call_tool(self, context, call_next):
        name = context.message.name
        from fastmcp.server.dependencies import get_access_token
        access = get_access_token()
        # Signed issuer policy admits the probe; it is never a user client.
        if access is not None and access.client_id.startswith('probe:') and name != 'agent_status':
            raise ToolError('probe_read_only')
        from material_runtime import TOOLS
        if name in TOOLS:
            return await self.material.on_call_tool(context, call_next)
        args = snapshot(context.message.arguments or {})
        if name not in CONTROLS | READ_TOOLS:
            raise ToolError('operation_not_enabled')
        ctx = context.fastmcp_context
        if ctx is None or not ctx.session_id:
            raise ToolError('request_not_bound')
        identity = self.bind_session(ctx)
        invocation = Invocation(self, ctx.session_id, name, args, approval_client=identity)
        token = _CURRENT.set(invocation)
        read_succeeded = False
        paused = False
        try:
            if name == 'agent_prepare':
                self.plans.pop(invocation.client_id, None)
                previous = self.preparing.get(invocation.client_id)
                if previous is not None:
                    previous.cancelled = True
                if len(self.preparing) >= 128 and previous is None:
                    raise ToolError('prepare_capacity')
                self.preparing[invocation.client_id] = invocation
            if name in READ_TOOLS:
                if name == 'read_console':
                    console_params(args)
                    action, target = 'get', 'Console'
                elif name == 'manage_scene':
                    scene_params(args)
                    action, target = args['action'], 'Scenes'
                elif name == 'manage_animation' and args.get('action') in ANIMATOR_ACTIONS:
                    animator_params(args)
                    action, target = args['action'], 'Scenes'
                elif name == 'manage_packages':
                    package_params(args)
                    action, target = 'get_package_info', 'ProjectMetadata'
                elif name in METADATA_TOOLS:
                    if args: raise ToolError('invalid_project_metadata_arguments')
                    action, target = 'read', 'ProjectMetadata' if name in PROJECT_TOOLS else 'EditorMetadata'
                elif name in OBJECT_TOOLS:
                    object_params(name, args)
                    action, target = 'read', 'Scenes'
                elif name == 'find_gameobjects':
                    find_params(args)
                    action, target = 'find', 'Scenes'  # Permission label; NOT a native argument.
                else:
                    action, key, _, extension = SPECS[name]
                    if set(args) != {'action', key} or args['action'] != action:
                        raise ToolError('operation_not_enabled')
                    target = target_path(args[key])
                    if not target.endswith(extension):
                        raise ToolError('invalid_target')
                invocation.plan = self.plans.get(invocation.client_id)
                self.check_plan(invocation)
                if (name, action) not in invocation.plan.operations or target not in invocation.plan.targets:
                    raise ToolError('outside_plan')
            elif name == 'agent_catalog':
                if (set(args) - {'offset','limit'} or
                        any(type(value) is not int for value in args.values())):
                    raise ToolError('invalid_catalog_page')
            elif name == 'agent_status' and args:
                raise ToolError('unexpected_arguments')
            elif name == 'agent_stop' and set(args) != {'task_id'}:
                raise ToolError('unexpected_arguments')
            elif name == 'agent_prepare' and set(args) != {'task_id', 'operations', 'targets', 'ttl_seconds'}:
                raise ToolError('unexpected_arguments')
            if name == 'agent_prepare' and type(args.get('ttl_seconds')) not in (int, float):
                raise ToolError('invalid_ttl')
            await ctx.set_state('unity_instance', self.project_id)
            result = await call_next(context)
            if name in READ_TOOLS:
                if ctx.session in self.closed_sessions:
                    raise ToolError('session_closed')  # Never return a late session result.
                data = result.structured_content
                if name in METADATA_TOOLS and isinstance(data, dict) and set(data) == {'result'}:
                    data = data['result']  # Pinned SDK union-return envelope; not recursive unwrapping.
                read_succeeded = (not result.is_error and isinstance(data, dict)
                                  and data.get('success') is True)
                paused = self.paused_response(invocation, data)
                if name in METADATA_TOOLS and isinstance(data, dict) and data.get('success') is False and data.get('error') == 'plan_paused':
                    paused = self.paused_response(invocation, invocation.paused_receipt)
                if paused:
                    result.is_error = True
            return result
        finally:
            # Includes failures before PluginHub.send_command, exceptions and
            # server-side cancellation. command_failed compares plan identity.
            try:
                if name in READ_TOOLS and not read_succeeded and not paused:
                    self.command_failed()
                if invocation.revoked_plan is not None:
                    await self.notify_stop(invocation.client_id, invocation.revoked_plan)
            finally:
                invocation.active = False
                if self.preparing.get(invocation.client_id) is invocation:
                    self.preparing.pop(invocation.client_id, None)
                _CURRENT.reset(token)

    def check_plan(self, invocation):
        plan = invocation.plan
        if (plan is None or not plan.plan_id or self.plans.get(invocation.client_id) is not plan
                or time.monotonic() >= plan.expires_at):
            raise ToolError('plan_not_current')

    async def connection(self):
        # Only registry identity; not cryptographic attestation of a local peer.
        sessions = await PluginHub._registry.list_sessions()
        matching = [s for s in sessions.values() if s.project_hash == self.project_id
                    and (not self.unity_required or
                         (self.unity_ingress is not None and self.unity_ingress.allows(s)))]
        if len(matching) != 1:
            raise ToolError('expected_project_not_connected')
        return matching[0].session_id

    async def resolve_native_instance(self, unity_instance, user_id):
        self.current()
        if unity_instance != self.project_id or user_id is not None:
            raise ToolError('request_not_bound')
        return await self.connection()

    def paused_response(self, invocation, result):
        # A gate-denied, non-executed call is not successful, but its exact local
        # pause must not be mistaken for an execution failure that destroys it.
        plan = invocation.plan
        plans = self.material.plans if invocation.name == 'material_execute' else self.plans
        return (invocation.active and not invocation.cancelled and plan is not None
                and plans.get(invocation.client_id) is plan and time.monotonic() < plan.expires_at
                and isinstance(result, dict) and result.get('success') is False
                and result.get('error') == 'plan_paused'
                and result.get('data') == {'status': 'paused', 'reason': 'plan_paused', 'plan_id': plan.plan_id})

    def command_failed(self, result=None):
        invocation = _CURRENT.get()
        # The native resource model omits error data; retain only an exact pause
        # receipt, then recheck plan identity and expiry after wrapper completion.
        if (invocation is not None and invocation.owner is self and invocation.name in METADATA_TOOLS
                and self.paused_response(invocation, result)):
            invocation.paused_receipt = snapshot(result)
        if (invocation is not None and invocation.owner is self and invocation.name in READ_TOOLS
                and self.plans.get(invocation.client_id) is invocation.plan
                and not self.paused_response(invocation, result)):
            # Preserve the precise identity until middleware can await bounded
            # Unity revocation. A cancelled read exits before SDK stack cleanup.
            invocation.revoked_plan = self.plans.pop(invocation.client_id, None)

    async def envelope(self, session_id, command, params):
        # Snapshot before await: validation and send consume this same detached value.
        params = snapshot(params)
        invocation = _CURRENT.get()
        session = await PluginHub._registry.get_session(session_id)
        if (invocation is None or invocation.owner is not self or not invocation.active or invocation.cancelled
                or config.transport_mode != 'http' or config.http_remote_hosted
                or session is None or session.project_hash != self.project_id
                or (self.unity_required and (self.unity_ingress is None or
                    not self.unity_ingress.allows(session)))):
            raise ToolError('request_not_bound')
        if command != invocation.name:
            raise ToolError('operation_not_enabled')
        from material_runtime import TOOLS
        if command in TOOLS:
            return self.material.envelope(invocation, session_id, command, params)
        if command in READ_TOOLS:
            self.check_plan(invocation)
            if command == 'read_console':
                expected = console_params(invocation.arguments)
            elif command == 'manage_scene':
                expected = scene_params(invocation.arguments)
            elif command == 'manage_animation' and invocation.arguments.get('action') in ANIMATOR_ACTIONS:
                expected = animator_params(invocation.arguments)
            elif command == 'manage_packages':
                expected = package_params(invocation.arguments)
            elif command in METADATA_TOOLS:
                expected = {'refresh': True, 'search': ''} if command == 'get_menu_items' else {}
            elif command in OBJECT_TOOLS:
                expected = object_params(command, invocation.arguments)
            elif command == 'find_gameobjects':
                expected = find_params(invocation.arguments)
            else:
                action, key, wire_key, _ = SPECS[command]
                expected = {'action': action, wire_key: invocation.arguments[key]}
            if params != expected:
                raise ToolError('operation_not_enabled')
            kind = 'execute'
            body = {'command': command, 'params': params}
        else:
            kind = command.removeprefix('agent_')
            body = params
            expected = {} if kind in ('status', 'stop') else {
                k: invocation.arguments[k] for k in ('operations', 'targets', 'ttl_seconds')}
            if params != expected:
                raise ToolError('unexpected_arguments')
        plan = invocation.plan
        if plan is not None:
            if plan.connection_id != session_id:
                raise ToolError('connection_changed')
            if kind == 'prepare' and self.plans.get(invocation.client_id) is not plan:
                raise ToolError('plan_replaced')
        return 'vrchat_agent_dispatch', {
            'protocol': 1, 'kind': kind, 'project_id': self.project_id,
            'client_id': self.wire_client(invocation), 'connection_id': session_id,
            'task_id': plan.task_id if plan else '',
            'plan_id': plan.plan_id if plan else '', 'body': body,
        }

    async def prepare(self, task_id, operations, targets, ttl_seconds):
        invocation = self.current()
        exact_id(task_id)
        if type(ttl_seconds) not in (int, float) or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= 900:
            raise ToolError('invalid_ttl')
        if not isinstance(operations, list) or not 1 <= len(operations) <= len(SPECS) + 3 + len(SCENE_ACTIONS) + len(OBJECT_TOOLS) + len(ANIMATOR_ACTIONS) + len(METADATA_TOOLS):
            raise ToolError('invalid_operations')
        pairs = []
        for operation in operations:
            if type(operation) is not dict or set(operation) != {'command', 'action'}:
                raise ToolError('invalid_operations')
            command = operation['command']
            allowed = (ANIMATOR_ACTIONS | {'controller_get_info'} if command == 'manage_animation' else
                       {'get_package_info'} if command == 'manage_packages' else
                       SCENE_ACTIONS if command == 'manage_scene' else
                       {'read'} if command in OBJECT_TOOLS | METADATA_TOOLS.keys() else
                       {'find'} if command == 'find_gameobjects' else
                       {'get'} if command == 'read_console' else
                       {SPECS[command][0]} if command in SPECS else set())
            if type(operation['action']) is not str or operation['action'] not in allowed:
                raise ToolError('operation_not_enabled')
            pairs.append((command, operation['action']))
        if (type(targets) is not list or not 1 <= len(targets) <= 64
                or len(set(targets)) != len(targets) or len(set(pairs)) != len(pairs)):
            raise ToolError('invalid_targets')
        for target in targets:
            if target == 'Console' and ('read_console', 'get') in pairs:
                continue
            if target == 'Scenes' and any(command in {'manage_scene','find_gameobjects'} | OBJECT_TOOLS or
                                          (command == 'manage_animation' and action in ANIMATOR_ACTIONS) for command, action in pairs):
                continue
            if ((target == 'ProjectMetadata' and any(command in PROJECT_TOOLS or command == 'manage_packages' for command, action in pairs)) or
                    (target == 'EditorMetadata' and any(command in EDITOR_TOOLS for command, action in pairs))):
                continue
            target_path(target)
            if not any(c in SPECS and a == SPECS[c][0] and target.endswith(SPECS[c][3]) for c, a in pairs):
                raise ToolError('invalid_target')
        # Bound idle session storage. Expiry removes mapping, never renews Unity approval.
        self.plans = {k: p for k, p in self.plans.items() if p.expires_at > time.monotonic()}
        if len(self.plans) >= 128 and invocation.client_id not in self.plans:
            raise ToolError('plan_capacity')
        self.plans.pop(invocation.client_id, None)
        connection = await self.connection()
        if invocation.cancelled or self.preparing.get(invocation.client_id) is not invocation:
            raise ToolError('prepare_cancelled')
        plan = Plan(task_id, connection, time.monotonic() + ttl_seconds,
                    frozenset(pairs), frozenset(targets), approval_client=invocation.approval_client)
        invocation.plan = plan
        self.plans[invocation.client_id] = plan
        returned_plan = None
        try:
            result = await PluginHub.send_command(connection, 'agent_prepare', {
                'operations': operations, 'targets': targets, 'ttl_seconds': ttl_seconds})
            data = result.get('data', {})
            if result.get('success') is not True or data.get('status') != 'pending':
                raise ToolError('prepare_not_pending')
            plan_id = exact_id(data.get('plan_id'))
            returned_plan = Plan(plan.task_id, connection, plan.expires_at,
                                 plan.operations, plan.targets, plan_id, plan.approval_client)
            current_connection = await self.connection()
            if (self.plans.get(invocation.client_id) is not plan or current_connection != connection
                    or time.monotonic() >= plan.expires_at or not invocation.active or invocation.cancelled):
                raise ToolError('plan_replaced')
            self.plans[invocation.client_id] = returned_plan
            return result
        except BaseException:
            if self.plans.get(invocation.client_id) is plan:
                self.plans.pop(invocation.client_id, None)
            if returned_plan is not None and invocation.client_id not in self.sessions:
                await self.notify_stop(invocation.client_id, returned_plan)
            raise

    async def stop(self, task_id):
        invocation = self.current()
        exact_id(task_id)
        plan = self.plans.get(invocation.client_id)
        pending = self.preparing.get(invocation.client_id)
        if pending is not None:
            if pending.arguments.get('task_id') != task_id:
                raise ToolError('task_mismatch')
            pending.cancelled = True
        if plan is None:
            return {'success': True, 'data': {'status': 'locally_stopped', 'unity_confirmed': False}}
        if plan.task_id != task_id:
            raise ToolError('task_mismatch')
        invocation.plan = self.plans.pop(invocation.client_id)
        return await PluginHub.send_command(plan.connection_id, 'agent_stop', {})


async def scene_read_preflight(ctx, **_options):
    """Native scene wrapper's preflight adapter in this owned candidate process.

    Upstream preflight can refresh/import/compile and query an ungranted resource.
    Final editor dispatch remains responsible for compile/update readiness. No
    cached editor state, automatic refresh, retry, or self-granted status query.
    """
    invocation = _CURRENT.get()
    if (invocation is None or not invocation.active or invocation.cancelled or
            invocation.name not in ('manage_scene','find_gameobjects') or ctx.session_id != invocation.client_id):
        raise ToolError('request_not_bound')
    if invocation.name == 'find_gameobjects': find_params(invocation.arguments)
    else: scene_params(invocation.arguments)
    invocation.owner.check_plan(invocation)
    return None


def create_server(project_id, *, mcp_auth=None):
    exact_id(project_id)
    config.transport_mode = 'http'
    config.http_remote_hosted = False
    config.telemetry_enabled = False
    # Embedding hook only; trusted credential/bootstrap provisioning is separate.
    # None preserves synthetic fixture mode, not an authenticated installed entry.
    server = FastMCP('vrchat-agent-candidate', auth=mcp_auth,
                     instructions='权限默认关闭；须在Unity本地核对并批准清单。')
    runtime = Runtime(project_id, authenticated=server.auth is not None)
    server._candidate_runtime = runtime
    PluginHub.configure(PluginRegistry(), asyncio.get_running_loop(), mcp=server)
    PluginHub.command_envelope = runtime.envelope
    PluginHub.instance_resolver = runtime.resolve_native_instance
    PluginHub.command_failed = runtime.command_failed
    PluginHub.connection_closed = runtime.connection_closed
    server.add_middleware(runtime)

    @server.tool
    async def agent_status(ctx: Context) -> dict:
        """读取所选Unity工程受控入口状态；不授予权限。"""
        result = await PluginHub.send_command(await runtime.connection(), 'agent_status', {})
        if type(result) is dict and result.get('success') is True and type(result.get('data')) is dict:
            result = {**result, 'data': {**result['data'], 'project_id': runtime.project_id}}
        return result

    @server.tool
    async def agent_catalog(offset: int = 0, limit: int = 12) -> dict:
        """分页列出固定版本的中文原生能力目录，不接触Unity、不授予权限。"""
        from operation_catalog import page
        return page(offset, limit)

    @server.tool
    async def agent_prepare(task_id: str, operations: list[dict], targets: list[str],
                            ttl_seconds: float, ctx: Context) -> dict:
        """提交明确清单供Unity本地核对；仅pending，不批准或续权。"""
        return await runtime.prepare(task_id, operations, targets, ttl_seconds)

    @server.tool
    async def agent_stop(task_id: str, ctx: Context) -> dict:
        """立即关闭本会话清单映射，通知Unity撤权；不回滚文件。"""
        return await runtime.stop(task_id)

    server.tool(read_console, description='仅本地批准Console范围后的get；必须action=get、format=json、page_size整数1–100。仅types(error/warning/log)、cursor整数0–1000000、filter_text、include_stacktrace布尔可选；拒绝clear/count/类型转换。分页total在truncated时仅为下界，实时日志非冻结快照。')
    # Module-local adapter: installed only by this candidate server factory.
    import importlib
    importlib.import_module('services.tools.manage_scene').preflight = scene_read_preflight
    importlib.import_module('services.tools.find_gameobjects').preflight = scene_read_preflight
    for name, reader in EDITOR_TOOLS.items():
        if name == 'get_menu_items':
            server.tool(reader, name=name, description='固定原生菜单名称资源facade，仅空参数{}，独立get_menu_items/read与EditorMetadata批准；内部refresh=true仅重建TypeCache菜单元数据缓存，不是资产刷新，不执行菜单方法。至多4096项，原生扫描失败可能返回旧缓存或空列表，不承诺穷尽。')
            continue
        server.tool(reader, name=name, description='复用固定原生编辑器资源；仅空参数{}，独立'+name+'/read和EditorMetadata本地清单批准。披露当前选择的名称/类型/ID、窗口标题与坐标、当前工具设置或已打开Prefab Stage路径。不是对象内容权限，不选择/聚焦/打开Prefab、不刷新。选择最多1024项、窗口最多256个；原生窗口异常可跳过，不保证穷尽。')
    for name, reader in PROJECT_TOOLS.items():
        server.tool(reader, name=name, description='复用固定原生资源，仅空参数{}；需独立本地'+name+'/read和ProjectMetadata批准。项目元数据实时读取：info含绝对工程路径、Unity版本与平台，原生Python模型不输出管线/输入/包标记；tags至多1024条，layers仅0–31。不是资产正文/目录权限，不刷新、不安装包、不执行脚本。')
    server.tool(get_gameobject, name='get_gameobject', description='复用原生gameobject资源：仅精确规范instance_id字符串，当前场景/Prefab Stage对象摘要、Transform值、子对象ID及组件类型，不读取通用组件属性。需独立本地get_gameobject/read及Scenes批准；子对象超1024或组件超256拒绝，不截断。')
    server.tool(get_gameobject_components, name='get_gameobject_components', description='复用原生components资源，仅组件类型和ID分页。必须显式include_properties=false、page_size整数1–100和规范instance_id字符串；可选cursor整数0–1000000。只读当前场景/Prefab Stage，需独立本地get_gameobject_components/read及Scenes批准；不调用用户属性getter。')
    server.tool(find_gameobjects, description='查找当前场景/Prefab Stage对象ID；须本地批准Scenes及find_gameobjects/find（find仅为清单权限名，不是工具action参数）。必填search_term、search_method、include_inactive=true、page_size整数1–100；可选cursor整数0–1000000。by_id只接收规范非零int32字符串；其他方法by_name/by_tag/by_layer/by_path；by_component已禁用，避免类型解析触发用户回调。分页只限制响应条数，上游仍先遍历全部匹配项；不是冻结快照。不读取组件属性、不选择对象、不加载资产、不刷新。')
    server.tool(manage_scene, description='仅本地批准Scenes范围后的get_active/get_build_settings/get_loaded_scenes（仅action）和get_hierarchy。层级必填page_size整数1–100；可选cursor整数0–1000000、parent非零int32的当前场景/Prefab Stage内GameObject ID、include_transform布尔。拒绝名称/路径、max_depth、加载/保存/刷新/修复。validate必须仅action和显式auto_repair=false，不修复、不Undo、不标脏；问题记录最多200条，totalIssues按脚本/Prefab问题数量统计，非对象记录数，全场景遍历可能耗时。单层实时摘要，非冻结完整树或完整组件属性；childrenPageSizeDefault仅上游提示，不扩大100条上限。')
    server.tool(manage_animation, description='controller_get_info仅精确批准的controller_path；animator_get_info/animator_get_parameter需独立Scenes批准，必填规范非零int32字符串target与search_method=by_id。get_parameter仅properties字典parameter_name精确名称；get_info不接受properties。仅当前场景/Prefab Stage，参数最多256、层最多64，info含至多1024个已引用clip摘要。Trigger沿用原生GetBool结果，不承诺触发器队列状态。拒绝播放、赋值、修改、刷新与任何其他参数。')
    server.tool(manage_packages, description='仅get_package_info与规范小写已安装包名package（最长214字符），独立ProjectMetadata清单批准。复用本地GetAllRegisteredPackages，返回版本/描述/作者/来源/绝对路径/依赖元数据；不是包内容授权，不查询远端或触发UPM任务。拒绝其他action及多余参数；依赖超1024/输出预算拒绝。')
    server.tool(manage_material, description='仅已批准get_material_info；其他操作拒绝。')
    from material_runtime import register
    register(server, runtime.material)
    return server


class LocalRequestBoundary:
    """Native clients only: exact local authority; no browser Origin allowed.

    This is a shared HTTP/WS request guard, not local-user authentication.
    Do not derive authority from forwarded or caller-controlled headers.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            headers = scope.get('headers', [])
            hosts = [v for k, v in headers if k.lower() == b'host']
            has_origin = any(k.lower() == b'origin' for k, _ in headers)
            server = scope.get('server')
            port = server[1] if server else None
            # ASGI test transports may omit the default HTTP port.
            if port is None:
                port = 443 if scope.get('scheme') in ('https', 'wss') else 80
            allowed = {f'{host}:{port}'.encode('ascii') for host in ('127.0.0.1', 'localhost')}
            if port == 80:
                allowed.update({b'127.0.0.1', b'localhost'})
            if len(hosts) != 1 or hosts[0] not in allowed or has_origin:
                if scope['type'] == 'websocket':
                    await send({'type': 'websocket.close', 'code': 1008})
                else:
                    from starlette.responses import PlainTextResponse
                    await PlainTextResponse('local_native_request_required', status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SessionTermination:
    """Observe SDK-accepted DELETE; do not reimplement or bypass MCP validation.

    FastMCP 3.4.7 waits for in-flight handlers before session exit callbacks.
    Revoke before delivering its successful termination response, not after a
    potentially slow native handler returns. Rejected DELETEs have no effects.
    """
    def __init__(self, app, runtime):
        self.app, self.runtime = app, runtime

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope.get('method') != 'DELETE'
                or scope.get('path', '').rstrip('/') != '/mcp'):
            return await self.app(scope, receive, send)
        from starlette.datastructures import Headers
        client = Headers(scope=scope).get('mcp-session-id')
        session = self.runtime.sessions.get(client)

        async def accepted(message):
            if (session is not None and message['type'] == 'http.response.start'
                    and message['status'] == 200):
                await self.runtime.close_session(client, session)
            await send(message)
        await self.app(scope, receive, accepted)


def create_app(server, *, unity_auth=None):
    """Only MCP and the native Unity socket; no native REST/custom routes."""
    from pathlib import Path
    if unity_auth is not None:
        from candidate_auth import CandidateJWTVerifier
        if (type(unity_auth) is not CandidateJWTVerifier
                or type(server.auth) is not CandidateJWTVerifier
                or len(unity_auth._principals) != 1
                or not unity_auth._principals.isdisjoint(server.auth._principals)
                or unity_auth.audience == server.auth.audience
                or unity_auth.required_scopes != ['candidate:unity']
                or server.auth.required_scopes != ['candidate:mcp']):
            raise ValueError('disjoint_finite_role_policies_required')
    import mcp.server.streamable_http as sdk_http
    expected = Path(__file__).resolve().parents[1] / 'dependencies/mcp-1.29.1/mcp/server/streamable_http.py'
    if Path(sdk_http.__file__).resolve() != expected:
        raise RuntimeError('candidate_sdk_required')
    from starlette.routing import WebSocketRoute
    app = server.http_app(path='/mcp', transport='streamable-http')
    # FastMCP 3.4.7 does not forward this MCP 1.29.1 option. Configure its actual
    # manager after lifespan startup but BEFORE accepting any requests. Preserve
    # upstream run/termination/cleanup logic instead of copying a session stack.
    from fastmcp.server.http import StreamableHTTPASGIApp
    endpoint = next(r.endpoint for r in app.routes if getattr(r, 'path', None) == '/mcp')
    from fastmcp.server.auth.middleware import RequireAuthMiddleware
    if type(endpoint) is RequireAuthMiddleware:
        endpoint = endpoint.app  # Inspect the manager; never remove the auth route.
    if not isinstance(endpoint, StreamableHTTPASGIApp):
        raise RuntimeError('candidate_session_manager_unavailable')
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def bounded_sessions(application):
        async with original_lifespan(application) as state:
            manager = endpoint.session_manager
            if (manager is None or not hasattr(manager, 'session_idle_timeout')
                    or not 0 < SESSION_IDLE_TIMEOUT <= 60):
                raise RuntimeError('candidate_session_policy_unavailable')
            manager.session_idle_timeout = SESSION_IDLE_TIMEOUT
            yield state

    app.router.lifespan_context = bounded_sessions
    server._candidate_runtime.unity_required = server.auth is not None
    # Authenticated ingress is local-factory injection only; no CLI/bootstrap yet.
    if unity_auth is not None:
        if server.auth is None:
            raise RuntimeError('mcp_auth_required')
        from unity_ingress import UnityIngress
        ingress = UnityIngress(unity_auth, server._candidate_runtime)
        server._candidate_runtime.unity_ingress = ingress
        app.routes.append(WebSocketRoute('/hub/plugin', ingress))
    elif server.auth is None:
        app.routes.append(WebSocketRoute('/hub/plugin', PluginHub))
        app.routes.append(WebSocketRoute('/hub', PluginHub))  # Synthetic fixture mode only.
    app.add_middleware(SessionTermination, runtime=server._candidate_runtime)
    app.add_middleware(LocalRequestBoundary)
    return app
