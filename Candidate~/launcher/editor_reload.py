"""OS-authenticated Editor -> surviving owner control; never an MCP endpoint.
Locators are not grants. Only this original held Editor process can detach/rejoin;
all authority remains in the original owner/runtime, with the original deadlines.
No credentials, transfer authority, process discovery or reconnect retry on disk.
"""
import json
import os
import threading
import time
from .peer_channel import PeerListener
from .peer_identity import PeerProcess


class EditorReloadControl:
    def __init__(self, owned, parent_pid, stop):
        if owned.reload_control is None or parent_pid!=os.getppid():
            raise ValueError('editor_control_owner_required')
        self.owned=owned
        self.run_stop=stop
        self.stop=threading.Event()
        self.ready=threading.Event()
        self.failed=threading.Event()
        self.closed=threading.Event()
        self.requested_stop=threading.Event()
        self.finished=threading.Event()
        self.private_stop_wait=False
        self.legacy_eof_allowed=False
        self.result=None
        self.channel=None
        self.next_listener=None
        self.peer=PeerProcess(parent_pid)
        try:
            with PeerProcess(os.getpid()) as owner:self.created=owner.identity[1]
            self.listener=PeerListener()
            self.deadline=owned.reload_control.deadline
        except BaseException:
            self.peer.close();raise

    def metadata(self):
        return {'address':self.listener.address,'created':self.created}

    def unity_binding(self):
        owner=self.owned.owner
        return {'endpoint':f'wss://127.0.0.1:{owner.port}/hub/plugin','pin':owner.tls.pin,
            'unity_bearer':owner.identity.credentials['unity'].token,'expires_at':owner.identity.expires_at}

    def send(self, value):
        self.channel.send(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))

    def finish(self, result):
        # Caller has already completed client/probe cleanup and joined supervisor.
        self.result=dict(result)
        self.finished.set()
        if not self.private_stop_wait:self.stop.set()

    def serve(self):
        # Same native worker owns accept/read/write/cancel/drain/close, also on Windows.
        from reload_control import decode,keys
        def receive():return decode(self.channel.receive().decode('utf-8'))
        def stop_reply():
            self.private_stop_wait=True;self.requested_stop.set()
            while not self.finished.wait(.01):
                if not self.peer.alive() or time.monotonic()>=self.deadline:raise TimeoutError()
            # Runtime/client cleanup only; caller must also observe exact owner exit.
            self.send({'kind':'stopped',**self.result})
            return True
        try:
            self.channel=self.listener.accept(self.peer,deadline=min(self.deadline,time.monotonic()+10),stop=self.stop)
            hello=receive();keys(hello,'kind','version','project')
            if (type(hello['version']) is not int or
                hello!={'kind':'hello','version':1,'project':self.owned.owner.project}):
                raise PermissionError('editor_control_hello_invalid')
            self.send({'kind':'editor_control_ready','version':1})
            self.channel.deadline=self.deadline
            self.ready.set()
            for _ in range(1024):
                request=receive()
                if request=={'kind':'stop'}:return stop_reply()
                if request=={'kind':'status'}:
                    reply={'kind':'editor_control_status','phase':self.owned.reload_control.phase}
                elif request.get('kind')=='detach':
                    keys(request,'kind','handoff_id')
                    control=self.owned.reload_control
                    if (control.phase!='armed' or not control.pending() or self.next_listener is None
                        or request['handoff_id']!=control.handoff):raise PermissionError('unarmed_detach')
                    self.legacy_eof_allowed=True
                    self.send({'kind':'detached','handoff_id':control.handoff})
                    # No data may follow detach on the old channel. EOF is allowed
                    # only after this explicit command; unexpected EOF still fails.
                    try:self.channel.receive()
                    except EOFError:pass
                    else:raise PermissionError('old_channel_reused')
                    self.channel.close()
                    self.channel=self.next_listener.accept(self.peer,deadline=min(self.deadline,control.handoff_deadline),stop=self.stop)
                    self.next_listener=None
                    resume=receive();keys(resume,'kind','version','project','handoff_id')
                    if (type(resume['version']) is not int or resume['kind'] not in ('resume','cancel') or resume!={'kind':resume['kind'],'version':1,
                        'project':self.owned.owner.project,'handoff_id':control.handoff}):raise PermissionError('resume_changed')
                    if resume['kind']=='cancel':return stop_reply()
                    reply=control.request({'kind':'reattach','handoff_id':control.handoff})
                    reply['unity_binding']=self.unity_binding()
                elif request.get('kind') in ('arm','commit'):
                    if request['kind']=='arm' and self.next_listener is not None:raise PermissionError('already_armed')
                    reply=self.owned.reload_control.request(request)
                    if reply['kind']=='armed':
                        self.next_listener=PeerListener()
                        reply['next_address']=self.next_listener.address
                        self.channel.deadline=min(self.deadline,self.owned.reload_control.handoff_deadline)
                    elif reply['kind']=='committed':self.channel.deadline=self.deadline
                else:raise PermissionError('editor_control_operation_denied')
                self.send(reply)
            raise PermissionError('editor_control_message_limit')
        except BaseException:
            if not self.run_stop.is_set() and not self.stop.is_set():self.failed.set()
            return False
        finally:
            self.ready.clear()
            # Preserve runtime until normal SDK DELETEs finish. On unexpected loss,
            # revoke immediately; any unconfirmed protocol cleanup stays a failure.
            if self.failed.is_set():self.owned.reload_control.close()
            if self.channel is not None:self.channel.close()
            if self.next_listener is not None:self.next_listener.close()
            self.listener.close()
            self.peer.close()
            self.closed.set()
