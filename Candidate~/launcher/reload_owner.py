"""Private owner-to-exact-child reload channel. Not an Editor approval source.

Created only through the typed local OwnedRun API. No port/PID discovery, public
CLI option, disk record or remote tool. Editor coordination remains separate.
"""
import json
import math
import os
import threading
import time

from .peer_channel import PeerListener
from .peer_identity import PeerProcess

ENVIRONMENT_KEY='VRCHAT_AGENT_RELOAD'


class OwnerReloadControl:
    def __init__(self,project,expires_at,binding):
        self.project=project
        self.binding=binding
        self.handoff=None
        self.transfers=[]
        self.expires_at=expires_at
        self.deadline=time.monotonic()+max(0,expires_at-time.time())
        if not 0<self.deadline-time.monotonic()<=3600:raise ValueError('invalid_run_deadline')
        self.listener=PeerListener()
        self.peer=None
        self.channel=None
        self.stop=threading.Event()
        self.lock=threading.RLock()
        self.bound=threading.Event()
        self.phase='idle'
        self.handoff_deadline=0

    def environment(self):
        return {ENVIRONMENT_KEY:json.dumps({'version':1,'address':self.listener.address,
            'parent_pid':os.getpid(),'expires_at':self.expires_at},separators=(',',':'))}

    def bind(self,pid):
        with self.lock:
            if self.peer is not None or self.stop.is_set():raise ValueError('control_already_bound')
            self.peer=PeerProcess(pid) # PID supplied by the original owned spawn, not IPC.
            self.bound.set()

    def connect(self):
        with self.lock:
            try:
                if self.stop.is_set() or self.peer is None:raise PermissionError('control_not_bound')
                if self.channel is None:
                    self.channel=self.listener.accept(self.peer,deadline=min(self.deadline,time.monotonic()+10),stop=self.stop)
                    reply=json.loads(self.channel.receive())
                    expected={'kind':'control_ready','version':1,'project_id':self.project}
                    if reply!=expected:raise PermissionError('control_handshake_changed')
                    self.channel.deadline=self.deadline
                return {'kind':'control_ready','version':1,'project_id':self.project}
            except BaseException:
                self.close();raise

    def pending(self):
        return (self.phase in ('arming','armed','reattaching','committing')
            and not self.stop.is_set() and self.peer is not None and self.peer.alive()
            and time.monotonic()<min(self.handoff_deadline,self.deadline)
            and time.time()<self.expires_at)

    def request(self,document):
        """Local Editor caller only, serialized; no method accepts approval."""
        import hashlib
        with self.lock:
            try:
                self.connect()
                wire=json.dumps(document,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
                request=json.loads(wire) # Caller alias cannot alter a queued request.
                kind=request.get('kind') if type(request) is dict else None
                if kind=='arm' and self.phase=='idle':
                    window=request.get('window')
                    if type(window) not in (int,float) or not math.isfinite(window) or not 0<window<=60:raise ValueError()
                    self.handoff=request.get('handoff_id')
                    self.transfers=request.get('transfers')
                    self.handoff_deadline=min(self.deadline,time.monotonic()+window)
                    self.phase='arming'
                    self.binding.ready.clear()
                    while self.binding.probe_inflight.is_set():
                        if not self.pending():raise TimeoutError()
                        time.sleep(.01)
                    expected='armed'
                elif kind=='reattach' and self.phase=='armed' and request.get('handoff_id')==self.handoff:
                    self.phase='reattaching';expected='reattach'
                elif kind=='commit' and self.phase=='reattaching' and request.get('handoff_id')==self.handoff:
                    self.phase='committing';expected='committed'
                else:raise ValueError()
                if not self.pending():raise TimeoutError()
                self.channel.deadline=min(self.deadline,self.handoff_deadline)
                self.channel.send(wire)
                from reload_control import decode
                reply=decode(self.channel.receive().decode('utf-8'))
                if (type(reply) is not dict or reply.get('kind')!=expected
                    or reply.get('handoff_id')!=self.handoff):raise ValueError()
                if expected=='armed':
                    if reply.get('digests')!=[hashlib.sha256(s.encode('utf-8')).hexdigest() for s in self.transfers]:raise ValueError()
                    self.phase='armed'
                elif expected=='reattach':
                    if reply.get('transfers')!=self.transfers:raise ValueError()
                else:
                    self.phase='idle';self.transfers=[];self.handoff=None
                    self.channel.deadline=self.deadline
                return reply
            except BaseException:
                self.binding.failed.set();self.close()
                raise PermissionError('local_owner_reload_denied') from None

    def close(self):
        self.stop.set() # Wake any active synchronous worker before taking its lock.
        with self.lock:
            self.phase='closed'
            self.transfers=[];self.handoff=None
            if self.channel is not None:self.channel.close();self.channel=None
            self.listener.close()
            if self.peer is not None:self.peer.close();self.peer=None
