"""Opt-in host-side Hermes binding; import is inert, no gateway installation.

The trusted host supplies an already authenticated, exclusively owned native
MCPServerTask on the running event loop. This module is not credential delivery.
Install the returned tool snapshot only at a new conversation's construction;
never mutate an existing agent's tools. The host must await close before loop exit.
"""
import asyncio
import json
import secrets
import re
from concurrent.futures import TimeoutError, CancelledError

from weakref import WeakValueDictionary

CALL_TIMEOUT = 30
_ADOPTED = WeakValueDictionary()  # Weak binding, not the native slotted peer.


class Binding:
    def __init__(self, peer, registry, conversation_id):
        self._peer = peer
        self._session = peer.session
        self._registry = registry
        self._conversation = conversation_id
        self._loop = asyncio.get_running_loop()
        self._scope = registry.current_scope_key()
        self._entries = []
        self._schemas = '[]'
        self._ready = False
        self._closed = False
        self._inflight = set()
        self._close_task = None

    def snapshot(self):
        """Return an independent JSON snapshot, not a live registry view."""
        return json.loads(self._schemas)

    def _handler(self, raw):
        def call(args, **context):
            if self._closed:
                return json.dumps({'error':'candidate_binding_closed'})
            try:
                current = asyncio.get_running_loop()
            except RuntimeError:
                current = None
            if current is self._loop or not self._loop.is_running():
                return json.dumps({'error':'candidate_dispatch_loop_unavailable'})
            try:
                if type(args) is not dict:
                    raise ValueError()
                arguments = json.loads(json.dumps(args, allow_nan=False))
            except (ValueError, TypeError, RecursionError):
                return json.dumps({'error':'candidate_arguments_invalid'})
            coroutine = self._call(raw, arguments, context.get('session_id'))
            try:
                future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
            except RuntimeError:
                coroutine.close()
                return json.dumps({'error':'candidate_dispatch_loop_unavailable'})
            try:
                return future.result(timeout=CALL_TIMEOUT)
            except TimeoutError:
                future.cancel()
                self._loop.call_soon_threadsafe(self._begin_close)
                return json.dumps({'error':'candidate_call_timeout','outcome_unknown':True})
            except CancelledError:
                return json.dumps({'error':'candidate_call_interrupted','outcome_unknown':True})
        return call

    async def _call(self, raw, args, conversation):
        if self._closed or not self._ready:
            return json.dumps({'error':'candidate_binding_closed'})
        if type(conversation) is not str or conversation != self._conversation:
            return json.dumps({'error':'candidate_wrong_conversation'})
        if self._peer.session is not self._session:
            return json.dumps({'error':'candidate_session_changed'})
        task = asyncio.current_task()
        self._inflight.add(task)
        try:
            response = await self._session.call_tool(raw, args)
            if self._closed or self._peer.session is not self._session:
                return json.dumps({'error':'candidate_call_interrupted','outcome_unknown':True})
            result = {'mcp': response.model_dump(mode='json', by_alias=True)}
            if response.is_error:
                result['error'] = 'candidate_remote_error'
            return json.dumps(result)
        except asyncio.CancelledError:
            return json.dumps({'error':'candidate_call_interrupted','outcome_unknown':True})
        except Exception:
            self._begin_close()
            return json.dumps({'error':'candidate_transport_failed','outcome_unknown':True})
        finally:
            self._inflight.discard(task)

    async def close(self):
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('candidate_wrong_loop')
        self._begin_close()
        await asyncio.shield(self._close_task)

    def _begin_close(self):
        # Called only on the owned loop; close is terminal for this generation.
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._cleanup())

    async def _cleanup(self):
        try:
            for name, entry in self._entries:
                self._registry.restore_registration(name, entry, None, scope=self._scope)
        finally:
            tasks = tuple(self._inflight)
            for task in tasks:
                task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                await self._peer.shutdown()


async def bind(peer, registry, *, conversation_id, include):
    """Transfer one started peer, including failure cleanup; no credentials accepted."""
    from tools.mcp_tool import _convert_mcp_schema
    if id(peer) in _ADOPTED:
        raise ValueError('candidate_peer_already_bound')
    binding = Binding(peer, registry, conversation_id)
    _ADOPTED[id(peer)] = binding
    try:
        if (type(conversation_id) is not str or not 1 <= len(conversation_id) <= 512
                or type(include) is not tuple or not 1 <= len(include) <= 64
                or any(type(n) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', n) is None for n in include)
                or len(set(include)) != len(include) or binding._session is None):
            raise ValueError('candidate_binding_invalid')
        catalog = await binding._session.list_tools()
        tools = {t.name:t for t in catalog.tools}
        if (len(tools) != len(catalog.tools) or getattr(catalog,'next_cursor',None) is not None
                or any(raw not in tools for raw in include) or peer.session is not binding._session):
            raise ValueError('candidate_catalog_invalid')
        generation = secrets.token_hex(16)
        schemas = []
        for i, raw in enumerate(include):
            schema = _convert_mcp_schema('candidate', tools[raw])
            # Preserve the actual MCP contract (including nullable branches).
            # The native host repairs top-level typed properties before dispatch.
            # Equivalent standard allOf schemas keep raw JSON for final authority;
            # no host patch, disabled guard, or broadened accepted input types.
            parameters = json.loads(json.dumps(tools[raw].input_schema))
            if 'properties' in parameters:
                parameters['properties'] = {key: {'allOf': [value]}
                    for key, value in parameters['properties'].items()}
            schema['parameters'] = parameters
            name = 'vrc_' + generation + '_' + str(i)
            schema['name'] = name
            if registry.get_entry(name, scope=binding._scope) is not None:
                raise ValueError('candidate_registration_collision')
            handler = binding._handler(raw)
            try:
                registry.register(name=name, toolset='vrc-'+generation,
                    schema=json.loads(json.dumps(schema)), handler=handler, scope=binding._scope)
            finally:
                entry = registry.snapshot_registration(name, scope=binding._scope)
                if entry is not None and entry.handler is handler:
                    binding._entries.append((name, entry))
            if entry is None or entry.handler is not handler:
                raise ValueError('candidate_registration_failed')
            schemas.append({'type':'function','function':schema})
        binding._schemas = json.dumps(schemas)
        binding._ready = True
        return binding
    except BaseException:
        await binding.close()
        raise
