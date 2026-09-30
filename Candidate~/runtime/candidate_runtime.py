"""Local candidate runtime. Reuses real FastMCP, native handlers and PluginHub.

Unity is the separate final authority. No approval endpoint exists here. Only
audited reads are enabled; this is NOT the complete installable product.
"""
import asyncio
import json
import logging
import math
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

_CURRENT: ContextVar[Any] = ContextVar('candidate_request', default=None)
SPECS = {
    'manage_animation': ('controller_get_info', 'controller_path', 'controllerPath', '.controller'),
    'manage_material': ('get_material_info', 'material_path', 'materialPath', '.mat'),
}
CONTROLS = {'agent_status', 'agent_prepare', 'agent_stop'}
# Native SDK session expiration, not a new heartbeat protocol. A quiet client
# must prepare/approve again after expiry; ping activity never extends plan TTL.
SESSION_IDLE_TIMEOUT = 60.0


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


class Runtime(Middleware):
    def __init__(self, project_id):
        self.project_id = project_id
        self.unity_required = False
        self.unity_ingress = None
        self.plans = {}
        self.preparing = {}
        self.sessions = {}
        self.closed_sessions = weakref.WeakSet()
        self.lifecycle_results = deque(maxlen=128)
        from material_runtime import MaterialRuntime
        self.material = MaterialRuntime(self)

    def bind_session(self, ctx):
        # Same SDK exit-stack mechanism used by FastMCP's stateful proxy.
        # Private SDK seam: pinned/tested, never substitute a caller identity.
        session, client = ctx.session, ctx.session_id
        if session in self.closed_sessions:
            raise ToolError('session_closed')
        if client in self.sessions:
            if self.sessions[client] is not session:
                raise ToolError('session_identity_changed')
            return
        stack = getattr(session, '_exit_stack', None)
        if stack is None or not callable(getattr(stack, 'push_async_callback', None)):
            raise ToolError('session_lifecycle_unavailable')
        self.sessions[client] = session
        stack.push_async_callback(self.close_session, client, session)

    async def close_session(self, client, session):
        if self.sessions.get(client) is not session:
            return
        self.closed_sessions.add(session)
        self.sessions.pop(client, None)
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
            invocation = Invocation(self, client, command, {}, plan)
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
        if name not in CONTROLS | SPECS.keys():
            raise ToolError('operation_not_enabled')
        ctx = context.fastmcp_context
        if ctx is None or not ctx.session_id:
            raise ToolError('request_not_bound')
        self.bind_session(ctx)
        invocation = Invocation(self, ctx.session_id, name, args)
        token = _CURRENT.set(invocation)
        read_succeeded = False
        try:
            if name == 'agent_prepare':
                self.plans.pop(invocation.client_id, None)
                previous = self.preparing.get(invocation.client_id)
                if previous is not None:
                    previous.cancelled = True
                if len(self.preparing) >= 128 and previous is None:
                    raise ToolError('prepare_capacity')
                self.preparing[invocation.client_id] = invocation
            if name in SPECS:
                action, key, _, extension = SPECS[name]
                if set(args) != {'action', key} or args['action'] != action:
                    raise ToolError('operation_not_enabled')
                target_path(args[key])
                if not args[key].endswith(extension):
                    raise ToolError('invalid_target')
                invocation.plan = self.plans.get(invocation.client_id)
                self.check_plan(invocation)
                if (name, action) not in invocation.plan.operations or args[key] not in invocation.plan.targets:
                    raise ToolError('outside_plan')
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
            if name in SPECS:
                if ctx.session in self.closed_sessions:
                    raise ToolError('session_closed')  # Never return a late session result.
                data = result.structured_content
                read_succeeded = (not result.is_error and isinstance(data, dict)
                                  and data.get('success') is True)
            return result
        finally:
            # Includes failures before PluginHub.send_command, exceptions and
            # server-side cancellation. command_failed compares plan identity.
            try:
                if name in SPECS and not read_succeeded:
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

    def command_failed(self):
        invocation = _CURRENT.get()
        if (invocation is not None and invocation.owner is self and invocation.name in SPECS
                and self.plans.get(invocation.client_id) is invocation.plan):
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
        if command in SPECS:
            self.check_plan(invocation)
            action, key, wire_key, _ = SPECS[command]
            if params != {'action': action, wire_key: invocation.arguments[key]}:
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
            'client_id': invocation.client_id, 'connection_id': session_id,
            'task_id': plan.task_id if plan else '',
            'plan_id': plan.plan_id if plan else '', 'body': body,
        }

    async def prepare(self, task_id, operations, targets, ttl_seconds):
        invocation = self.current()
        exact_id(task_id)
        if type(ttl_seconds) not in (int, float) or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= 900:
            raise ToolError('invalid_ttl')
        if not isinstance(operations, list) or not 1 <= len(operations) <= len(SPECS):
            raise ToolError('invalid_operations')
        pairs = []
        for operation in operations:
            if type(operation) is not dict or set(operation) != {'command', 'action'}:
                raise ToolError('invalid_operations')
            command = operation['command']
            if command not in SPECS or operation['action'] != SPECS[command][0]:
                raise ToolError('operation_not_enabled')
            pairs.append((command, operation['action']))
        if (type(targets) is not list or not 1 <= len(targets) <= 64
                or len(set(targets)) != len(targets) or len(set(pairs)) != len(pairs)):
            raise ToolError('invalid_targets')
        for target in targets:
            target_path(target)
            if not any(target.endswith(SPECS[c][3]) for c, _ in pairs):
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
                    frozenset(pairs), frozenset(targets))
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
                                 plan.operations, plan.targets, plan_id)
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


def create_server(project_id, *, mcp_auth=None):
    exact_id(project_id)
    config.transport_mode = 'http'
    config.http_remote_hosted = False
    config.telemetry_enabled = False
    # Embedding hook only; trusted credential/bootstrap provisioning is separate.
    # None preserves synthetic fixture mode, not an authenticated installed entry.
    server = FastMCP('vrchat-agent-candidate', auth=mcp_auth,
                     instructions='权限默认关闭；须在Unity本地核对并批准清单。')
    runtime = Runtime(project_id)
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
        return await PluginHub.send_command(await runtime.connection(), 'agent_status', {})

    @server.tool
    async def agent_prepare(task_id: str, operations: list[dict], targets: list[str],
                            ttl_seconds: float, ctx: Context) -> dict:
        """提交明确清单供Unity本地核对；仅pending，不批准或续权。"""
        return await runtime.prepare(task_id, operations, targets, ttl_seconds)

    @server.tool
    async def agent_stop(task_id: str, ctx: Context) -> dict:
        """立即关闭本会话清单映射，通知Unity撤权；不回滚文件。"""
        return await runtime.stop(task_id)

    server.tool(manage_animation, description='仅已批准controller_get_info；其他操作拒绝。')
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
