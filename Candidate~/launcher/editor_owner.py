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


async def read_control(stop,timeout=None,*,fd=0,limit=16):
    """Bounded polling only; no daemon reader blocked in console ReadLine."""
    deadline=None if timeout is None else time.monotonic()+timeout
    data=bytearray()
    while not stop.is_set():
        if deadline is not None and time.monotonic()>=deadline:raise TimeoutError()
        if os.name=='nt':
            import msvcrt,win32pipe,pywintypes
            try:available=win32pipe.PeekNamedPipe(msvcrt.get_osfhandle(fd),0)[1]
            except pywintypes.error as exc:
                if exc.winerror in (109,232):return b''
                raise
        else:
            import select
            available=bool(select.select([fd],[],[],0)[0])
        if available:
            b=os.read(fd,1)
            if not b:return b''
            data.extend(b)
            if len(data)>limit:raise ValueError('control_too_long')
            if b==b'\n':return bytes(data)
        else:await asyncio.sleep(.02)
    return b''


def emit(value):
    sys.stdout.write(json.dumps(value,separators=(',',':'))+'\n');sys.stdout.flush()


async def run(args):
    from launcher.owned_run import create_owned_run,supervise_owned
    from launcher.candidate_launch import validate_config
    from launcher.hermes_delivery import deliver
    from launcher.codex_local import serve as serve_codex
    stop=threading.Event();handoff_stop=threading.Event();offered=threading.Event()
    if await read_control(stop,5)!=b'start\n':return 2
    if os.getppid()!=args.parent_pid:return 2
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1',0));port=reserved.getsockname()[1]
    raw={'project':args.project,'parent_pid':args.parent_pid,'local_port':port}
    remote=None
    if any(getattr(args,name,None) is not None for name in ('hermes_host','hermes_user','hermes_port','hermes_forward_port')):
        if 'hermes' not in args.client:raise ValueError('hermes_not_selected')
        remote=validate_config({**raw,'ssh':{'host':args.hermes_host,'user':args.hermes_user or '',
            'port':22 if args.hermes_port is None else args.hermes_port,'remote_port':args.hermes_forward_port}})
    codex_executable=getattr(args,'codex_executable',None)
    codex_project=getattr(args,'codex_project',None)
    if codex_executable is not None or codex_project is not None:
        if 'codex' not in args.client or not codex_executable or not codex_project:
            raise ValueError('codex_local_selection_required')
    owned=create_owned_run(raw,clients=tuple(args.client))
    task=asyncio.create_task(asyncio.to_thread(supervise_owned,raw,owned=owned,stop=stop))
    control=asyncio.create_task(read_control(stop))
    delivery=None;delivery_result=None
    codex=None;codex_result=None;codex_started=threading.Event()
    binding_sent=ready_sent=False
    try:
        while not task.done():
            requested=control.done() or os.getppid()!=args.parent_pid
            if requested:
                handoff_stop.set()
                if (delivery is None or delivery.done()) and (codex is None or codex.done()):stop.set()
            if delivery is not None and delivery.done():
                delivery_result=delivery.result();handoff_stop.set()
                if codex is None or codex.done():stop.set()
            if codex is not None and codex.done():
                codex_result=codex.result();handoff_stop.set()
                if delivery is None or delivery.done():stop.set()
            if not stop.is_set() and not requested and owned.transport_ready.is_set() and not binding_sent:
                emit({'kind':'unity_binding','version':2,'clients':owned.owner.identity.clients,'owner_pid':os.getpid(),'project':args.project,
                    'endpoint':f'wss://127.0.0.1:{port}/hub/plugin','pin':owned.owner.tls.pin,
                    'unity_bearer':owned.owner.identity.credentials['unity'].token,
                    'expires_at':owned.owner.identity.expires_at})
                binding_sent=True
            if not stop.is_set() and not requested and binding_sent and owned.binding.ready.is_set():
                if remote is not None and delivery is None:
                    delivery=asyncio.create_task(deliver(remote,owned.owner,stop=handoff_stop,offered=offered))
                if codex_executable is not None and codex is None:
                    codex=asyncio.create_task(serve_codex(owned.owner,codex_executable,codex_project,stop=handoff_stop,started=codex_started))
                if not ready_sent and (remote is None or offered.is_set()) and (codex_executable is None or codex_started.is_set()):
                    emit({'kind':'ready'});ready_sent=True
            await asyncio.sleep(.02)
        result=await task
    finally:
        handoff_stop.set()
        try:
            if delivery is not None:delivery_result=await delivery
        finally:
            try:
                if codex is not None:codex_result=await codex
            finally:
                stop.set();control.cancel();await asyncio.gather(control,return_exceptions=True)
                await asyncio.wait_for(asyncio.shield(task),12)
    if remote is not None:
        result['handoff_cleanup_confirmed']=delivery_result is not None and delivery_result['remote_cleanup_confirmed']
        result['process_cleanup_complete'] &= delivery_result is None or delivery_result['process_cleanup_complete']
        if not result['handoff_cleanup_confirmed'] or delivery_result['code'] not in ('STOPPED','HANDOFF_CLOSED'):
            result.update(phase='blocked',code=delivery_result['code'] if delivery_result else 'HANDOFF_NOT_STARTED')
    if codex_executable is not None:
        result['codex_cleanup_complete']=bool(codex_result and codex_result['process_cleanup_complete'] and codex_result['profile_cleanup_complete'])
        result['process_cleanup_complete'] &= result['codex_cleanup_complete']
        if not result['codex_cleanup_complete'] or codex_result['code'] not in ('STOPPED','CODEX_CLOSED'):
            result.update(phase='blocked',code=codex_result['code'] if codex_result else 'CODEX_NOT_STARTED')
    emit({'kind':'stopped',**result})
    return 0 if result['phase']=='stopped' else 1


def main():
    parser=Parser(description='Editor-owned private-pipe entry',allow_abbrev=False)
    parser.add_argument('--project',required=True)
    parser.add_argument('--parent-pid',required=True,type=int)
    parser.add_argument('--client',choices=('hermes','codex'),action='append',default=[])
    parser.add_argument('--codex-executable')
    parser.add_argument('--codex-project')
    parser.add_argument('--hermes-host')
    parser.add_argument('--hermes-user')
    parser.add_argument('--hermes-port',type=int)
    parser.add_argument('--hermes-forward-port',type=int)
    try:
        args=parser.parse_args()
        if args.parent_pid!=os.getppid() or args.parent_pid<=1 or not private_pipes():return 2
        return asyncio.run(run(args))
    except BaseException:
        # Never echo argv, JSON, bootstrap material, SDK exception details or tracebacks.
        return 2

if __name__=='__main__':raise SystemExit(main())
