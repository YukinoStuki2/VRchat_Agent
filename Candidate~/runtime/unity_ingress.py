"""Candidate-only native Unity ingress; not a server identity/bootstrap proof.

Reuses MCP BearerAuthBackend and the pinned PluginHub protocol. Installed CLI
must not enable this until a trusted local owner supplies transport identity.
"""
import asyncio
import json
import time

from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
from starlette.requests import HTTPConnection
from transport.plugin_hub import PluginHub


class UnityIngress:
    def __init__(self, verifier, runtime):
        self.backend = BearerAuthBackend(verifier)
        self.runtime = runtime
        self.used = False
        self.live = False
        self.session_id = None
        self.principal = None
        self.expiry = 0
        self.deadline = 0
        self._reload = None
        self._reload_timer = None
        self._close_event = None

    def reload_pending(self):
        return self._reload is not None

    def suspend_reload(self, ticket):
        barrier = self.runtime._reload_barrier
        if (self._reload is not None or not self.active() or self.session_id is None
                or barrier is None or barrier['ticket'] is not ticket
                or barrier['connection'] != self.session_id):
            return False
        barrier['deadline'] = min(barrier['deadline'], self.deadline,
            time.monotonic() + max(0, self.expiry-time.time()))
        if not self.runtime.reload_is_frozen():
            return False
        self._reload = {'ticket': ticket, 'old': self.session_id, 'principal': self.principal,
            'expiry': self.expiry, 'deadline': self.deadline, 'phase': 'awaiting_close', 'closed': False}
        self._reload_timer = asyncio.get_running_loop().call_later(
            max(0, barrier['deadline']-time.monotonic()), self.runtime.cancel_reload_barrier)
        return True

    def expected_reload_close(self, connection):
        state = self._reload
        return (state is not None and state['old'] == connection
                and state['phase'] in ('suspended', 'permitted', 'connecting', 'reattached'))

    def allow_reload_reattach(self, ticket):
        # Called ONLY by the surviving local owner after OS peer reauthentication.
        # Knowledge of a session ID, JWT or serialized history is insufficient.
        state = self._reload
        if (state is None or state['ticket'] is not ticket or state['phase'] != 'suspended'
                or not state['closed'] or self.live or not self.runtime.reload_is_frozen()):
            return False
        state['phase'] = 'permitted'
        return True

    def reload_committable(self, ticket, connection):
        state = self._reload
        return (state is not None and state['ticket'] is ticket and state['phase'] == 'reattached'
                and self.session_id == connection and connection != state['old'] and self.active())

    def _cancel_timer(self):
        if self._reload_timer is not None:
            self._reload_timer.cancel()
            self._reload_timer = None

    def finish_reload(self, ticket):
        if self._reload is not None and self._reload['ticket'] is ticket:
            self._cancel_timer()
            self._reload = None

    def cancel_reload(self):
        self._cancel_timer()
        if self._reload is not None:
            self._reload = None
            self.live = False
            if self._close_event is not None:
                self._close_event.set()

    def active(self):
        return self.live and time.time() < self.expiry and time.monotonic() < self.deadline

    def allows(self, session):
        return (self.active() and session.session_id == self.session_id
                and session.user_id == self.principal)

    def revoke(self, expected=False):
        self.live = False
        if (expected and self._reload is not None and self._reload['phase'] == 'suspended'
                and self.runtime.reload_is_frozen()):
            return
        self.runtime.cancel_reload_barrier()
        self._reload = None
        if self.session_id is not None:
            self.runtime.connection_closed(self.session_id)

    async def __call__(self, scope, receive, send):
        identity = await self.backend.authenticate(HTTPConnection(scope))
        state = self._reload
        if identity is None:
            await send({'type': 'websocket.close', 'code': 1008})
            return
        credentials, user = identity
        expiry = user.access_token.expires_at
        deadline = time.monotonic() + max(0, expiry - time.time())
        if self.used:
            if (state is None or state['phase'] != 'permitted' or not self.runtime.reload_is_frozen()
                    or user.access_token.client_id != state['principal'] or expiry != state['expiry']):
                await send({'type': 'websocket.close', 'code': 1008})
                return
            state['phase'] = 'connecting'  # Consume exactly once before any await.
            self.session_id = None
            deadline = min(deadline, state['deadline'])
        self.used = True
        self.live = True
        self.principal = user.access_token.client_id
        self.expiry, self.deadline = expiry, deadline
        scope = dict(scope)
        scope['auth'], scope['user'] = credentials, user
        scope['state'] = {**scope.get('state', {}), 'user_id': user.access_token.client_id}
        normal_reload_close = False
        close_event = asyncio.Event()
        self._close_event = close_event
        async def checked_receive():
            nonlocal normal_reload_close
            try:
                remaining = min(expiry - time.time(), deadline - time.monotonic())
                if remaining <= 0:
                    raise TimeoutError
                incoming = asyncio.create_task(receive())
                revoked = asyncio.create_task(close_event.wait())
                try:
                    done, _ = await asyncio.wait((incoming, revoked), timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED)
                    if revoked in done or incoming not in done:
                        raise TimeoutError
                    message = incoming.result()
                finally:
                    for task in (incoming, revoked):
                        if not task.done(): task.cancel()
                    await asyncio.gather(incoming, revoked, return_exceptions=True)
            except TimeoutError:
                self.revoke()
                await send({'type':'websocket.close', 'code':1008})
                return {'type':'websocket.disconnect', 'code':1008}
            if message['type'] == 'websocket.receive':
                try:
                    if not self.active():
                        raise ValueError('unity_credential_expired')
                    data = json.loads(message.get('text') or message.get('bytes') or '')
                    if not isinstance(data, dict):
                        raise ValueError('object_required')
                    kind = data.get('type')
                    if kind == 'register':
                        if self.session_id is not None or data.get('project_hash') != self.runtime.project_id:
                            raise ValueError('wrong_or_repeated_registration')
                    elif kind not in ('pong', 'command_result') or self.session_id is None:
                        raise ValueError('message_not_enabled')
                    if kind == 'pong' and data.get('session_id') not in (None, self.session_id):
                        raise ValueError('foreign_pong')
                    if data.get('type') == 'command_result':
                        command_id = data.get('id')
                        pending = PluginHub._pending.get(command_id) if type(command_id) is str else None
                        if self.session_id is None or pending is None or pending.get('session_id') != self.session_id:
                            raise ValueError('foreign_command')
                except (ValueError, TypeError):
                    self.revoke()
                    await send({'type':'websocket.close', 'code':1008})
                    return {'type':'websocket.disconnect', 'code':1008}
            if message['type'] == 'websocket.disconnect':
                state = self._reload
                if (message.get('code') == 1000 and state is not None and state['phase'] == 'awaiting_close'
                        and self.runtime.reload_is_frozen()):
                    state['phase'] = 'suspended'
                    normal_reload_close = True
                self.revoke(expected=normal_reload_close)
            return message
        async def checked_send(message):
            if message['type'] == 'websocket.send':
                if not self.active():
                    raise PermissionError('unity_credential_expired')
                data = json.loads(message.get('text') or message.get('bytes') or '')
                if data.get('type') == 'registered':
                    self.session_id = data['session_id']
                    state = self._reload
                    if state is not None and state['phase'] == 'connecting':
                        if self.session_id == state['old'] or not self.runtime.reload_is_frozen():
                            self.revoke()
                            raise PermissionError('reload_binding_changed')
                        state['phase'] = 'reattached'
            await send(message)
        try:
            await PluginHub(scope, checked_receive, checked_send)
        finally:
            self.revoke(expected=normal_reload_close)
            if normal_reload_close and self._reload is not None:
                self._reload['closed'] = True
            if self._close_event is close_event:
                self._close_event = None
