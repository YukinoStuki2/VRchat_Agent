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
P=ROOT/'Packages~/com.yukino.vrchat-agent-launcher/Editor/Runtime~/windows_processes.py'
spec=importlib.util.spec_from_file_location('windows_processes',P)
assert spec is not None and spec.loader is not None
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@unittest.skipUnless(os.name=='nt','Requires real Windows kernel, not emulated')
class RealWindowsTests(unittest.TestCase):
 def test_suspended_child_and_descendant_job_cleanup(self):
  owner=m.OwnedProcesses(os.getpid());ready=threading.Event();rows=[]
  code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); print(p.pid,file=sys.stderr,flush=True); time.sleep(60)"
  def line(s):rows.append(s);ready.set()
  grand=None
  try:
   process=owner.spawn([sys.executable,'-I','-c',code],dict(os.environ),line)
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
 def test_supervisor_crash_closes_job(self):
  # The disposable supervisor reports an owned child's PID then is terminated.
  # Holding our own child wait HANDLE avoids PID reuse during verification.
  code="import importlib.util,sys,os,time; sp=importlib.util.spec_from_file_location('w',sys.argv[1]); w=importlib.util.module_from_spec(sp); sp.loader.exec_module(w); o=w.OwnedProcesses(int(sys.argv[2])); p=o.spawn([sys.executable,'-I','-c','import time;time.sleep(60)'],dict(os.environ)); print(o.api.w.GetProcessId(p.handle),flush=True); time.sleep(60)"
  # GetProcessId is a Win32 API, not guaranteed exported by _winapi.
  code=code.replace('o.api.w.GetProcessId(p.handle)',"(lambda k: (setattr(k.GetProcessId,'argtypes',[w.HANDLE]),setattr(k.GetProcessId,'restype',w.DWORD),k.GetProcessId(p.handle))[-1])(o.api.k)")
  child=subprocess.Popen([sys.executable,'-I','-c',code,str(P),str(os.getpid())],stdout=subprocess.PIPE,text=True)
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
 def test_parent_handle_exit_is_observed(self):
  parent=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(60)'])
  owner=None
  try:
   owner=m.OwnedProcesses(parent.pid);self.assertTrue(owner.alive())
   parent.terminate();parent.wait(timeout=10);self.assertFalse(owner.alive())
   with self.assertRaises(OSError):owner.spawn([sys.executable,'-c','pass'],dict(os.environ))
   self.assertTrue(owner.close())
  finally:
   if owner:owner.close()
   if parent.poll() is None:parent.terminate();parent.wait(timeout=10)
 def test_explicit_stop_uses_owned_handle(self):
  owner=m.OwnedProcesses(os.getpid())
  try:
   p=owner.spawn([sys.executable,'-I','-c','import time;time.sleep(60)'],dict(os.environ))
   self.assertIsNone(p.poll());p.stop();self.assertIsNotNone(p.poll());self.assertTrue(owner.close())
  finally:owner.close()

if __name__=='__main__':
 if os.name!='nt':raise SystemExit('Real Windows test requires Windows; do not count a skip as a pass')
 unittest.main(verbosity=2)
