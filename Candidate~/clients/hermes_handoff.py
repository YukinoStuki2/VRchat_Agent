"""Linux same-UID credential handoff. Opt-in, memory-only, no gateway install.

An authenticated SSH stdio relay may reach this private UNIX socket. Peer UID
proves a local account, NOT the SSH key, workstation, software brand or a human.
That account, its SSH access policy and every process of that UID are trusted.
The host alone selects the conversation and tool allowlist. No tool can claim.
"""
import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import secrets
import re
import socket
import stat
import struct
import time


def _unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('candidate_duplicate_field')
    return result


@dataclass(slots=True)
class Offer:
    project: str
    document: dict = field(repr=False)
    binding: object = field(default=None, repr=False)
    claiming: object = field(default=None, repr=False)
    clean: bool = True
    source_task: object = field(default=None, repr=False)


class Receiver:
    def __init__(self, path):
        self.path = Path(path)
        self._server = None
        self._offers = {}
        self._tasks = set()
        self._identity = None
        self._closing = False
        self._cleanup_failed = False
        self._close_task = None

    async def __aenter__(self):
        info = self.path.parent.lstat()
        if (os.name != 'posix' or not hasattr(socket, 'SO_PEERCRED') or
                not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('candidate_private_directory_required')
        if self.path.exists() or self.path.is_symlink():
            raise ValueError('candidate_receiver_path_occupied')
        self._server = await asyncio.start_unix_server(self._receive, path=str(self.path),
                                                       limit=32768, start_serving=False)
        try:
            info = self.path.lstat(); self._identity = (info.st_dev, info.st_ino)
            self.path.chmod(0o600)
            await self._server.start_serving()
            return self
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, *unused):
        if self._close_task is None:
            self._closing = True
            self._close_task = asyncio.create_task(self._close())
        cancelled = None
        while not self._close_task.done():
            try:
                await asyncio.shield(self._close_task)
            except asyncio.CancelledError as exc:
                cancelled = exc
        self._close_task.result()
        if cancelled is not None:
            raise cancelled

    async def _close(self):
        if self._server is not None:
            self._server.close(); await self._server.wait_closed()
        for task in tuple(self._tasks):
            task.cancel()
        await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        if self._identity is not None:
            try:
                info = self.path.lstat()
                if (info.st_dev, info.st_ino) == self._identity:
                    self.path.unlink()
            except FileNotFoundError:
                pass

        if self._cleanup_failed:
            raise RuntimeError('candidate_receiver_cleanup_failed')

    def offers(self):
        return [{'id':key, 'project':value.project, 'claimed':value.binding is not None or value.claiming is not None}
                for key, value in self._offers.items()]

    async def withdraw(self, offer_id):
        """Trusted host stop; terminal removal and source cleanup, no remote grant."""
        offer = self._offers.pop(offer_id, None)
        if offer is None:
            return False
        task = offer.source_task
        task.cancel()
        cancelled = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                cancelled = exc
        task.result()
        if self._cleanup_failed:
            raise RuntimeError('candidate_receiver_cleanup_failed')
        if cancelled is not None:
            raise cancelled
        return True

    async def claim(self, offer_id, *, conversation_id, include):
        if __package__:
            from .hermes_connection import connect
            from .hermes_binding import bind
        else:
            from hermes_connection import connect
            from hermes_binding import bind
        from tools.registry import registry
        offer = self._offers.get(offer_id)
        if offer is None or offer.claiming or offer.binding is not None:
            raise ValueError('candidate_offer_unavailable')
        offer.claiming = asyncio.current_task()
        peer = None
        try:
            peer = await connect(**{k:v for k,v in offer.document.items()
                                    if k in ('port','server_port','certificate','pin','bearer','expires_at')})
            if self._offers.get(offer_id) is not offer:
                raise ValueError('candidate_offer_withdrawn')
            async with asyncio.timeout(8):
                status = await peer.session.call_tool('agent_status', {})
            data = status.structured_content
            if (status.is_error or type(data) is not dict or data.get('success') is not True
                    or type(data.get('data')) is not dict or data['data'].get('read_only') is not True
                    or data['data'].get('project_id') != offer.project):
                raise ValueError('candidate_project_unverified')
            adopted, peer = peer, None  # bind owns failure cleanup as well
            binding = await bind(adopted, registry, conversation_id=conversation_id, include=include)
            if self._offers.get(offer_id) is not offer:
                await binding.close()
                raise ValueError('candidate_offer_withdrawn')
            offer.binding = binding
            return binding
        except BaseException as exc:
            was_live = self._offers.pop(offer_id, None) is offer
            if not isinstance(exc, asyncio.CancelledError):
                offer.clean = False
            if was_live:
                offer.source_task.cancel()
            if peer is not None:
                try:
                    await peer.shutdown()
                except BaseException:
                    offer.clean = False
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError('candidate_claim_failed') from None
        finally:
            offer.claiming = None

    async def _receive(self, reader, writer):
        task = asyncio.current_task(); self._tasks.add(task)
        key = None; offer = None; clean = True
        try:
            if self._closing or len(self._tasks) > 8:
                raise ValueError('candidate_receiver_capacity')
            uid = struct.unpack('3i', writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
            if uid != os.getuid():
                raise ValueError('candidate_local_user_required')
            raw = await asyncio.wait_for(reader.readline(),5)
            doc = json.loads(raw, object_pairs_hook=_unique)
            fields = {'version','project','role','port','server_port','certificate','pin','bearer','expires_at'}
            if (type(doc) is not dict or set(doc) != fields or type(doc['version']) is not int
                    or doc['version'] != 1 or doc['role'] != 'hermes'
                    or type(doc['project']) is not str
                    or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', doc['project']) is None):
                raise ValueError('candidate_offer_invalid')
            if __package__:
                from .hermes_connection import validate_handoff
            else:
                from hermes_connection import validate_handoff
            validate_handoff(**{k:v for k,v in doc.items()
                                if k in ('port','server_port','certificate','pin','bearer','expires_at')})
            key = secrets.token_hex(16)
            offer = Offer(doc['project'],doc,source_task=task)
            self._offers[key] = offer
            writer.write(json.dumps({'kind':'offered','id':key}).encode()+b'\n'); await writer.drain()
            try:
                control = await asyncio.wait_for(reader.readline(), max(0,doc['expires_at']-time.time()))
                if control not in (b'', b'stop\n'):
                    raise ValueError('candidate_control_invalid')
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            pass
        except Exception:
            clean = False
        finally:
            cleanup=asyncio.create_task(self._finish(key,offer,writer,clean))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    pass  # Source owns cleanup even if the receiver is also closing.
            try:
                cleanup.result()
            finally:
                self._tasks.discard(task)

    async def _finish(self,key,offer,writer,clean):
        if key is not None:
            self._offers.pop(key,None)
        if offer is not None:
            if offer.claiming is not None:
                claim = offer.claiming
                claim.cancel()
                await asyncio.gather(claim, return_exceptions=True)
            clean = clean and offer.clean
            if offer.binding is not None:
                try:
                    await offer.binding.close()
                except BaseException:
                    clean = False
                    self._cleanup_failed = True
            offer.document.clear()
        try:
            writer.write(json.dumps({'kind':'closed','clean':clean}).encode()+b'\n')
            await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
