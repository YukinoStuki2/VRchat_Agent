"""Real C# OS peer channel. Linux != Windows kernel, net8 != Unity Mono."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from launcher.peer_channel import PeerListener
from launcher.peer_identity import PeerProcess
from test_bootstrap_runtime import child_environment
WIRE_DLL=None
DOTNET=None

class EditorPeerTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def child(self,address,pid,created,mode='exchange'):
        self.assertTrue(WIRE_DLL and Path(WIRE_DLL).is_file() and DOTNET,'fresh compiled peer required')
        with tempfile.TemporaryDirectory(prefix='editor-peer-') as home:
            process=await asyncio.create_subprocess_exec(str(DOTNET),str(WIRE_DLL),str(pid),str(created),address,mode,
                stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
                cwd=home,env={**child_environment(home),'TMPDIR':home,'TMP':home,'TEMP':home})
            try:yield process
            finally:
                try:await asyncio.wait_for(process.wait(),7)
                except TimeoutError:
                    process.kill();await process.wait();self.fail('C# peer required safety kill')
                self.assertFalse(list(Path(home).iterdir()),'test left persistent data')
        self.assertFalse(Path(home).exists())

    async def test_EP001_actual_csharp_peer_exchanges_binary_frame(self):
        with PeerProcess(os.getpid()) as parent,PeerListener() as listener:
            async with self.child(listener.address,*parent.identity) as process:
                with PeerProcess(process.pid) as peer:
                    channel=await asyncio.to_thread(listener.accept,peer,deadline=time.monotonic()+5)
                    try:
                        data=await asyncio.to_thread(channel.receive)
                        self.assertEqual(data,'fixture-中文-\0-byte-channel'.encode())
                        await asyncio.to_thread(channel.send,'reply-中文'.encode())
                        out,err=await asyncio.wait_for(process.communicate(),5)
                        self.assertEqual(process.returncode,0,err.decode('utf-8','replace'))
                        self.assertEqual(out.strip(),b'PASS editor_peer_exchange');self.assertFalse(err)
                    finally:channel.close()

    async def test_EP002_creation_mismatch_refuses_before_connecting(self):
        with PeerProcess(os.getpid()) as parent,PeerListener() as listener:
            async with self.child(listener.address,parent.pid,parent.identity[1]+1) as process:
                out,err=await asyncio.wait_for(process.communicate(),5)
                self.assertEqual(process.returncode,2);self.assertEqual(out.strip(),b'DENIED owner_identity_changed')
                self.assertFalse(err)

    async def test_EP003_live_foreign_server_refuses_before_authority_bytes(self):
        with PeerProcess(os.getppid()) as foreign,PeerListener() as listener:
            async with self.child(listener.address,*foreign.identity) as process:
                # This listener is current PID, NOT the held outer runner above.
                with PeerProcess(process.pid) as peer:
                    channel=None;data=b''
                    try:
                        channel=await asyncio.to_thread(listener.accept,peer,deadline=time.monotonic()+5)
                        try:data=await asyncio.to_thread(channel.receive)
                        except (EOFError,PermissionError):pass
                    except PermissionError:pass
                    finally:
                        if channel is not None:channel.close()
                    out,err=await asyncio.wait_for(process.communicate(),5)
                    self.assertFalse(data);self.assertFalse(err);self.assertEqual(process.returncode,2)
                    self.assertEqual(out.strip(),b'DENIED owner_channel_foreign')

    async def rejected_frame(self,expected,*,mode='exchange',wire=None,close=False):
        with PeerProcess(os.getpid()) as parent,PeerListener() as listener:
            async with self.child(listener.address,*parent.identity,mode=mode) as process:
                with PeerProcess(process.pid) as peer:
                    channel=await asyncio.to_thread(listener.accept,peer,deadline=time.monotonic()+5)
                    try:
                        self.assertEqual(await asyncio.to_thread(channel.receive),'fixture-中文-\0-byte-channel'.encode())
                        if wire is not None:
                            def raw():
                                remaining=memoryview(wire)
                                while remaining:
                                    count=channel._io(remaining,write=True);self.assertGreater(count,0);remaining=remaining[count:]
                            await asyncio.to_thread(raw)
                        if close:channel.close()
                        out,err=await asyncio.wait_for(process.communicate(),5)
                        self.assertFalse(err);self.assertEqual(process.returncode,2)
                        self.assertEqual(out.strip(),('DENIED '+expected).encode())
                    finally:channel.close()

    async def test_EP004_invalid_frame_lengths_and_partial_eof_reject(self):
        import struct
        for n in (0,4*1024*1024+1,0xffffffff):
            await self.rejected_frame('owner_frame_invalid',wire=struct.pack('!I',n))
        await self.rejected_frame('owner_channel_closed',wire=struct.pack('!I',10)+b'xy',close=True)

    async def test_EP005_cancelled_pending_read_exits_without_forced_cleanup(self):
        await self.rejected_frame('cancelled',mode='cancel')

    async def test_EP006_queued_request_obeys_its_own_deadline(self):
        with PeerProcess(os.getpid()) as parent,PeerListener() as listener:
            async with self.child(listener.address,*parent.identity,mode='queue') as process:
                with PeerProcess(process.pid) as peer:
                    channel=await asyncio.to_thread(listener.accept,peer,deadline=time.monotonic()+5)
                    try:
                        self.assertEqual(await asyncio.to_thread(channel.receive),'fixture-中文-\0-byte-channel'.encode())
                        out,err=await asyncio.wait_for(process.communicate(),5)
                        self.assertFalse(err);self.assertEqual(process.returncode,0,out.decode())
                        self.assertEqual(out.strip(),b'PASS queued_deadline')
                    finally:channel.close()

if __name__=='__main__':unittest.main(verbosity=2)


