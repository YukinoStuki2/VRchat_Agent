"""Local typed owner binding for the restricted process supervisor.

No JSON-to-authority conversion, client configuration write, token delivery,
Unity discovery, or permission grant. Those installation/bootstrap parts remain
separate. This API is called only by a trusted local owner implementation.
"""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import sys
import threading
from typing import Any

from .candidate_launch import RuntimeBinding, supervise, validate_config

ROOT=Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class OwnedRun:
    config: dict = field(repr=False)
    owner: Any = field(repr=False)
    binding: RuntimeBinding = field(repr=False)
    _used: bool = field(default=False,init=False,repr=False)
    _lock: Any = field(default_factory=threading.Lock,init=False,repr=False)


def create_owned_run(raw, *, lifetime=600):
    c=validate_config(raw)
    # Fixed, packaged modules, never caller-selected paths or installed SDK edits.
    for path in (ROOT/'runtime',ROOT/'dependencies/mcp-1.29.1'):
        if str(path) not in sys.path:sys.path.insert(0,str(path))
    from owner_bootstrap import new_local_run
    owner=new_local_run(c['project'],c['local_port'],lifetime=lifetime)
    return OwnedRun(c,owner,RuntimeBinding(owner.take_environment(),threading.Event()))


def supervise_owned(raw, *, owned, stop=None, report=None):
    c=validate_config(raw)
    if type(owned) is not OwnedRun or owned.config!=c or owned.owner.project!=c['project'] or owned.owner.port!=c['local_port']:
        raise ValueError('owned_target_mismatch')
    with owned._lock:
        if owned._used:raise ValueError('owned_run_already_consumed')
        owned._used=True
    from owned_probe import observe_runtime
    binding=owned.binding
    stop = threading.Event() if stop is None else stop
    halt = threading.Event()
    receipt = {}
    def observer():
        try:
            asyncio.run(observe_runtime(owned.owner,binding,stop=stop,receipt=receipt))
        except BaseException:
            # Never print exceptions that may include headers or material.
            binding.failed.set()
        finally:
            binding.ready.clear()
            if stop.is_set() and not binding.failed.is_set():halt.set()
            elif not binding.cancelled.is_set():binding.failed.set()
    thread=threading.Thread(target=observer,name='vrchat-owned-probe-'+str(owned.owner.port),daemon=False)
    thread.start()
    try:
        result=supervise(c,binding=binding,stop=halt,report=report)
    finally:
        binding.cancelled.set()
        binding.ready.clear()
        thread.join(timeout=10)
        binding.environment.clear()
    result['probe_cleanup_complete']=not thread.is_alive()
    result['probe_session_cleanup_confirmed']=receipt.get('session_cleanup_confirmed',False)
    # Remote plan/session cleanup is NOT inferred from a terminated thread.
    if thread.is_alive():
        result['code']='PROBE_CLEANUP_FAILED'
        result['phase']='error'
    return result
