"""Local-only admission control around the unchanged audited MCP bridge.
No new routes/tools. In-flight requests may finish; never retry source mutations.
"""
import threading


def make_server_class(audit):
    class GatedServer(audit._Server):
        def __init__(self,*args,**kwargs):
            self._admission=threading.Event();self._admission.set()
            self._forward_lock=threading.Lock()
            super().__init__(*args,**kwargs)
        @property
        def is_paused(self):return not self._admission.is_set()
        def pause(self):self._admission.clear()
        def _deny(self):
            raise audit.Rejected(503,-32003,'Temporarily suspended or busy; request not forwarded; do not automatically retry mutations')
        def drain(self):
            if not self.is_paused:return False
            acquired=self._forward_lock.acquire(timeout=self.call_timeout*2+2)
            if acquired:self._forward_lock.release()
            return acquired
        def resume(self):
            # Caller must have completed local revoke acknowledgement and identity/status checks.
            if not self._forward_lock.acquire(timeout=1):raise audit.Rejected(503,-32003,'Admission still busy')
            try:self._admission.set()
            finally:self._forward_lock.release()
        def dispatch(self,msg,token,version):
            if msg.get('method') not in {'tools/call','resources/read'}:
                return super().dispatch(msg,token,version)
            if self.is_paused:self._deny()
            # No queue across a pause/resume episode. Immediate busy response is safer than replay.
            if not self._forward_lock.acquire(False):self._deny()
            try:
                if self.is_paused:self._deny()
                return super().dispatch(msg,token,version)
            finally:self._forward_lock.release()
    return GatedServer
