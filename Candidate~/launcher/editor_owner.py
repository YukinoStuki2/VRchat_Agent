"""Private redirected-pipe entry, created and owned by the local editor process.

stdout's first message contains ONLY Unity's finite credential, never MCP roles.
It is not a console/status-log interface. Caller must hold this exact child's
redirected Process pipes. No token files, environment delivery to Unity, discovery,
remote approvals, auto-start, or reusable authority. Same-UID compromise is out
of scope; parent PID checks do not prove the parent's executable brand.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import stat
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher.cli import Parser


def private_pipes():
    if os.name=='nt':
        import msvcrt,win32file
        return all(win32file.GetFileType(msvcrt.get_osfhandle(fd))==win32file.FILE_TYPE_PIPE for fd in (0,1))
    return all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in (0,1))


async def read_control(stop,timeout=None):
    """Bounded polling only; no daemon reader blocked in console ReadLine."""
    deadline=None if timeout is None else time.monotonic()+timeout
    data=bytearray()
    while not stop.is_set():
        if deadline is not None and time.monotonic()>=deadline:raise TimeoutError()
        if os.name=='nt':
            import msvcrt,win32pipe,pywintypes
            try:available=win32pipe.PeekNamedPipe(msvcrt.get_osfhandle(0),0)[1]
            except pywintypes.error as exc:
                if exc.winerror in (109,232):return b''
                raise
        else:
            import select
            available=bool(select.select([0],[],[],0)[0])
        if available:
            b=os.read(0,1)
            if not b:return b''
            data.extend(b)
            if len(data)>16:raise ValueError('control_too_long')
            if b==b'\n':return bytes(data)
        else:await asyncio.sleep(.02)
    return b''


def emit(value):
    sys.stdout.write(json.dumps(value,separators=(',',':'))+'\n');sys.stdout.flush()


async def run(args):
    from launcher.owned_run import create_owned_run,supervise_owned
    stop=threading.Event()
    if await read_control(stop,5)!=b'start\n':return 2
    if os.getppid()!=args.parent_pid:return 2
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1',0));port=reserved.getsockname()[1]
    raw={'project':args.project,'parent_pid':args.parent_pid,'local_port':port}
    owned=create_owned_run(raw)
    task=asyncio.create_task(asyncio.to_thread(supervise_owned,raw,owned=owned,stop=stop))
    control=asyncio.create_task(read_control(stop))
    binding_sent=ready_sent=False
    try:
        while not task.done():
            if control.done() or os.getppid()!=args.parent_pid:
                stop.set()
            if not stop.is_set() and owned.transport_ready.is_set() and not binding_sent:
                emit({'kind':'unity_binding','version':1,'owner_pid':os.getpid(),'project':args.project,
                    'endpoint':f'wss://127.0.0.1:{port}/hub/plugin','pin':owned.owner.tls.pin,
                    'unity_bearer':owned.owner.identity.credentials['unity'].token,
                    'expires_at':owned.owner.identity.expires_at})
                binding_sent=True
            if not stop.is_set() and binding_sent and owned.binding.ready.is_set() and not ready_sent:
                emit({'kind':'ready'});ready_sent=True
            await asyncio.sleep(.02)
        result=await task
        emit({'kind':'stopped',**result})
        return 0 if result['phase']=='stopped' else 1
    finally:
        stop.set();control.cancel();await asyncio.gather(control,return_exceptions=True)
        await asyncio.wait_for(asyncio.shield(task),12)


def main():
    parser=Parser(description='Editor-owned private-pipe entry',allow_abbrev=False)
    parser.add_argument('--project',required=True)
    parser.add_argument('--parent-pid',required=True,type=int)
    try:
        args=parser.parse_args()
        if args.parent_pid!=os.getppid() or args.parent_pid<=1 or not private_pipes():return 2
        return asyncio.run(run(args))
    except BaseException:
        # Never echo argv, JSON, bootstrap material, SDK exception details or tracebacks.
        return 2

if __name__=='__main__':raise SystemExit(main())
