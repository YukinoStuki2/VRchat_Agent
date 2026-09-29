"""Real private pipe + owned child, synthetic Unity peer; not Editor acceptance."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/'launcher/editor_owner.py'
sys.path[:0]=[str(ROOT/'runtime'),str(ROOT/'dependencies/mcp-1.29.1')]


def environment():
    names=('SystemRoot','WINDIR','PATH','COMSPEC','PATHEXT','TEMP','TMP','HOME','USERPROFILE')
    return {**{k:os.environ[k] for k in names if k in os.environ},
        'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','DISABLE_TELEMETRY':'true'}


class EditorOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def spawn(self,parent=None):
        self.assertTrue(ENTRY.exists(),'editor owner entry missing')
        return await asyncio.create_subprocess_exec(sys.executable,'-B',str(ENTRY),
            '--project','fixture-project','--parent-pid',str(os.getpid() if parent is None else parent),
            env=environment(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)

    async def stop(self,p):
        if p.returncode is None:
            try:p.stdin.write(b'stop\n');await p.stdin.drain();p.stdin.close()
            except (BrokenPipeError,ConnectionResetError):pass
        try:return await asyncio.wait_for(p.communicate(),12)
        except TimeoutError:
            p.kill();await p.communicate();raise

    async def test_EB001_private_bundle_then_ready_and_clean_stop(self):
        import websockets
        p=await self.spawn()
        try:
            p.stdin.write(b'start\n');await p.stdin.drain()
            line=await asyncio.wait_for(p.stdout.readline(),10)
            bundle=json.loads(line)
            self.assertEqual(set(bundle),{'kind','version','owner_pid','project','endpoint','pin','unity_bearer','expires_at'})
            self.assertEqual(bundle['kind'],'unity_binding')
            self.assertEqual(bundle['owner_pid'],p.pid)
            self.assertEqual(bundle['project'],'fixture-project')
            self.assertNotIn(b'PRIVATE KEY',line)
            # SSL pin checked manually by this synthetic peer before sending bearer.
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
            from urllib.parse import urlparse
            port=urlparse(bundle['endpoint']).port
            reader,writer=await asyncio.open_connection('127.0.0.1',port,ssl=context)
            self.assertEqual(hashlib.sha256(writer.get_extra_info('ssl_object').getpeercert(True)).hexdigest(),bundle['pin'])
            writer.close();await writer.wait_closed()
            async with websockets.connect(bundle['endpoint'],ssl=context,proxy=None,
                    additional_headers={'Authorization':'Bearer '+bundle['unity_bearer']}) as ws:
                self.assertEqual(json.loads(await ws.recv())['type'],'welcome')
                await ws.send(json.dumps({'type':'register','project_hash':'fixture-project','project_name':'TEST','unity_version':'FIXTURE'}))
                self.assertEqual(json.loads(await ws.recv())['type'],'registered')
                command=json.loads(await ws.recv())
                self.assertEqual(command['params']['kind'],'status')
                await ws.send(json.dumps({'type':'command_result','id':command['id'],
                    'result':{'status':'success','result':{'success':True,'data':{'read_only':True}}}}))
                ready=json.loads(await asyncio.wait_for(p.stdout.readline(),3))
                self.assertEqual(ready['kind'],'ready')
                out,err=await self.stop(p)
                final=json.loads(out.decode().splitlines()[-1])
                self.assertEqual(final['kind'],'stopped');self.assertTrue(final['process_cleanup_complete'])
                self.assertTrue(final['probe_cleanup_complete']);self.assertTrue(final['probe_session_cleanup_confirmed'])
                self.assertEqual(p.returncode,0,err.decode())
                self.assertNotIn(bundle['unity_bearer'].encode(),out+err)
            with socket.socket() as s:self.assertNotEqual(s.connect_ex(('127.0.0.1',port)),0)
        finally:
            if p.returncode is None:await self.stop(p)

    async def test_EB002_wrong_parent_refused_without_bundle(self):
        p=await self.spawn(parent=1)
        out,err=await asyncio.wait_for(p.communicate(b'start\n'),5)
        self.assertNotEqual(p.returncode,0)
        self.assertNotIn(b'unity_bearer',out+err);self.assertNotIn(b'Traceback',out+err)

    async def test_EB003_eof_before_start_creates_no_runtime(self):
        p=await self.spawn()
        try:out,err=await asyncio.wait_for(p.communicate(b''),5)
        finally:
            if p.returncode is None:await self.stop(p)
        self.assertNotIn(b'unity_bearer',out+err)
        self.assertNotIn(b'Traceback',out+err)

    async def test_EB005_oversize_start_refused_without_bundle(self):
        p=await self.spawn()
        try:out,err=await asyncio.wait_for(p.communicate(b'x'*64+b'\n'),5)
        finally:
            if p.returncode is None:await self.stop(p)
        self.assertNotEqual(p.returncode,0);self.assertNotIn(b'unity_bearer',out+err)

    async def test_EB006_eof_after_binding_before_unity_cleans_listener(self):
        from urllib.parse import urlparse
        p=await self.spawn()
        try:
            p.stdin.write(b'start\n');await p.stdin.drain()
            bundle=json.loads(await asyncio.wait_for(p.stdout.readline(),10))
            port=urlparse(bundle['endpoint']).port
            p.stdin.close();out,err=await self.stop(p)
            final=json.loads(out.decode().splitlines()[-1])
            self.assertTrue(final['process_cleanup_complete'])
            self.assertTrue(final['probe_cleanup_complete'])
            self.assertNotIn(bundle['unity_bearer'].encode(),out+err)
            with socket.socket() as s:self.assertNotEqual(s.connect_ex(('127.0.0.1',port)),0)
        finally:
            if p.returncode is None:await self.stop(p)

    async def test_EB007_parent_crash_closes_owner_and_listener(self):
        sys.path.insert(0,str(ROOT))
        from launcher.candidate_launch import make_owner
        code = """import json,os,subprocess,sys
from urllib.parse import urlparse
p=subprocess.Popen([sys.executable,'-I','-B',sys.argv[1],'--project','fixture-project','--parent-pid',str(os.getpid())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
p.stdin.write(b'start\\n');p.stdin.flush()
b=json.loads(p.stdout.readline())
print(json.dumps({'port':urlparse(b['endpoint']).port,'owner_pid':p.pid}),flush=True)
sys.stdin.readline()
os._exit(0)
"""
        parent=await asyncio.create_subprocess_exec(sys.executable,'-I','-B','-c',code,str(ENTRY),env=environment(),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        pin=None
        try:
            assert parent.stdout is not None
            row=json.loads(await asyncio.wait_for(parent.stdout.readline(),10))
            pin=make_owner(row['owner_pid'])
            self.assertTrue(pin.alive())
            await asyncio.wait_for(parent.communicate(b'crash\n'),5)
            deadline=time.monotonic()+10
            while pin.alive() and time.monotonic()<deadline:await asyncio.sleep(.05)
            self.assertFalse(pin.alive(),'owned launcher survived parent crash')
            with socket.socket() as s:self.assertNotEqual(s.connect_ex(('127.0.0.1',row['port'])),0)
        finally:
            if parent.returncode is None:parent.kill();await parent.communicate()
            if pin is not None:pin.close()

    async def test_EB008_actual_interpreter_parent_and_private_pipes(self):
        code = """import os,sys,json
sys.path.insert(0,sys.argv[1])
from launcher.editor_owner import private_pipes
row={'pid':os.getpid(),'ppid':os.getppid()}
try:row['private_pipes']=private_pipes()
except Exception as exc:row['error_type']=type(exc).__name__
print(json.dumps(row),flush=True)
"""
        p=await asyncio.create_subprocess_exec(sys.executable,'-B','-c',code,str(ROOT),
            env=environment(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        out,err=await asyncio.wait_for(p.communicate(),5)
        self.assertEqual(p.returncode,0)
        row=json.loads(out)
        self.assertEqual(row,{'pid':p.pid,'ppid':os.getpid(),'private_pipes':True})

    async def test_EB004_nonpipe_output_refused(self):
        self.assertTrue(ENTRY.exists())
        with tempfile.TemporaryFile() as output:
            p=await asyncio.create_subprocess_exec(sys.executable,'-B',str(ENTRY),
                '--project','fixture-project','--parent-pid',str(os.getpid()),env=environment(),
                stdin=asyncio.subprocess.PIPE,stdout=output,stderr=asyncio.subprocess.PIPE)
            _,err=await asyncio.wait_for(p.communicate(b'start\n'),5)
            output.seek(0);out=output.read()
            self.assertNotEqual(p.returncode,0);self.assertNotIn(b'unity_bearer',out+err)

if __name__=='__main__':unittest.main(verbosity=2)
