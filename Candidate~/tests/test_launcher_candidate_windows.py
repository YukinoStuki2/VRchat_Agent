"""Real Windows process tests. Explicit invocation only; no Unity/SSH/network."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'launcher/windows_processes.py'
spec=importlib.util.spec_from_file_location('windows_processes',P)
assert spec is not None and spec.loader is not None
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@unittest.skipUnless(os.name=='nt','Requires real Windows kernel, not emulated')
class RealWindowsTests(unittest.TestCase):
 def test_W001_suspended_child_and_descendant_job_cleanup(self):
  owner=m.OwnedProcesses(os.getpid());ready=threading.Event();rows=[]
  code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)']); print(p.pid,file=sys.stderr,flush=True); time.sleep(60)"
  def line(s):rows.append(s);ready.set()
  grand=None
  try:
   process=owner.spawn([sys.executable,'-B','-I','-c',code],dict(os.environ),line)
   self.assertTrue(ready.wait(10),'child stdout redirected, stderr pipe failed')
   self.assertIsNone(process.poll());self.assertTrue(owner.alive())
   grand=owner.api.w.OpenProcess(0x00100000,False,int(rows[0]))
   self.assertEqual(owner.api.w.WaitForSingleObject(grand,0),258)
   self.assertTrue(owner.close(),'job accounting did not reach zero')
   self.assertEqual(owner.api.w.WaitForSingleObject(grand,5000),0,'descendant leaked')
   self.assertFalse(process.reader.is_alive())
  finally:
   owner.close()
   if grand is not None:owner.api.close_handle(grand)
 def test_W002_supervisor_crash_closes_job(self):
  # The disposable supervisor reports an owned child's PID then is terminated.
  # Holding our own child wait HANDLE avoids PID reuse during verification.
  code="import importlib.util,sys,os,time; sp=importlib.util.spec_from_file_location('w',sys.argv[1]); w=importlib.util.module_from_spec(sp); sp.loader.exec_module(w); o=w.OwnedProcesses(int(sys.argv[2])); p=o.spawn([sys.executable,'-B','-I','-c','import time;time.sleep(60)'],dict(os.environ)); print(o.api.w.GetProcessId(p.handle),flush=True); time.sleep(60)"
  # GetProcessId is a Win32 API, not guaranteed exported by _winapi.
  code=code.replace('o.api.w.GetProcessId(p.handle)',"(lambda k: (setattr(k.GetProcessId,'argtypes',[w.HANDLE]),setattr(k.GetProcessId,'restype',w.DWORD),k.GetProcessId(p.handle))[-1])(o.api.k)")
  child=subprocess.Popen([sys.executable,'-B','-I','-c',code,str(P),str(os.getpid())],stdout=subprocess.PIPE,text=True)
  handle=None;api=m.WinAPI()
  try:
   # Bound read with a thread because the subprocess may fail before printing.
   rows=[];reader=threading.Thread(target=lambda:rows.append(child.stdout.readline()),daemon=True);reader.start();reader.join(15)
   self.assertFalse(reader.is_alive(),'test supervisor did not announce child')
   self.assertTrue(rows and rows[0].strip(),'test supervisor startup failed')
   handle=api.w.OpenProcess(0x00100000,False,int(rows[0]))
   child.terminate();child.wait(timeout=10)
   self.assertEqual(api.w.WaitForSingleObject(handle,10000),0,'crash leaked child')
  finally:
   if child.poll() is None:child.terminate();child.wait(timeout=10)
   child.stdout.close()
   if handle:api.close_handle(handle)
 def test_W003_parent_handle_exit_is_observed(self):
  parent=subprocess.Popen([sys.executable,'-B','-I','-c','import time;time.sleep(60)'])
  owner=None
  try:
   owner=m.OwnedProcesses(parent.pid);self.assertTrue(owner.alive())
   parent.terminate();parent.wait(timeout=10);self.assertFalse(owner.alive())
   with self.assertRaises(OSError):owner.spawn([sys.executable,'-B','-c','pass'],dict(os.environ))
   self.assertTrue(owner.close())
  finally:
   if owner:owner.close()
   if parent.poll() is None:parent.terminate();parent.wait(timeout=10)
 def test_W004_explicit_stop_uses_owned_handle(self):
  owner=m.OwnedProcesses(os.getpid())
  try:
   p=owner.spawn([sys.executable,'-B','-I','-c','import time;time.sleep(60)'],dict(os.environ))
   self.assertIsNone(p.poll());p.stop();self.assertIsNotNone(p.poll());self.assertTrue(owner.close())
  finally:owner.close()

 def test_W005_crash_after_create_before_python_returns_has_no_orphan(self):
  # A safety job owned by this test bounds even the OLD implementation's leak.
  # The inner supervisor crashes before assign() can execute. Pin a wait HANDLE
  # before terminating it, so cleanup never guesses by process name or reused PID.
  code="""import importlib.util,sys,os,time
sp=importlib.util.spec_from_file_location('w',sys.argv[1]); w=importlib.util.module_from_spec(sp); sp.loader.exec_module(w)
o=w.OwnedProcesses(int(sys.argv[2])); original=o.api.create_suspended
k=o.api.k; k.GetProcessId.argtypes=[w.HANDLE]; k.GetProcessId.restype=w.DWORD
def intercept(*a,**kw):
 p=original(*a,**kw)
 print(k.GetProcessId(p.handle),file=sys.stderr,flush=True)
 time.sleep(60)  # killed by the observer while still before Python return
 return p
o.api.create_suspended=intercept
o.spawn([sys.executable,'-B','-I','-c','import time;time.sleep(60)'],dict(os.environ))
"""
  safety=m.OwnedProcesses(os.getpid());ready=threading.Event();rows=[];handle=None
  def line(text):
   if text.isdecimal():rows.append(text);ready.set()
  try:
   supervisor=safety.spawn([sys.executable,'-B','-I','-c',code,str(P),str(os.getpid())],dict(os.environ),line)
   self.assertTrue(ready.wait(15),'supervisor did not reach create-return seam')
   handle=safety.api.w.OpenProcess(0x00100000,False,int(rows[0]))
   self.assertEqual(safety.api.w.WaitForSingleObject(handle,0),258)
   supervisor.stop()
   self.assertEqual(safety.api.w.WaitForSingleObject(handle,5000),0,'create/assign crash window leaked suspended child')
  finally:
   self.assertTrue(safety.close(),'safety job failed to clean old implementation leak')
   if handle:
    try:self.assertEqual(safety.api.w.WaitForSingleObject(handle,5000),0,'test fixture cleanup failed')
    finally:safety.api.close_handle(handle)

 def test_W006_unicode_env_and_explicit_handle_list_survive_native_creation(self):
  owner=m.OwnedProcesses(os.getpid());ready=threading.Event();rows=[]
  readfd,writefd=os.pipe();os.set_inheritable(writefd,True)
  stray=owner.api.m.get_osfhandle(writefd)
  code="""import ctypes as c,os,sys,json,time
k=c.WinDLL('kernel32',use_last_error=True); k.WriteFile.argtypes=[c.c_void_p,c.c_void_p,c.c_uint32,c.POINTER(c.c_uint32),c.c_void_p];k.WriteFile.restype=c.c_int
n=c.c_uint32(); leaked=bool(k.WriteFile(int(sys.argv[1]),b'X',1,c.byref(n),None))
print(json.dumps({'stray_writable':leaked,'value':os.environ.get('CANDIDATE_FIXTURE_UNICODE'),'arg':sys.argv[2]}),file=sys.stderr,flush=True)
time.sleep(60)
"""
  def line(text):rows.append(text);ready.set()
  try:
   env=dict(os.environ);env['CANDIDATE_FIXTURE_UNICODE']='中文 空格'
   process=owner.spawn([sys.executable,'-B','-I','-c',code,str(stray),'引号 " 与尾斜线\\'],env,line)
   self.assertTrue(ready.wait(10));value=json.loads(rows[0])
   self.assertEqual(value,{'stray_writable':False,'value':'中文 空格','arg':'引号 " 与尾斜线\\'})
   self.assertTrue(owner.close())
  finally:
   self.assertTrue(owner.close());os.close(writefd);os.close(readfd)

if __name__=='__main__':
 if os.name!='nt':raise SystemExit('Real Windows test requires Windows; do not count a skip as a pass')
 unittest.main(verbosity=2)
