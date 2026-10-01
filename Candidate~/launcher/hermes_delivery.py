"""Local owner -> fixed SSH subsystem. No shell, files, retries or approvals.

The calling owner keeps its runtime alive until this delivery closes. Offering
is not admission to any Hermes chat; the trusted remote host must choose that.
"""
import asyncio
import json
import os
import re
import threading
import time

from .candidate_launch import (build_handoff_command, child_environment,
                               make_owner, Progress, validate_config)
from .editor_owner import read_control


async def deliver(raw, local_run, *, stop, offered):
    """Repeated cancellation requests stop and wait; never orphan an owned SSH."""
    task=asyncio.create_task(_deliver(raw,local_run,stop=stop,offered=offered))
    cancelled=False
    while True:
        try:
            result=await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            cancelled=True;stop.set()
    if cancelled:raise asyncio.CancelledError()
    return result


async def _deliver(raw,local_run,*,stop,offered):
    result={'code':'HANDOFF_FAILED','process_cleanup_complete':True,'remote_cleanup_confirmed':False}
    owner=None;fds=[];receipt=None;read_stop=threading.Event();progress=None
    try:
        c=validate_config(raw)
        identity,tls=local_run.identity,local_run.tls
        if 'hermes' not in identity.clients or local_run.project!=c['project'] or local_run.port!=c['local_port']:
            raise ValueError('candidate_hermes_not_selected')
        command=build_handoff_command(c)
        payload=json.dumps({'version':1,'role':'hermes','project':local_run.project,'port':c['ssh']['remote_port'],
            'server_port':c['local_port'],'certificate':tls.certificate.decode('ascii'),'pin':tls.pin,
            'bearer':identity.credentials['hermes'].token,'expires_at':identity.expires_at},
            separators=(',',':')).encode()+b'\n'
        # A single bounded write fits the supported anonymous pipe buffers.
        if not 1<=len(payload)<=4096:raise ValueError('candidate_handoff_size')
        progress=Progress('ssh',c['ssh']['remote_port'],c['local_port'])
        owner=make_owner(c['parent_pid'])
        r_in,w_in=os.pipe();fds.extend((r_in,w_in))
        r_out,w_out=os.pipe();fds.extend((r_out,w_out))
        child=owner.spawn(command,child_environment(),progress.line,stdio=(r_in,w_out))
        for fd in (r_in,w_out):os.close(fd);fds.remove(fd)
        deadline=time.monotonic()+30
        while not progress.ready:
            if stop.is_set():result['code']='STOPPED';return result
            if progress.error or child.poll() is not None or not owner.alive():
                raise OSError('candidate_ssh_unavailable')
            if time.monotonic()>=deadline:raise TimeoutError()
            await asyncio.sleep(.02)
        if os.write(w_in,payload)!=len(payload):raise OSError('candidate_handoff_incomplete')
        payload=b''
        reply=json.loads(await read_control(read_stop,6,fd=r_out,limit=256))
        if (type(reply) is not dict or set(reply)!={'kind','id'} or reply['kind']!='offered'
                or type(reply['id']) is not str or re.fullmatch('[0-9a-f]{32}',reply['id']) is None):
            raise ValueError('candidate_handoff_receipt')
        offered.set()
        receipt=asyncio.create_task(read_control(read_stop,max(1,identity.expires_at-time.time()+8),fd=r_out,limit=256))
        while not receipt.done() and not stop.is_set() and owner.alive():
            await asyncio.sleep(.02)
        requested=stop.is_set()
        if not receipt.done():
            if os.write(w_in,b'stop\n')!=5:raise OSError('candidate_stop_incomplete')
        reply=json.loads(await asyncio.wait_for(receipt,8))
        if type(reply) is not dict or set(reply)!={'kind','clean'} or reply['kind']!='closed' or type(reply['clean']) is not bool:
            raise ValueError('candidate_handoff_receipt')
        result['remote_cleanup_confirmed']=reply['clean']
        result['code']='STOPPED' if requested and reply['clean'] else 'HANDOFF_CLOSED' if reply['clean'] else 'HANDOFF_CLEANUP_FAILED'
    except Exception:
        # Do not emit SDK/SSH details, certificate contents, envelope or paths.
        if progress is not None and progress.error:result['code']=progress.error
    finally:
        read_stop.set()
        if receipt is not None:
            receipt.cancel();await asyncio.gather(receipt,return_exceptions=True)
        if owner is not None:
            result['process_cleanup_complete']=await asyncio.to_thread(owner.close)
        for fd in fds:os.close(fd)
        if not result['process_cleanup_complete']:result['code']='HANDOFF_CLEANUP_FAILED'
    return result
