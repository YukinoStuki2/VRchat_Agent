"""Owned private stdio, using actual OS children (Windows run required too)."""
import os
from pathlib import Path
import sys
import threading
import unittest
import asyncio

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher.candidate_launch import make_owner,child_environment
from launcher.direct_python import current,environment_hint


class PrivatePipes(unittest.IsolatedAsyncioTestCase):
    async def test_PP001_owned_child_roundtrip_preserves_private_pipe_ownership(self):
        import inspect
        owner=make_owner(os.getpid())
        try:
            self.assertIn('stdio',inspect.signature(owner.spawn).parameters)
            from launcher.editor_owner import read_control
            readin,writein=os.pipe();readout,writeout=os.pipe()
            try:
                child=owner.spawn([current()['executable'],'-B','-c',
                    "import sys,time; data=sys.stdin.buffer.readline();sys.stdout.buffer.write(data);sys.stdout.buffer.flush();time.sleep(60)"],
                    {**child_environment(),**environment_hint()},stdio=(readin,writeout))
                os.close(readin);readin=None;os.close(writeout);writeout=None
                secret=b'private-pipe-test-value\n'
                os.write(writein,secret)
                got=await read_control(threading.Event(),3,fd=readout,limit=128)
                self.assertEqual(got,secret)
                self.assertTrue(owner.close())
                self.assertIsNotNone(child.poll())
                self.assertEqual(await read_control(threading.Event(),1,fd=readout,limit=128),b'')
                self.assertFalse(os.get_inheritable(writein))
                self.assertFalse(os.get_inheritable(readout))
            finally:
                owner.close()
                for fd in (readin,writein,readout,writeout):
                    if fd is not None:os.close(fd)
        finally:owner.close()

    async def test_PP002_reader_is_bounded_and_cancellable(self):
        import inspect
        from launcher.editor_owner import read_control
        self.assertIn('fd',inspect.signature(read_control).parameters)
        r,w=os.pipe()
        try:
            os.write(w,b'x'*17+b'\n')
            with self.assertRaises(ValueError):await read_control(threading.Event(),1,fd=r)
            os.read(r,1)
            with self.assertRaises(TimeoutError):await read_control(threading.Event(),.04,fd=r)
            stop=threading.Event();task=asyncio.create_task(read_control(stop,fd=r))
            await asyncio.sleep(.02);stop.set();self.assertEqual(await task,b'')
        finally:os.close(r);os.close(w)

if __name__=='__main__':unittest.main()
