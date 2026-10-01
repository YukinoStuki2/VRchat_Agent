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

    async def test_PP003_visible_console_is_explicit_and_never_mixed_with_stdio(self):
        import inspect
        from launcher.windows_processes import OwnedProcesses,WinAPI
        self.assertIn('new_console',inspect.signature(OwnedProcesses.spawn).parameters)
        self.assertIn('new_console',inspect.signature(WinAPI.create_suspended).parameters)
        with self.assertRaises(ValueError):
            WinAPI.create_suspended(None,[],{},None,1,stdio=(0,1),new_console=True)

    async def test_PP004_real_windows_console_is_owned_and_stops(self):
        if os.name!='nt':self.skipTest('actual Windows console required')
        import json,tempfile,time
        owner=make_owner(os.getpid())
        with tempfile.TemporaryDirectory(prefix='vrc-console-fixture-') as td:
            target=Path(td)/'result.json'
            code="import ctypes,json,sys,time;from pathlib import Path;k=ctypes.WinDLL('kernel32');k.GetConsoleWindow.restype=ctypes.c_void_p;Path(sys.argv[1]).write_text(json.dumps({'console':bool(k.GetConsoleWindow()),'stdin':sys.stdin.isatty(),'stdout':sys.stdout.isatty()}));time.sleep(60)"
            try:
                child=owner.spawn([current()['executable'],'-I','-B','-c',code,str(target)],{**child_environment(),**environment_hint()},new_console=True)
                deadline=time.monotonic()+5
                while not target.exists() and time.monotonic()<deadline:await asyncio.sleep(.02)
                self.assertTrue(target.exists(),'visible console child not started')
                result=json.loads(target.read_text())
                self.assertEqual(result,{'console':True,'stdin':True,'stdout':True})
                self.assertTrue(owner.close());self.assertIsNotNone(child.poll())
            finally:owner.close()
        self.assertFalse(Path(td).exists())

if __name__=='__main__':unittest.main()
