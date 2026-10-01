"""Opt-in Linux SSH-command stdio relay to one same-UID private receiver.

No SSH account provisioning, credential files, shell, client registration or
model call. The installed absolute socket path is a local operator argument.
Use a dedicated restricted SSH account policy; UID is not workstation identity.
"""
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import sys
import time


def line(fd, *, limit, deadline):
    data = bytearray()
    while len(data) < limit:
        remaining = deadline-time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError()
        value = os.read(fd, 1)
        if not value:
            return bytes(data)
        data += value
        if value == b'\n':
            return bytes(data)
    raise ValueError('candidate_frame_limit')


def emit(value):
    sys.stdout.write(json.dumps(value,separators=(',',':'))+'\n')
    sys.stdout.flush()


def relay(path):
    if os.name != 'posix' or not hasattr(socket,'SO_PEERCRED'):
        raise ValueError()
    if not all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in (0,1)):
        raise ValueError()
    target=Path(path)
    parent=target.parent.lstat(); info=target.lstat()
    if (not target.is_absolute() or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.getuid() or parent.st_mode & 0o077
            or not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError()
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(5)
        stream.connect(str(target))
        if struct.unpack('3i',stream.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1] != os.getuid():
            raise ValueError()
        first=line(0,limit=32768,deadline=time.monotonic()+5)
        if not first.endswith(b'\n'):
            raise ValueError()
        stream.sendall(first)
        first=b''
        reply=json.loads(line(stream.fileno(),limit=256,deadline=time.monotonic()+6))
        if (type(reply) is not dict or set(reply) != {'kind','id'} or reply['kind'] != 'offered'
                or type(reply['id']) is not str or re.fullmatch('[0-9a-f]{32}',reply['id']) is None):
            raise ValueError()
        emit({'kind':'offered','id':reply['id']})
        stop=False; deadline=time.monotonic()+3610
        while time.monotonic()<deadline:
            ready=select.select([stream] if stop else [stream,0],[],[],max(0,deadline-time.monotonic()))[0]
            if stream in ready:
                reply=json.loads(line(stream.fileno(),limit=256,deadline=time.monotonic()+5))
                if (type(reply) is not dict or set(reply) != {'kind','clean'}
                        or reply['kind'] != 'closed' or type(reply['clean']) is not bool):
                    raise ValueError()
                emit({'kind':'closed','clean':reply['clean']})
                return 0 if reply['clean'] else 1
            if 0 in ready:
                control=line(0,limit=16,deadline=time.monotonic()+5)
                if control not in (b'',b'stop\n'):
                    raise ValueError()
                stream.sendall(b'stop\n')
                stop=True; deadline=time.monotonic()+40
        raise TimeoutError()


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError()
        return relay(sys.argv[1])
    except BaseException:
        try:
            emit({'kind':'closed','clean':False})
        except BaseException:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
