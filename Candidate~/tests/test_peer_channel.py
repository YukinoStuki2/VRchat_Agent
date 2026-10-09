"""Real OS-local byte transport; no Editor approval or reload orchestration.
Windows branches must run on Windows; Linux is not a HANDLE/ACL substitute.
"""
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher.peer_identity import PeerProcess


class PeerChannelTests(unittest.TestCase):
    def api(self):
        self.assertTrue((ROOT/'launcher/peer_channel.py').is_file(),'bounded OS channel missing')
        from launcher.peer_channel import PeerListener, PeerChannel
        return PeerListener, PeerChannel

    def spawn(self, address, payload_size=16):
        code='''
import os,sys,time
sys.path.insert(0,sys.argv[1])
from launcher.peer_identity import PeerProcess
from launcher.peer_channel import PeerChannel
with PeerProcess(os.getppid()) as parent:
    with PeerChannel.connect(sys.argv[2],parent,deadline=time.monotonic()+5) as channel:
        channel.send(b'R'*int(sys.argv[3]))
        assert channel.receive()==b'accepted'
        # Remain alive until the trusted parent consumed the frame.
        assert sys.stdin.buffer.read(1)==b'Q'
'''
        env=dict(os.environ)
        if os.name=='nt':env['__PYVENV_LAUNCHER__']=sys.executable
        return subprocess.Popen([getattr(sys,'_base_executable',sys.executable),'-I','-B','-c',code,
            str(ROOT),address,str(payload_size)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)

    def finish(self, child):
        if child.poll() is None:child.kill();child.communicate(timeout=5)
        else:
            for stream in (child.stdin,child.stdout,child.stderr):
                if stream and not stream.closed:stream.close()

    def test_OS001_exact_child_and_parent_exchange_bounded_bytes(self):
        Listener,_=self.api()
        # Socket/pipe name is a locator, not a secret or authentication proof.
        with Listener() as listener:
            child=self.spawn(listener.address)
            try:
                with PeerProcess(child.pid) as identity:
                    with listener.accept(identity,deadline=time.monotonic()+5) as channel:
                        self.assertEqual(channel.receive(),b'R'*16)
                        channel.send(b'accepted')
                        out,err=child.communicate(b'Q',timeout=5)
                        self.assertEqual(child.returncode,0,err.decode('utf-8','replace'))
                        self.assertEqual(out,b'');self.assertEqual(err,b'')
            finally:self.finish(child)
        self.assertTrue(listener.closed)


    def test_OS002_foreign_process_cannot_receive_authority_bytes(self):
        Listener,_=self.api()
        with Listener() as listener, PeerProcess(os.getpid()) as wrong:
            child=self.spawn(listener.address)
            try:
                with self.assertRaises(PermissionError):
                    listener.accept(wrong,deadline=time.monotonic()+5)
                self.assertTrue(listener.closed)
                out,err=child.communicate(b'Q',timeout=5)
                self.assertNotEqual(child.returncode,0)
                self.assertEqual(out,b'');self.assertNotIn(b'ResourceWarning',err)
            finally:self.finish(child)

    def test_OS003_accept_and_idle_read_have_fixed_deadline(self):
        Listener,Channel=self.api()
        with Listener() as listener, PeerProcess(os.getpid()) as own:
            start=time.monotonic()
            with self.assertRaises(TimeoutError):listener.accept(own,deadline=start+.1)
            self.assertLess(time.monotonic()-start,2)
            self.assertTrue(listener.closed)
        with Listener() as listener, PeerProcess(os.getpid()) as own:
            deadline=time.monotonic()+.3
            with Channel.connect(listener.address,own,deadline=deadline) as client:
                with listener.accept(own,deadline=deadline) as server:
                    with self.assertRaises(TimeoutError):server.receive()
                    self.assertIsNone(server._handle)
            self.assertLess(time.monotonic()-deadline,2)

    def test_OS004_large_frame_and_oversize_header_are_bounded(self):
        Listener,Channel=self.api()
        from launcher.peer_channel import MAX_FRAME
        import struct
        with Listener() as listener:
            child=self.spawn(listener.address,1024*1024)
            try:
                with PeerProcess(child.pid) as identity, listener.accept(identity,deadline=time.monotonic()+5) as server:
                    self.assertEqual(server.receive(),b'R'*(1024*1024))
                    server.send(b'accepted')
                    out,err=child.communicate(b'Q',timeout=5)
                    self.assertEqual(child.returncode,0,err.decode('utf-8','replace'))
                    self.assertEqual(out,b'');self.assertEqual(err,b'')
            finally:self.finish(child)
        for size in (0,MAX_FRAME+1,0xffffffff):
            with self.subTest(size=size), Listener() as listener, PeerProcess(os.getpid()) as own:
                deadline=time.monotonic()+3
                with Channel.connect(listener.address,own,deadline=deadline) as client:
                    with listener.accept(own,deadline=deadline) as server:
                        self.assertEqual(client._io(struct.pack('!I',size),write=True),4)
                        with self.assertRaises(ValueError):server.receive()
                        self.assertIsNone(server._handle)

    def test_OS005_cancel_unblocks_io_and_listener_is_not_reused(self):
        Listener,Channel=self.api()
        for io in ('accept','receive','send'):
            with self.subTest(io=io), Listener() as listener, PeerProcess(os.getpid()) as own, ExitStack() as stack:
                stop=threading.Event();deadline=time.monotonic()+3
                if io!='accept':
                    client=stack.enter_context(Channel.connect(listener.address,own,deadline=deadline))
                    server=stack.enter_context(listener.accept(own,deadline=deadline,stop=stop))
                timer=threading.Timer(.1,stop.set);timer.start()
                try:
                    with self.assertRaises(TimeoutError):
                        if io=='accept':listener.accept(own,deadline=deadline,stop=stop)
                        elif io=='receive':server.receive()
                        else:server.send(b'X'*(4*1024*1024)) # reader deliberately idle
                    self.assertTrue(listener.closed)
                    with self.assertRaises(PermissionError):listener.accept(own,deadline=deadline)
                finally:timer.join(timeout=1)
                self.assertFalse(timer.is_alive())

    def test_OS006_invalid_locator_deadline_and_payload_fail_closed(self):
        Listener,Channel=self.api()
        with PeerProcess(os.getpid()) as own:
            for address in ('127.0.0.1:1234','/tmp/foreign','vrchat-local-'+'a'*47,'vrchat-local-'+'A'*48):
                with self.subTest(address=address),self.assertRaises(ValueError):
                    Channel.connect(address,own,deadline=time.monotonic()+1)
            for delta in (-1,0,3601,float('inf'),float('nan')):
                with Listener() as listener,self.subTest(delta=delta),self.assertRaises(ValueError):
                    listener.accept(own,deadline=time.monotonic()+delta)
            for payload in (b'',bytearray(b'X'),'X',b'X'*(4*1024*1024+1)):
                with Listener() as listener:
                    deadline=time.monotonic()+3
                    with Channel.connect(listener.address,own,deadline=deadline) as client:
                        with listener.accept(own,deadline=deadline) as server:
                            with self.assertRaises(ValueError):server.send(payload)
                            self.assertIsNone(server._handle)

    def test_OS007_private_native_endpoint_has_no_persisted_file(self):
        Listener,_=self.api()
        with Listener() as listener:
            self.assertRegex(listener.address,r'^vrchat-local-[0-9a-f]{48}$')
            if os.name=='nt':
                import win32api,win32security
                self.assertEqual(win32api.GetHandleInformation(listener._handle)&1,0)
                security=win32security.GetSecurityInfo(listener._handle,6,4)
                self.assertTrue(security.GetSecurityDescriptorControl()[0]&0x1000,'DACL not protected')
                token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),8)
                try:sid=win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,1)[0])
                finally:token.Close()
                acl=security.GetSecurityDescriptorDacl()
                self.assertEqual(acl.GetAceCount(),2)
                got={win32security.ConvertSidToStringSid(acl.GetAce(i)[2]) for i in range(acl.GetAceCount())}
                self.assertEqual(got,{sid,'S-1-5-18'})
            else:
                self.assertEqual(listener._handle.getsockname(),b'\0'+listener.address.encode('ascii'))
                self.assertFalse(os.get_inheritable(listener._handle.fileno()))
        self.assertTrue(listener.closed)

    def test_OS008_windows_cancel_error_still_drains_before_event_close(self):
        # ABI/control-flow double ONLY; real Windows execution is a separate gate.
        from types import SimpleNamespace
        from unittest.mock import patch
        self.api()
        from launcher.peer_channel import _win_io
        class WinError(Exception):
            def __init__(self,code):self.winerror=code
        events=[]
        event=SimpleNamespace(Close=lambda:events.append('close'))
        def cancel(_):
            events.append('cancel');raise WinError(5)
        def drain(*args):
            events.append('drain');raise WinError(995)
        modules={
            'pywintypes':SimpleNamespace(OVERLAPPED=SimpleNamespace,error=WinError),
            'win32event':SimpleNamespace(CreateEvent=lambda *args:event),
            'win32file':SimpleNamespace(CancelIo=cancel,GetOverlappedResult=drain)}
        with patch.dict(sys.modules,modules),patch('launcher.peer_channel._remaining',side_effect=[.02,TimeoutError()]):
            with self.assertRaises(WinError):_win_io(object(),lambda _:0,object(),1,threading.Event())
        self.assertEqual(events,['cancel','drain','close'])

    def test_OS009_control_transport_deadline_may_cover_finite_run_not_task(self):
        Listener,_=self.api()
        with Listener() as listener:
            child=self.spawn(listener.address)
            try:
                with PeerProcess(child.pid) as peer:
                    with listener.accept(peer,deadline=time.monotonic()+600) as channel:
                        self.assertEqual(channel.receive(),b'R'*16)
                        channel.send(b'accepted')
                        out,err=child.communicate(b'Q',timeout=5)
                        self.assertEqual(child.returncode,0,err)
                        self.assertNotIn(b'ResourceWarning',err)
            finally:self.finish(child)
        with Listener() as listener,PeerProcess(os.getpid()) as peer:
            with self.assertRaises(ValueError):listener.accept(peer,deadline=time.monotonic()+3601)

if __name__=='__main__':unittest.main(verbosity=2)
