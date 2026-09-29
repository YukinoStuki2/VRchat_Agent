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

    def active(self):
        return self.live and time.time() < self.expiry and time.monotonic() < self.deadline

    def allows(self, session):
        return (self.active() and session.session_id == self.session_id
                and session.user_id == self.principal)

    def revoke(self):
        self.live = False
        if self.session_id is not None:
            self.runtime.connection_closed(self.session_id)

    async def __call__(self, scope, receive, send):
        identity = await self.backend.authenticate(HTTPConnection(scope))
        if identity is None or self.used:
            await send({'type': 'websocket.close', 'code': 1008})
            return
        self.used = True  # No await between check and consume; new local run required.
        credentials, user = identity
        expiry = user.access_token.expires_at
        deadline = time.monotonic() + max(0, expiry - time.time())
        self.live = True
        self.principal = user.access_token.client_id
        self.expiry, self.deadline = expiry, deadline
        scope = dict(scope)
        scope['auth'], scope['user'] = credentials, user
        scope['state'] = {**scope.get('state', {}), 'user_id': user.access_token.client_id}
        async def checked_receive():
            try:
                remaining = min(expiry - time.time(), deadline - time.monotonic())
                if remaining <= 0:
                    raise TimeoutError
                message = await asyncio.wait_for(receive(), remaining)
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
                self.revoke()
            return message
        async def checked_send(message):
            if message['type'] == 'websocket.send':
                if not self.active():
                    raise PermissionError('unity_credential_expired')
                data = json.loads(message.get('text') or message.get('bytes') or '')
                if data.get('type') == 'registered':
                    self.session_id = data['session_id']
            await send(message)
        try:
            await PluginHub(scope, checked_receive, checked_send)
        finally:
            self.revoke()
