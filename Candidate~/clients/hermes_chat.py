"""Opt-in per-chat native conversations; no live gateway-agent mutation.

Caller authenticates the platform event before command(). Route identifiers are
trusted host inputs, never tool/model arguments. No chat command grants editing.
"""
import asyncio
from dataclasses import dataclass, field
import re
import secrets
if __package__:
    from .hermes_handoff import Receiver
    from .hermes_conversation import bound_conversation
else:
    from hermes_handoff import Receiver
    from hermes_conversation import bound_conversation


async def finish(task):
    """Do not abandon owned shutdown on repeated cancellation."""
    cancelled = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            cancelled = exc
    result = task.result()
    if cancelled is not None:
        raise cancelled
    return result


@dataclass
class Chat:
    offer: str
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    agent: object = None
    binding: object = None
    task: object = None
    turn: object = None
    history: list = field(default_factory=list)


class ChatHost:
    def __init__(self, path, *, include):
        self.receiver = Receiver(path)
        self.include = include
        self.chats = {}
        self.closing = False
        self.cleanup_failed = False

    async def __aenter__(self):
        await self.receiver.__aenter__()
        return self

    async def __aexit__(self, *unused):
        self.closing = True
        await finish(asyncio.create_task(self._close()))

    async def _close(self):
        for chat in tuple(self.chats.values()):
            chat.stop.set()
        results = await asyncio.gather(*(c.task for c in tuple(self.chats.values())), return_exceptions=True)
        try:
            await self.receiver.__aexit__(None, None, None)
        finally:
            if self.cleanup_failed or any(isinstance(r, BaseException) for r in results):
                raise RuntimeError('candidate_chat_cleanup_failed')

    async def _session(self, route, chat, options):
        binding = None
        try:
            binding = await self.receiver.claim(chat.offer,
                conversation_id='vrc-' + secrets.token_hex(24), include=self.include)
            chat.binding = binding
            if chat.stop.is_set():
                return
            async with bound_conversation(binding, options=options) as agent:
                chat.agent = agent
                chat.ready.set()
                try:
                    while not chat.stop.is_set() and not binding._closed:
                        await asyncio.sleep(.02)
                finally:
                    chat.stop.set()
                    try:
                        await self.receiver.withdraw(chat.offer)  # revoke before joining model thread
                    finally:
                        if chat.turn is not None and not chat.turn.done():
                            agent.interrupt('candidate_stopped')
                            await finish(chat.turn)
        finally:
            try:
                if binding is not None:
                    await self.receiver.withdraw(chat.offer)
            except BaseException:
                self.cleanup_failed = True
                raise
            finally:
                chat.ready.set()
                chat.history.clear()
                if self.chats.get(route) is chat:
                    self.chats.pop(route)

    def request_stop(self, route):
        chat = self.chats.get(route)
        if chat is not None:
            chat.stop.set()
            if chat.binding is not None:
                chat.binding._begin_close()

    async def command(self, route, text, *, options, reply):
        if self.closing or self.cleanup_failed:
            await reply('入口已关闭或清理未确认；没有恢复权限。')
            return
        action, _, argument = text.strip().partition(' ')
        chat = self.chats.get(route)
        if action == '列表':
            offers = self.receiver.offers()
            await reply('\n'.join(f"{o['id']} · {o['project']} · {'已绑定' if o['claimed'] else '待绑定'}" for o in offers) or '没有待绑定连接。')
        elif action == '绑定' and re.fullmatch('[0-9a-f]{32}', argument):
            if chat is not None:
                await reply('本聊天已有连接；先停止，不能替换活跃会话。')
                return
            chat = Chat(argument)
            self.chats[route] = chat
            chat.task = asyncio.create_task(self._session(route, chat, options))
            await chat.ready.wait()
            if chat.task.done():
                try:
                    chat.task.result()
                except Exception:
                    await reply('绑定失败；未授权编辑。')
                    return
            await reply('已绑定新的专用会话；未授予任务权限。用 /vrc 问 内容 开始，/vrc 停止 关闭。')
        elif action == '停止' and not argument:
            if chat is None:
                await reply('本聊天没有活跃连接。')
                return
            chat.stop.set()
            try:
                await finish(chat.task)
            except Exception:
                self.cleanup_failed = True
                await reply('已请求撤权，但清理未确认；禁止重新绑定。')
                return
            await reply('已停止并关闭本轮连接；不回退文件，不恢复权限。')
        elif action == '问' and argument and chat is not None and chat.agent is not None and not chat.stop.is_set():
            if chat.turn is not None and not chat.turn.done():
                await reply('本会话正在执行；不会并发发送或自动重试。')
                return
            chat.turn = asyncio.create_task(asyncio.to_thread(chat.agent.run_conversation,
                user_message=argument, conversation_history=chat.history, task_id=chat.agent.session_id))
            try:
                result = await asyncio.shield(chat.turn)
                if chat.stop.is_set():
                    return
                chat.history = result.get('messages', [])
                await reply(result.get('final_response') or '本轮未得到有效回复；不会自动重试。')
            except BaseException:
                chat.stop.set()
                await finish(chat.task)
                raise
        else:
            await reply('指令：/vrc 列表、/vrc 绑定 连接编号、/vrc 问 内容、/vrc 停止。')
