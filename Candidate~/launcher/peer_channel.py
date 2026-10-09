"""One-shot OS-local bytes for a held peer identity; not an approval endpoint.

No discovery, pickle, tokens, file persistence, TCP fallback or reconnect. Callers
must supply the process captured at the original trusted spawn and an absolute
monotonic run deadline (at most one hour, NOT task authority). Unix uses an abstract socket; Windows uses a current-SID ACL,
first-instance/remote-rejecting named pipe with cancelled/drained overlapped I/O.
Close only after the synchronous I/O worker has returned (signal stop to cancel).
"""
import math
import os
import re
import secrets
import socket
import struct
import threading
import time

from .peer_identity import PeerProcess

MAX_FRAME = 4 * 1024 * 1024


def _remaining(deadline, stop, peer):
    remaining = deadline - time.monotonic()
    if (not math.isfinite(remaining) or remaining <= 0 or stop.is_set()):
        raise TimeoutError('local_channel_cancelled_or_expired')
    if not peer.alive():
        raise PermissionError('local_peer_exited')
    return min(remaining, .02)


def _validate(peer, deadline, stop):
    if type(peer) is not PeerProcess or type(deadline) not in (int, float):
        raise ValueError('local_channel_identity_required')
    if not math.isfinite(deadline) or not 0 < deadline-time.monotonic() <= 3600:
        raise ValueError('local_channel_deadline_invalid')
    _remaining(deadline, stop, peer)


def _address(value):
    if type(value) is not str or re.fullmatch(r'vrchat-local-[0-9a-f]{48}', value) is None:
        raise ValueError('local_channel_locator_invalid')
    return '\\\\.\\pipe\\' + value if os.name == 'nt' else '\0' + value


def _win_io(handle, invoke, peer, deadline, stop):
    """One I/O, issued and cancelled on this same worker; no blocking flush."""
    import pywintypes, win32event, win32file
    event = win32event.CreateEvent(None, True, False, None)
    operation = pywintypes.OVERLAPPED()
    operation.hEvent = event
    issued = False
    try:
        _remaining(deadline, stop, peer)
        result = invoke(operation)
        if result == 535:  # ConnectNamedPipe: client arrived before accept.
            return None, 0
        issued = True
        while True:
            remaining = _remaining(deadline, stop, peer)
            wait = win32event.WaitForSingleObject(event, max(1, int(remaining * 1000)))
            if wait == 0:
                count = win32file.GetOverlappedResult(handle, operation, False)
                issued = False
                _remaining(deadline, stop, peer)
                return result, count
            if wait != 258:
                raise OSError('local_channel_wait_failed')
    except pywintypes.error as error:
        if error.winerror == 535 and not issued:
            return None, 0
        if error.winerror == 109:  # ERROR_BROKEN_PIPE
            raise EOFError('local_channel_closed') from None
        raise OSError('local_channel_io_failed') from None
    finally:
        try:
            if issued:
                try:
                    try:
                        win32file.CancelIo(handle)
                    except pywintypes.error as error:
                        if error.winerror != 1168:
                            raise
                finally:
                    # Even cancellation failure cannot free a pending buffer/event.
                    try:
                        win32file.GetOverlappedResult(handle, operation, True)
                    except pywintypes.error as error:
                        if error.winerror == 109:  # ERROR_BROKEN_PIPE
                            raise EOFError('local_channel_closed') from None
                        if error.winerror != 995:
                            raise OSError('local_channel_io_failed') from None
        finally:
            event.Close()


class PeerChannel:
    def __init__(self, handle, peer, deadline, stop, *, server):
        self._handle, self.peer = handle, peer
        self.deadline, self.stop = deadline, stop
        self.server = server
        self._lock = threading.Lock()
        try:
            _validate(peer, deadline, stop)
            if not peer.matches_channel(handle, server=server):
                raise PermissionError('local_channel_peer_mismatch')
        except BaseException:
            self.close()
            raise

    @classmethod
    def connect(cls, address, peer, *, deadline, stop=None):
        stop = threading.Event() if stop is None else stop
        _validate(peer, deadline, stop)
        address = _address(address)
        if os.name == 'nt':
            import win32file
            handle = win32file.CreateFile(address, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, win32file.FILE_FLAG_OVERLAPPED, None)
        else:
            handle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                handle.settimeout(_remaining(deadline, stop, peer))
                handle.connect(address)
            except BaseException:
                handle.close()
                raise
        return cls(handle, peer, deadline, stop, server=False)

    def _io(self, value, *, write):
        if self._handle is None or not self.peer.matches_channel(self._handle, server=self.server):
            raise PermissionError('local_channel_closed_or_foreign')
        while True:
            remaining = _remaining(self.deadline, self.stop, self.peer)
            if os.name == 'nt':
                import win32file
                if write:
                    _, count = _win_io(self._handle, lambda op: win32file.WriteFile(self._handle, value, op),
                        self.peer, self.deadline, self.stop)
                    return count
                buffer = win32file.AllocateReadBuffer(value)
                _, count = _win_io(self._handle, lambda op: win32file.ReadFile(self._handle, buffer, op),
                    self.peer, self.deadline, self.stop)
                return bytes(buffer[:count])
            self._handle.settimeout(remaining)
            try:
                return self._handle.send(value) if write else self._handle.recv(value)
            except socket.timeout:
                continue

    def send(self, payload):
        with self._lock:
            try:
                if type(payload) is not bytes or not 1 <= len(payload) <= MAX_FRAME:
                    raise ValueError('local_channel_frame_invalid')
                wire = memoryview(struct.pack('!I', len(payload)) + payload)
                while wire:
                    count = self._io(wire[:65536], write=True)
                    if count <= 0:
                        raise EOFError('local_channel_closed')
                    wire = wire[count:]
                _remaining(self.deadline, self.stop, self.peer)
            except BaseException:
                self.close()
                raise

    def receive(self):
        with self._lock:
            try:
                def exact(count):
                    data = bytearray()
                    while len(data) < count:
                        part = self._io(min(65536, count-len(data)), write=False)
                        if not part:
                            raise EOFError('local_channel_closed')
                        data.extend(part)
                    return bytes(data)
                length = struct.unpack('!I', exact(4))[0]
                if not 1 <= length <= MAX_FRAME:
                    raise ValueError('local_channel_frame_invalid')
                payload = exact(length)
                _remaining(self.deadline, self.stop, self.peer)
                return payload
            except BaseException:
                self.close()
                raise

    def close(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.Close() if os.name == 'nt' else handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class PeerListener:
    def __init__(self):
        self.address = 'vrchat-local-' + secrets.token_hex(24)
        self._handle = None
        self.used = False
        if os.name == 'nt':
            import pywintypes, win32api, win32file, win32pipe, win32security
            token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
            try:
                sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, 1)[0])
            finally:
                token.Close()
            attributes = pywintypes.SECURITY_ATTRIBUTES()
            attributes.bInheritHandle = False
            attributes.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
                'D:P(A;;GA;;;' + sid + ')(A;;GA;;;SY)', 1)
            self._handle = win32pipe.CreateNamedPipe(_address(self.address),
                win32pipe.PIPE_ACCESS_DUPLEX | 0x00080000 | win32file.FILE_FLAG_OVERLAPPED,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | 0x8,
                1, 65536, 65536, 0, attributes)
        else:
            handle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                handle.bind(_address(self.address))
                handle.listen(1)
                self._handle = handle
            except BaseException:
                handle.close()
                raise

    @property
    def closed(self):
        return self._handle is None

    def accept(self, peer, *, deadline, stop=None):
        if self.used or self.closed:
            raise PermissionError('local_listener_consumed')
        self.used = True
        stop = threading.Event() if stop is None else stop
        try:
            _validate(peer, deadline, stop)
            if os.name == 'nt':
                import win32pipe
                _win_io(self._handle, lambda op: win32pipe.ConnectNamedPipe(self._handle, op), peer, deadline, stop)
                handle, self._handle = self._handle, None
            else:
                while True:
                    self._handle.settimeout(_remaining(deadline, stop, peer))
                    try:
                        handle, _ = self._handle.accept()
                        break
                    except socket.timeout:
                        continue
            return PeerChannel(handle, peer, deadline, stop, server=True)
        finally:
            self.close()

    def close(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.Close() if os.name == 'nt' else handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
