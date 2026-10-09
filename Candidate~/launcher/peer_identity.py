"""Retained OS process identity for local reload rendezvous.

No PID/port discovery, process termination, credentials or authority deserialization.
The caller must capture the intended PID from its original owned process/parent.
This is not protection from same-user injection, debuggers or administrators.
"""
import ctypes as C
import os
from pathlib import Path
import select
import sys


class PeerProcess:
    def __init__(self, pid):
        if type(pid) is not int or not 1 < pid <= 0xffffffff:
            raise ValueError('invalid_peer_pid')
        self.pid, self._handle, self._api = pid, None, None
        try:
            if os.name == 'nt':
                from .windows_processes import WinAPI, HANDLE
                self._api = WinAPI()
                self._handle = self._api.w.OpenProcess(0x00101000, False, pid)
                fn = self._api.k.GetProcessTimes
                fn.argtypes = [HANDLE] + [C.POINTER(C.c_uint64)] * 4
                fn.restype = C.c_int
                created, exited, kernel, user = [C.c_uint64() for _ in range(4)]
                self._api.checked(fn(self._handle, C.byref(created), C.byref(exited), C.byref(kernel), C.byref(user)))
                self.created = created.value
            elif sys.platform == 'linux' and hasattr(os, 'pidfd_open'):
                self._handle = os.pidfd_open(pid)
                # /proc's comm can contain spaces and ')'; the final ') ' begins
                # the remaining numeric fields. The pidfd pins lifetime throughout.
                raw = Path('/proc') / str(pid) / 'stat'
                self.created = int(raw.read_bytes().rsplit(b') ', 1)[1].split()[19])
            else:
                raise OSError('peer_identity_platform_unsupported')
            if not self.alive() or self.created <= 0:
                raise OSError('peer_process_not_alive')
        except BaseException:
            self.close()
            raise

    @property
    def identity(self):
        return self.pid, self.created

    def alive(self):
        if self._handle is None:
            return False
        if self._api is not None:
            return self._api.parent_alive(self._handle)
        return not select.select([self._handle], [], [], 0)[0]

    def matches_channel(self, channel, *, server):
        """Check the kernel peer BEFORE receiving/sending any authority bytes.

        Unix credentials describe the connecting process; Windows queries the
        named-pipe endpoint. Never accept a PID supplied inside a message.
        """
        if type(server) is not bool or not self.alive():
            return False
        try:
            if self._api is not None:
                from .windows_processes import HANDLE, DWORD
                fn = getattr(self._api.k, 'GetNamedPipeClientProcessId' if server else 'GetNamedPipeServerProcessId')
                fn.argtypes = [HANDLE, C.POINTER(DWORD)]
                fn.restype = C.c_int
                peer = DWORD()
                self._api.checked(fn(int(channel), C.byref(peer)))
                pid = peer.value
            else:
                import socket, struct
                if not isinstance(channel, socket.socket) or channel.family != socket.AF_UNIX:
                    return False
                pid, uid, _ = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    return False
            return pid == self.pid and self.alive()
        except (OSError, TypeError, ValueError):
            return False

    def close(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            if self._api is not None:
                self._api.close_handle(handle)
            else:
                os.close(handle)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
