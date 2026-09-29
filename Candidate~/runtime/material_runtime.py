"""Narrow material wire adapter; approval and mutation stay in the Unity gate.
No native Python write/preflight handler, generic command or remote approval.
"""
import math
import re
import time
import unicodedata
from dataclasses import dataclass

from fastmcp import Context
from fastmcp.exceptions import ToolError
from transport.plugin_hub import PluginHub
from candidate_runtime import Invocation, _CURRENT, exact_id

TOOLS = {'material_prepare', 'material_execute', 'material_status', 'material_stop'}
ROUTE = 'vrchat_agent_material_dispatch'


def text(value):
    if (type(value) is not str or not 1 <= len(value) <= 512 or value != value.strip()
            or any(unicodedata.category(c) == 'Cc' for c in value)):
        raise ToolError('invalid_string')
    return value


def asset_path(value):
    text(value)
    if (not value.startswith('Assets/') or any(c in value for c in '\\:*?"<>|')
            or any(p in ('', '.', '..') or p != p.strip() or p.endswith('.') for p in value.split('/'))):
        raise ToolError('invalid_path')
    return value


def keys(value, *expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ToolError('unexpected_arguments')


def reference(value):
    keys(value, 'renderer', 'slot')
    if (re.fullmatch(r'GlobalObjectId_V1-[0-3]-[0-9a-fA-F]{32}-[0-9]+-[0-9]+', text(value['renderer'])) is None
            or type(value['slot']) is not int or not 0 <= value['slot'] < 256):
        raise ToolError('invalid_reference')


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate(name, args):
    if name == 'material_prepare':
        keys(args, 'task_id', 'source', 'candidate', 'operations', 'references', 'ttl_seconds')
        source, candidate = asset_path(args['source']), asset_path(args['candidate'])
        if not source.endswith('.mat') or not candidate.endswith('.mat') or source.lower() == candidate.lower():
            raise ToolError('invalid_material_pair')
        ops, refs, ttl = args['operations'], args['references'], args['ttl_seconds']
        if (type(ops) is not list or not 1 <= len(ops) <= 3
                or any(type(op) is not str or op not in ('copy', 'edit', 'reference') for op in ops)
                or len(set(ops)) != len(ops)):
            raise ToolError('invalid_operations')
        if type(refs) is not list or len(refs) > 32 or bool(refs) != ('reference' in ops):
            raise ToolError('reference_scope_required')
        for item in refs:
            reference(item)
        if len({(r['renderer'], r['slot']) for r in refs}) != len(refs):
            raise ToolError('invalid_reference')
        if not finite_number(ttl) or not 0 < ttl <= 900:
            raise ToolError('invalid_ttl')
    elif name == 'material_execute':
        keys(args, 'task_id', 'plan_id', 'action', 'arguments')
        action, body = args['action'], args['arguments']
        if action == 'copy':
            keys(body)
        elif action == 'reference':
            reference(body)
        elif action == 'edit':
            keys(body, 'property', 'value')
            text(body['property'])
            value = body['value']
            if type(value) is str:
                asset_path(value)  # Texture existence/type is checked in the real Unity backend.
            elif not (type(value) is bool or finite_number(value) or
                    (type(value) is list and 2 <= len(value) <= 4 and all(finite_number(x) for x in value))):
                raise ToolError('invalid_value')
        else:
            raise ToolError('unsupported_operation')
    else:
        keys(args, 'task_id', 'plan_id')
    text(args['task_id'])
    if name != 'material_prepare' and not (name == 'material_status' and args['plan_id'] == ''):
        text(args['plan_id'])


@dataclass(frozen=True)
class MaterialPlan:
    task_id: str
    connection_id: str
    expires_at: float
    manifest: dict
    plan_id: str = ''


class MaterialRuntime:
    def __init__(self, runtime):
        self.runtime = runtime
        self.plans = {}
        self.preparing = {}
        # Retain only identities, never manufacture cached transaction reports.
        # Historical status is always read from the same native connection.
        self.history = {}

    def connection_closed(self, connection_id):
        for client, invocation in list(self.preparing.items()):
            if invocation.plan is not None and invocation.plan.connection_id == connection_id:
                invocation.cancelled = True
                self.preparing.pop(client)
        for client, plan in list(self.plans.items()):
            if plan.connection_id == connection_id:
                self.plans.pop(client)
                self.runtime.lifecycle_results.append({'client_id': client, 'local_revoked': True,
                    'unity_confirmed': False, 'reason': 'unity_connection_closed',
                    'command': 'material_stop', 'task_id': plan.task_id, 'plan_id': plan.plan_id,
                    'connection_id': connection_id})
        for client, history in list(self.history.items()):
            for plan_id, plan in list(history.items()):
                if plan.connection_id == connection_id:
                    history.pop(plan_id)
            if not history:
                self.history.pop(client)

    async def on_call_tool(self, context, call_next):
        ctx = context.fastmcp_context
        if ctx is None or not ctx.session_id:
            raise ToolError('request_not_bound')
        self.runtime.bind_session(ctx)
        from candidate_runtime import snapshot
        args = snapshot(context.message.arguments or {})
        invocation = Invocation(self.runtime, ctx.session_id, context.message.name, args)
        token = _CURRENT.set(invocation)
        completed = False
        try:
            validate(invocation.name, args)  # Before FastMCP/Pydantic can coerce numbers/bools.
            await ctx.set_state('unity_instance', self.runtime.project_id)
            result = await call_next(context)
            data = result.structured_content
            completed = not result.is_error and isinstance(data, dict) and data.get('success') is True
            if isinstance(data, dict) and data.get('success') is False:
                # Keep the original transaction/readback even on native ErrorResponse.
                result.is_error = True
            return result
        finally:
            try:
                if (invocation.name == 'material_execute' and not completed and invocation.plan is not None
                        and self.plans.get(invocation.client_id) is invocation.plan):
                    self.plans.pop(invocation.client_id)
                    await self.runtime.notify_stop(invocation.client_id, invocation.plan, 'material_stop')
            finally:
                invocation.active = False
                _CURRENT.reset(token)

    def scope(self, task_id, plan_id, current=False):
        invocation = self.runtime.current()
        exact_id(task_id)
        exact_id(plan_id)
        plan = self.history.get(invocation.client_id, {}).get(plan_id)
        if plan is None or plan.task_id != task_id:
            raise ToolError('plan_not_current')
        if current and (self.plans.get(invocation.client_id) is not plan or time.monotonic() >= plan.expires_at):
            raise ToolError('plan_not_current')
        return invocation, plan

    def envelope(self, invocation, session_id, command, params):
        kind = command.removeprefix('material_')
        plan = invocation.plan
        if plan is None or plan.connection_id != session_id:
            raise ToolError('connection_changed')
        # This runs after the final async registry lookup, immediately before send.
        if kind == 'execute' and (self.plans.get(invocation.client_id) is not plan
                or time.monotonic() >= plan.expires_at):
            raise ToolError('plan_not_current')
        if kind == 'prepare' and self.preparing.get(invocation.client_id) is not invocation:
            raise ToolError('prepare_cancelled')
        expected = (plan.manifest if kind == 'prepare' else
            {k: invocation.arguments[k] for k in ('action', 'arguments')} if kind == 'execute' else {})
        if params != expected:
            raise ToolError('unexpected_arguments')
        return ROUTE, {'protocol': 1, 'kind': kind, 'project_id': self.runtime.project_id,
            'client_id': invocation.client_id, 'connection_id': session_id,
            'task_id': plan.task_id, 'plan_id': plan.plan_id, 'body': params}

    async def prepare(self, task_id, source, candidate, operations, references, ttl_seconds):
        invocation = self.runtime.current()
        exact_id(task_id)
        client = invocation.client_id
        if client in self.preparing:
            raise ToolError('prepare_in_progress')
        self.preparing[client] = invocation
        returned = None
        try:
            # A replacement attempt revokes the old grant even if Unity rejects it.
            # Keep only its journal identity, never restore its execution authority.
            previous = self.plans.pop(client, None)
            if previous is not None:
                await self.runtime.notify_stop(client, previous, 'material_stop')
            connection = await self.runtime.connection()
            if invocation.cancelled or self.preparing.get(client) is not invocation:
                raise ToolError('prepare_cancelled')
            manifest = {'source': source, 'candidate': candidate, 'operations': operations,
                'references': references, 'ttl_seconds': ttl_seconds}
            pending = MaterialPlan(task_id, connection, time.monotonic() + ttl_seconds, manifest)
            invocation.plan = pending
            result = await PluginHub.send_command(connection, 'material_prepare', manifest)
            data = result.get('data') or {}
            if result.get('success') is not True:
                return result  # Native failures may include actual transaction evidence.
            returned = MaterialPlan(task_id, connection, pending.expires_at, manifest, exact_id(data.get('plan_id')))
            if data.get('status') != 'pending':
                raise ToolError('prepare_not_pending')
            current_connection = await self.runtime.connection()
            if (invocation.cancelled or not invocation.active or client not in self.runtime.sessions
                    or self.preparing.get(client) is not invocation or connection != current_connection
                    or time.monotonic() >= pending.expires_at):
                raise ToolError('prepare_cancelled')
            self.plans[client] = returned
            self.history.setdefault(client, {})[returned.plan_id] = returned
            return result
        except BaseException:
            if returned is not None:
                await self.runtime.notify_stop(client, returned, 'material_stop')
            raise
        finally:
            if self.preparing.get(client) is invocation:
                self.preparing.pop(client)

    async def execute(self, task_id, plan_id, action, arguments):
        invocation, plan = self.scope(task_id, plan_id, current=True)
        if action not in plan.manifest['operations']:
            raise ToolError('outside_plan')
        if action == 'reference' and arguments not in plan.manifest['references']:
            raise ToolError('reference_not_approved')
        invocation.plan = plan
        return await PluginHub.send_command(plan.connection_id, 'material_execute',
            {'action': action, 'arguments': arguments})

    async def status(self, task_id, plan_id):
        if plan_id:
            invocation, plan = self.scope(task_id, plan_id)
        else:
            invocation = self.runtime.current()
            exact_id(task_id)
            plan = MaterialPlan(task_id, await self.runtime.connection(), 0, {})
        invocation.plan = plan
        return await PluginHub.send_command(plan.connection_id, 'material_status', {})

    async def stop(self, task_id, plan_id):
        invocation, plan = self.scope(task_id, plan_id)
        invocation.plan = plan
        if self.plans.get(invocation.client_id) is plan:
            self.plans.pop(invocation.client_id)
        return await PluginHub.send_command(plan.connection_id, 'material_stop', {})


def register(server, material):
    @server.tool
    async def material_prepare(task_id: str, source: str, candidate: str, operations: list[str],
            references: list[dict], ttl_seconds: float, ctx: Context) -> dict:
        """提交具体材质候选文件/引用清单；仅pending，须Unity本地批准。"""
        return await material.prepare(task_id, source, candidate, operations, references, ttl_seconds)

    @server.tool
    async def material_execute(task_id: str, plan_id: str, action: str, arguments: dict, ctx: Context) -> dict:
        """仅执行本会话已批准的copy/edit/reference；保留失败与回读，不重试。"""
        return await material.execute(task_id, plan_id, action, arguments)

    @server.tool
    async def material_status(task_id: str, plan_id: str, ctx: Context) -> dict:
        """精确读取本会话/任务/原连接journal；空plan_id仅查能力，不续权。"""
        return await material.status(task_id, plan_id)

    @server.tool
    async def material_stop(task_id: str, plan_id: str, ctx: Context) -> dict:
        """只停止精确材质计划，不回退、不保存场景，不撤其他新计划。"""
        return await material.stop(task_id, plan_id)
