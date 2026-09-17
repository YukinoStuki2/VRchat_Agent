"""Windows native ownership tests with injected fake API. Not Windows execution."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
P=Path(__file__).resolve().parents[1]/'Packages~/com.yukino.vrchat-agent-launcher/Editor/Runtime~/windows_processes.py'
class NativeTests(unittest.TestCase):
 def load(self):
  self.assertTrue(P.exists(),'Windows process implementation missing')
  spec=importlib.util.spec_from_file_location('windows_processes',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_suspended_assignment_before_resume(self):
  m=self.load();api=Mock();api.open_parent.return_value=101;api.create_job.return_value=202
  child=Mock();child.thread=303;child.handle=404
  order=[];api.create_suspended.side_effect=lambda *a: order.append('suspended') or child
  api.assign.side_effect=lambda *a:order.append('assign');api.resume.side_effect=lambda *a:order.append('resume')
  api.job_empty.return_value=True
  owner=m.OwnedProcesses(1,api=api);self.assertIs(owner.spawn(['trusted.exe'],{}),child)
  self.assertEqual(order,['suspended','assign','resume']);child.start_reader.assert_called_once()
  owner.close();api.terminate_job.assert_called_once_with(202);api.close_handle.assert_any_call(101);api.close_handle.assert_any_call(202)
 def test_assignment_failure_never_runs_child(self):
  m=self.load();api=Mock();api.open_parent.return_value=101;api.create_job.return_value=202
  child=Mock(handle=404,thread=303);api.create_suspended.return_value=child;api.assign.side_effect=OSError('assign denied');api.job_empty.return_value=True
  owner=m.OwnedProcesses(1,api=api)
  with self.assertRaises(OSError):owner.spawn(['trusted.exe'],{})
  api.resume.assert_not_called();child.stop.assert_called_once();child.close.assert_called_once();owner.close()
 def test_parent_handle_held_no_pid_relookup(self):
  m=self.load();api=Mock();api.open_parent.return_value=2**40;api.create_job.return_value=202;api.parent_alive.side_effect=[True,False];api.job_empty.return_value=True
  owner=m.OwnedProcesses(77,api=api);self.assertTrue(owner.alive());self.assertFalse(owner.alive());owner.close();owner.close()
  api.open_parent.assert_called_once_with(77);self.assertEqual(api.parent_alive.call_args.args,(2**40,));api.terminate_job.assert_called_once()
 def test_fixed_width_structs_and_guard(self):
  m=self.load();import ctypes,os
  self.assertEqual(ctypes.sizeof(m.DWORD),4);self.assertEqual(ctypes.sizeof(m.IO_COUNTERS),48)
  self.assertEqual(m.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,0x2000)
  if os.name!='nt':
   with self.assertRaises(OSError):m.WinAPI()
  source=P.read_text();self.assertIn('handle_list',source);self.assertIn('CREATE_SUSPENDED',source);self.assertNotIn('shell=True',source)
 def test_bounded_stderr_reader_with_real_pipe(self):
  m=self.load();import os
  readfd,writefd=os.pipe();lines=[];api=Mock()
  p=m.NativeProcess(api,11,12,readfd,lines.append);p.start_reader()
  try:
   os.write(writefd,b'x'*5000+b'\nready\r\n');os.close(writefd);writefd=None
   p.reader.join(3);self.assertFalse(p.reader.is_alive());self.assertEqual(lines,['ready'])
   p.close();self.assertIsNone(p.readfd)
  finally:
   if writefd is not None:os.close(writefd)
   p.reader.join(3)
 def test_no_nonexistent_subprocess_flag(self):
  m=self.load();self.assertNotIn('subprocess.CREATE_UNICODE_ENVIRONMENT',P.read_text())
 def test_unconfirmed_cleanup_is_false(self):
  m=self.load();api=Mock();api.open_parent.return_value=101;api.create_job.return_value=202;api.job_empty.return_value=False
  owner=m.OwnedProcesses(1,api=api)
  with patch.object(m.time,'monotonic',side_effect=[0,6]):self.assertFalse(owner.close())

if __name__=='__main__':unittest.main()
