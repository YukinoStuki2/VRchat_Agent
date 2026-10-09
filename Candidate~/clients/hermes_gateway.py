"""Manual Hermes gateway plugin controller. Import/register starts nothing.

pre_gateway_dispatch precedes Hermes auth, so BOTH explicit owner-route matching
and the live gateway authorization check are mandatory. No MCP tools or slash
handlers can claim offers. Only /vrc messages enter a separate new conversation.
"""
import asyncio
from pathlib import Path
import re
if __package__:
    from .hermes_chat import ChatHost, finish
else:
    from hermes_chat import ChatHost, finish


class GatewayPlugin:
    def __init__(self, ctx):
        self.ctx = ctx
        self.host = None
        self.runner = None
        self.pending = set()
        self.stop = None
        self.ready = None
        self.closing = False
        self.failed = False
        self.routes = set()
        self.path = None
        self.include = ()
        owners = ctx.get_config('owners', [])
        include = ctx.get_config('include', [])
        path = ctx.get_config('socket', '')
        if (type(owners) is list and 1 <= len(owners) <= 8 and type(include) is list
                and 1 <= len(include) <= 64 and all(type(n) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', n) for n in include)
                and len(set(include)) == len(include) and type(path) is str and Path(path).is_absolute()):
            for owner in owners:
                if (type(owner) is not dict or set(owner) != {'platform','user','chat','profile','thread'}
                        or any(type(owner[k]) is not str or not owner[k] for k in ('platform','user','chat'))
                        or any(owner[k] is not None and (type(owner[k]) is not str or not owner[k]) for k in ('profile','thread'))):
                    self.routes.clear()
                    break
                self.routes.add(tuple(owner[k] for k in ('platform','user','chat','profile','thread')))
            # One private receiver is one operator, not a cross-user offer queue.
            if len({(r[0], r[1], r[3]) for r in self.routes}) != 1:
                self.routes.clear()
            self.path = Path(path)
            self.include = tuple(include)
        ctx.register_hook('pre_gateway_dispatch', self.dispatch)
        ctx.on_unload(self.request_close)

    def dispatch(self, *, event, gateway, **unused):
        text = getattr(event, 'text', '')
        if type(text) is not str:
            return None
        command, _, args = text.strip().partition(' ')
        reset = command.lower() in ('/stop','/new','/reset')
        if command.lower() != '/vrc' and not reset:
            return None
        skipped = None if reset else {'action':'skip', 'reason':'candidate_private_command'}
        source = getattr(event, 'source', None)
        if self.closing or source is None:
            return skipped
        try:
            identity = source.to_dict()
            # Hermes omits false-valued profile fields; do not turn an invalid
            # empty profile into the authorized default (None) route.
            if identity.get('profile') != getattr(source, 'profile'):
                return skipped
            route = (identity['platform'], identity['user_id'], identity['chat_id'],
                     identity.get('profile'), identity['thread_id'])
        except Exception:
            return skipped  # incomplete/failed source serialization grants nothing
        if (route not in self.routes or source.chat_type != 'dm' or source.is_bot
                or source.profile_route_rejected
                or getattr(event, 'user_id', None) not in (None, source.user_id)):
            return skipped
        try:
            if not gateway._is_user_authorized_for_source(source):
                return skipped
            asyncio.get_running_loop()  # reviewed hook runs on gateway caller thread
            if self.host is not None and (reset or args == '停止'):
                self.host.request_stop(route)
            if reset:
                return None
            if len(self.pending) >= 8:
                return skipped
            task = self.ctx.spawn_task(self._request(route, args, source, event.message_id, gateway),
                                       name='candidate-command')
            self.pending.add(task)
            task.add_done_callback(self.pending.discard)
        except Exception:
            self.failed = True
        return skipped

    async def _serve(self):
        try:
            async with ChatHost(self.path, include=self.include) as host:
                self.host = host
                self.ready.set()
                try:
                    async with asyncio.timeout(3600):
                        await self.stop.wait()
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            if not self.closing:
                self.failed = True
            raise
        except BaseException:
            self.failed = True
            raise
        finally:
            self.host = None
            self.ready.set()

    async def _stop_host(self):
        if self.stop is not None:
            self.stop.set()
        if self.runner is not None:
            try:
                results = await finish(asyncio.gather(self.runner, return_exceptions=True))
                if any(isinstance(value, BaseException) and not
                       (isinstance(value, asyncio.CancelledError) and self.closing) for value in results):
                    raise RuntimeError('candidate_plugin_cleanup_failed')
            except BaseException:
                self.failed = True
                raise
            finally:
                if self.runner.done():
                    self.runner = None

    async def _request(self, route, args, source, message_id, gateway):
        adapter = gateway._adapter_for_source(source)
        if adapter is None:
            return
        async def reply(text):
            result = await adapter.send(source.chat_id, text, reply_to=message_id,
                metadata=gateway._thread_metadata_for_source(source, message_id))
            if not result.success:
                raise RuntimeError('candidate_reply_failed')
        try:
            if self.closing or not gateway._is_user_authorized_for_source(source):
                return
            action = args.split(' ', 1)[0]
            if args == '开始':
                if self.failed:
                    await reply('清理或启动未确认；入口保持关闭，需本地检查。')
                    return
                if self.runner is None:
                    self.stop = asyncio.Event()
                    self.ready = asyncio.Event()
                    self.runner = self.ctx.spawn_task(self._serve(), name='candidate-receiver')
                await self.ready.wait()
                if self.host is None:
                    await self._stop_host()
                    raise RuntimeError('candidate_receiver_unavailable')
                await reply('接收入口已开启，最长一小时；请在 Unity 手动连接，然后 /vrc 列表。没有授予任务权限。')
            elif self.host is None:
                await reply('入口未开启；使用 /vrc 开始。')
            elif args == '关闭':
                if any(key != route for key in self.host.chats):
                    await reply('其他聊天仍有绑定；只能用 /vrc 停止 关闭本聊天。')
                    return
                await self._stop_host()
                await reply('接收入口已关闭；所有本轮会话已结束，权限不恢复。')
            else:
                options = {}
                if action == '绑定':
                    model, runtime = gateway._resolve_session_agent_runtime(source=source)
                    options = {**runtime, 'model':model, 'quiet_mode':True, 'verbose_logging':False,
                               'fallback_model':None, 'max_iterations':20,
                               'platform':route[0], 'user_id':route[1], 'chat_id':route[2], 'chat_type':'dm'}
                await self.host.command(route, args, options=options, reply=reply)
        except asyncio.CancelledError:
            raise
        except Exception:
            try:
                await reply('候选操作失败；不会自动重试。若清理未确认，请在 Unity 停止连接。')
            except Exception:
                pass  # platform failure is not permission to send elsewhere

    def request_close(self):
        self.closing = True
        if self.host is not None:
            for route in tuple(self.host.chats):
                self.host.request_stop(route)
        if self.stop is not None:
            self.stop.set()

    async def close(self):
        self.request_close()
        try:
            await self._stop_host()
        finally:
            if self.pending:
                await finish(asyncio.ensure_future(asyncio.gather(*tuple(self.pending), return_exceptions=True)))
