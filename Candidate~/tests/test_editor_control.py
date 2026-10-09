"""Actual C# Process -> Python owner/runtime; Unity TLS peer is synthetic.
No user project, permissions UI, app-domain reload or native client approval.
"""
import asyncio
import os
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'runtime'),str(ROOT/'dependencies/mcp-1.29.1')]
from test_editor_owner import environment
WIRE_DLL=None
DOTNET=None


def detach_fixture_code(project="restore-fixture"):
    return "import sys,os,time,json,hashlib,threading\nsys.path.insert(0,ROOT)\nfrom launcher.peer_identity import PeerProcess\nfrom launcher.peer_channel import PeerListener\nassert sys.stdin.readline()=='start\\n'\nstop=threading.Event()\nwith PeerProcess(os.getppid()) as parent,PeerProcess(os.getpid()) as own,PeerListener() as listener,PeerListener() as next_listener:\n def send(c,obj):c.send(json.dumps(obj).encode())\n def recv(c):return json.loads(c.receive())\n expires=int(time.time())+30\n binding={'endpoint':'wss://127.0.0.1:18000/hub/plugin','pin':'a'*64,'unity_bearer':'fixture_no_authority_'+'a'*32,'expires_at':expires}\n print(json.dumps({'kind':'unity_binding','version':3,'owner_pid':os.getpid(),'project':'restore-fixture','clients':[],**binding,\n  'reload':{'address':listener.address,'created':own.identity[1]}}),flush=True)\n with listener.accept(parent,deadline=time.monotonic()+10,stop=stop) as c:\n  assert recv(c)=={'kind':'hello','version':1,'project':'restore-fixture'}\n  send(c,{'kind':'editor_control_ready','version':1});print(json.dumps({'kind':'ready'}),flush=True)\n  request=recv(c);assert request['kind']=='arm';hid=request['handoff_id'];raw=request['transfers']\n  send(c,{'kind':'armed','handoff_id':hid,'digests':[hashlib.sha256(s.encode()).hexdigest() for s in raw],'next_address':next_listener.address})\n  assert recv(c)=={'kind':'detach','handoff_id':hid};send(c,{'kind':'detached','handoff_id':hid})\n  try:c.receive();raise AssertionError('unexpected bytes')\n  except EOFError:pass\n assert sys.stdin.read()==''\n with open(os.devnull,'wb',buffering=0) as sink:\n  os.dup2(sink.fileno(),1,inheritable=False);os.dup2(sink.fileno(),2,inheritable=False)\n with next_listener.accept(parent,deadline=time.monotonic()+10,stop=stop) as c:\n  command=recv(c);assert command['kind'] in ('resume','cancel') and command['handoff_id']==hid\n  if command['kind']=='resume':\n   send(c,{'kind':'reattach','handoff_id':hid,'transfers':raw,'unity_binding':binding})\n   command=recv(c)\n   if command['kind']=='commit':\n    send(c,{'kind':'committed','handoff_id':hid});assert recv(c)=={'kind':'stop'}\n   else:assert command=={'kind':'stop'}\n  send(c,{'kind':'stopped','phase':'stopped','process_cleanup_complete':True,\n   'probe_cleanup_complete':True,'probe_session_cleanup_confirmed':True,'reload_control_cleanup_complete':True})\n".replace("restore-fixture",project)

class CompiledEditorControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_CE001_actual_csharp_owner_control_and_tls_cleanup(self):
        self.assertTrue(WIRE_DLL and Path(WIRE_DLL).is_file(),'fresh compiled bootstrap required')
        process=await asyncio.create_subprocess_exec(DOTNET,WIRE_DLL,'--reload-control-tests',sys.executable,
            str(ROOT/'launcher/editor_owner.py'),env=environment(),stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            out,err=await asyncio.wait_for(process.communicate(),35)
            self.assertEqual(process.returncode,0,(out+err).decode('utf-8',errors='replace'))
            ids=[line.split()[1] for line in out.decode().splitlines() if line.startswith('PASS ')]
            self.assertEqual(ids,['ECP003','ECP004'])
            self.assertNotIn(b'ResourceWarning',out+err)
        finally:
            if process.returncode is None:
                process.kill();await process.communicate()
                self.fail('compiled owner required forced cleanup')
    async def test_CE002_restore_api_uses_os_peer_and_refuses_changed_transfer(self):
        import tempfile
        from launcher.direct_python import current
        # Typed protocol fixture, not runtime authority; secret-free source file.
        code="""import sys,os,time,json,hashlib,threading
sys.path.insert(0,ROOT)
from launcher.peer_identity import PeerProcess
from launcher.peer_channel import PeerListener
stop=threading.Event()
try:
 with PeerProcess(os.getppid()) as parent,PeerProcess(os.getpid()) as own,PeerListener() as listener:
  raw='{}';hid='d'*32;expires=int(time.time())+20
  ticket={'version':1,'project':'restore-fixture','owner_pid':os.getpid(),'created':own.identity[1],'address':listener.address,
    'expires_at':expires,'handoff_id':hid,'digests':[hashlib.sha256(raw.encode()).hexdigest()],'remote_handoff':False,'local_codex':False}
  print(json.dumps(ticket),flush=True)
  with listener.accept(parent,deadline=time.monotonic()+10,stop=stop) as channel:
   request=json.loads(channel.receive());assert request=={'kind':'resume','version':1,'project':'restore-fixture','handoff_id':hid}
   transfer=raw if sys.argv[1]=='valid' else '{"changed":true}'
   channel.send(json.dumps({'kind':'reattach','handoff_id':hid,'transfers':[transfer],'unity_binding':{'endpoint':'wss://127.0.0.1:18000/hub/plugin',
    'pin':'a'*64,'unity_bearer':'fixture_non_authority_bearer_'+'a'*32,'expires_at':expires}}).encode())
   if sys.argv[1]=='valid':
    assert json.loads(channel.receive())['kind']=='commit'
    channel.send(json.dumps({'kind':'committed','handoff_id':hid}).encode())
    assert json.loads(channel.receive())=={'kind':'stop'}
    channel.send(json.dumps({'kind':'stopped','phase':'stopped','process_cleanup_complete':True,'probe_cleanup_complete':True,
     'probe_session_cleanup_confirmed':True,'reload_control_cleanup_complete':True}).encode())
except (EOFError,TimeoutError,PermissionError):
 if sys.argv[1]=='valid':raise
finally:
 stop.set()
"""
        with tempfile.TemporaryDirectory(prefix='editor-restore-fixture-') as td:
            script=Path(td)/'peer.py';script.write_text('ROOT='+repr(str(ROOT))+'\n'+code,encoding='utf-8')
            process=await asyncio.create_subprocess_exec(DOTNET,WIRE_DLL,'--restore-tests',current()['executable'],str(script),env=environment(),
                stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            try:
                out,err=await asyncio.wait_for(process.communicate(),30)
                self.assertEqual(process.returncode,0,(out+err).decode('utf-8',errors='replace'))
                self.assertEqual([line.split()[1] for line in out.decode().splitlines() if line.startswith('PASS ')],['ECP005','ECP006'])
            finally:
                if process.returncode is None:process.kill();await process.communicate();self.fail('restore fixture forced cleanup')

    async def test_CE003_arm_detach_restore_uses_same_original_owner(self):
        import tempfile,shutil
        code=detach_fixture_code()
        with tempfile.TemporaryDirectory(prefix='editor-detach-fixture-') as td:
            script=Path(td)/'editor_owner.py';script.write_text('ROOT='+repr(str(ROOT))+'\n'+code,encoding='utf-8')
            shutil.copyfile(ROOT/'launcher/direct_python.py',Path(td)/'direct_python.py')
            process=await asyncio.create_subprocess_exec(DOTNET,WIRE_DLL,'--cancel-tests' if getattr(self,'cancel_mode',False) else '--prepare-tests',sys.executable,str(script),env=environment(),
                stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            try:
                out,err=await asyncio.wait_for(process.communicate(),35)
                self.assertEqual(process.returncode,0,(out+err).decode('utf-8',errors='replace'))
                self.assertEqual([line.split()[1] for line in out.decode().splitlines() if line.startswith('PASS ')],['ECP008' if getattr(self,'cancel_mode',False) else 'ECP007'])
            finally:
                if process.returncode is None:process.kill();await process.communicate();self.fail('detach fixture forced cleanup')

    async def test_CE004_stop_after_detach_cancels_original_owner(self):
        self.cancel_mode=True
        await self.test_CE003_arm_detach_restore_uses_same_original_owner()
