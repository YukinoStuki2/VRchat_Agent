"""OS-held process identity, not Unity brand or approval authentication.
Linux exercises pidfd; Windows exercises a real process HANDLE when run there.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class PeerIdentityTests(unittest.TestCase):
    def api(self):
        path=ROOT/'launcher/peer_identity.py'
        self.assertTrue(path.is_file(),'OS-pinned peer identity is missing')
        from launcher.peer_identity import PeerProcess
        return PeerProcess

    def test_PI001_exact_process_is_pinned_and_close_revokes(self):
        PeerProcess=self.api()
        identity=PeerProcess(os.getpid())
        try:
            self.assertTrue(identity.alive())
            pid,created=identity.identity
            self.assertEqual(pid,os.getpid())
            self.assertIs(type(created),int)
            self.assertGreater(created,0)
        finally: identity.close()
        self.assertFalse(identity.alive())
        identity.close()

    def test_PI002_dead_process_never_revives_and_invalid_pid_rejected(self):
        PeerProcess=self.api()
        for pid in (True,False,0,-1,'123',2**32):
            with self.assertRaises(ValueError):PeerProcess(pid)
        # Execute the real interpreter directly: Windows venv redirectors must
        # not be mistaken for the actual child process identity.
        executable=getattr(sys,'_base_executable',sys.executable)
        child=subprocess.Popen([executable,'-I','-B','-c','import sys;sys.stdin.buffer.read(1)'],stdin=subprocess.PIPE)
        identity=None
        try:
            identity=PeerProcess(child.pid)
            self.assertTrue(identity.alive())
            child.stdin.close();child.wait(timeout=5)
            self.assertFalse(identity.alive())
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
            if not child.stdin.closed:child.stdin.close()
            if identity is not None:identity.close()

    def test_PI003_kernel_channel_pid_must_match_held_process(self):
        from contextlib import ExitStack
        import secrets
        PeerProcess=self.api()
        with ExitStack() as stack:
            if os.name=='nt':
                import pywintypes,win32file,win32pipe
                path=r'\\.\pipe\vragent-peer-test-'+secrets.token_hex(16)
                server=win32pipe.CreateNamedPipe(path,win32pipe.PIPE_ACCESS_DUPLEX|0x00080000,
                    win32pipe.PIPE_TYPE_BYTE|win32pipe.PIPE_READMODE_BYTE|0x8,1,1024,1024,0,None)
                stack.callback(server.Close)
                client=win32file.CreateFile(path,win32file.GENERIC_READ|win32file.GENERIC_WRITE,0,None,win32file.OPEN_EXISTING,0,None)
                stack.callback(client.Close)
                try:win32pipe.ConnectNamedPipe(server,None)
                except pywintypes.error as error:
                    if error.winerror!=535:raise
            else:
                server,client=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
                stack.callback(server.close);stack.callback(client.close)
            own=stack.enter_context(PeerProcess(os.getpid()))
            self.assertTrue(callable(getattr(own,'matches_channel',None)),'kernel channel peer check missing')
            self.assertTrue(own.matches_channel(server,server=True))
            self.assertTrue(own.matches_channel(client,server=False))
            executable=getattr(sys,'_base_executable',sys.executable)
            child=subprocess.Popen([executable,'-I','-B','-c','import sys;sys.stdin.buffer.read(1)'],stdin=subprocess.PIPE)
            try:
                with PeerProcess(child.pid) as foreign:
                    self.assertFalse(foreign.matches_channel(server,server=True),'same-user foreign process admitted')
                    self.assertFalse(foreign.matches_channel(client,server=False))
                own.close()
                self.assertFalse(own.matches_channel(server,server=True))
            finally:
                child.stdin.close()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5);raise

    def test_PI004_real_child_endpoint_and_parent_checked_without_pid_claims(self):
        from contextlib import ExitStack
        import secrets,tempfile
        PeerProcess=self.api()
        with ExitStack() as stack:
            if os.name=='nt':
                import pywintypes,win32file,win32pipe
                address=r'\\.\pipe\vragent-peer-child-'+secrets.token_hex(16)
                listener=win32pipe.CreateNamedPipe(address,win32pipe.PIPE_ACCESS_DUPLEX|0x00080000,
                    win32pipe.PIPE_TYPE_BYTE|win32pipe.PIPE_READMODE_BYTE|0x8,1,1024,1024,0,None)
                stack.callback(listener.Close)
            else:
                directory=stack.enter_context(tempfile.TemporaryDirectory(prefix='peer-child-'))
                address=str(Path(directory)/'socket')
                listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                stack.callback(listener.close);listener.settimeout(5);listener.bind(address);listener.listen(1)
            code="""
import os,socket,sys
sys.path.insert(0,sys.argv[1])
from launcher.peer_identity import PeerProcess
# Only fixture argv locates the endpoint. Kernel PID, not message content,
# identifies our parent; no claimed identity is accepted from the channel.
with PeerProcess(os.getppid()) as parent:
    if os.name=='nt':
        import win32file
        peer=win32file.CreateFile(sys.argv[2],win32file.GENERIC_READ|win32file.GENERIC_WRITE,0,None,win32file.OPEN_EXISTING,0,None)
    else:
        peer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);peer.settimeout(5);peer.connect(sys.argv[2])
    try:
        assert parent.matches_channel(peer,server=False)
        if os.name=='nt':win32file.WriteFile(peer,b'R')
        else:peer.sendall(b'R')
        assert sys.stdin.buffer.read(1)==b'Q'
    finally:
        if os.name=='nt':peer.Close()
        else:peer.close()
"""
            executable=getattr(sys,'_base_executable',sys.executable)
            env=dict(os.environ)
            if os.name=='nt':env['__PYVENV_LAUNCHER__']=sys.executable
            child=subprocess.Popen([executable,'-I','-B','-c',code,str(ROOT),address],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            identity=None
            try:
                identity=PeerProcess(child.pid)
                if os.name=='nt':
                    try:win32pipe.ConnectNamedPipe(listener,None)
                    except pywintypes.error as error:
                        if error.winerror!=535:raise
                    peer=listener
                else:
                    peer,_=listener.accept();stack.callback(peer.close);peer.settimeout(5)
                self.assertTrue(identity.matches_channel(peer,server=True))
                with PeerProcess(os.getpid()) as wrong:
                    self.assertFalse(wrong.matches_channel(peer,server=True))
                data=win32file.ReadFile(peer,1)[1] if os.name=='nt' else peer.recv(1)
                self.assertEqual(data,b'R','child verified actual parent endpoint')
                out,err=child.communicate(b'Q',timeout=5)
                self.assertEqual(child.returncode,0,err.decode('utf-8','replace'))
                self.assertEqual(out,b'');self.assertEqual(err,b'')
                self.assertFalse(identity.alive())
                self.assertFalse(identity.matches_channel(peer,server=True),'dead pinned peer cannot authenticate')
            finally:
                if child.poll() is None:child.kill();child.communicate(timeout=5)
                else:
                    for stream in (child.stdin,child.stdout,child.stderr):
                        if stream and not stream.closed:stream.close()
                if identity is not None:identity.close()
        if os.name!='nt':self.assertFalse(Path(directory).exists())

if __name__=='__main__':unittest.main(verbosity=2)
