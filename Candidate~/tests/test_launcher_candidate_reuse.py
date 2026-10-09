"""Characterizations of byte-identical legacy ownership; NOT Windows passes."""
import os
import sys
import time
import unittest
from unittest.mock import Mock
from test_launcher_candidate import ROOT, module


class ReusedOwnership(unittest.TestCase):
    def test_L026_runtime_uses_direct_child_and_local_venv_hint_only(self):
        import socket,threading
        from unittest.mock import patch
        from launcher import direct_python
        m=module(self);stop=threading.Event();owner=Mock();child=Mock(pid=4242)
        child.poll.return_value=None;owner.spawn.return_value=child;owner.close.return_value=True
        binding=m.RuntimeBinding({'VRCHAT_AGENT_TEST':'fixture'},threading.Event())
        binding.reload_control=Mock();binding.reload_control.bind.side_effect=lambda pid:binding.ready.set()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        info={'executable':'C:/Python311/python.exe','selected':'C:/fixture/Scripts/python.exe','windows':True}
        def report(row):
            if row['phase']=='running':stop.set()
        with patch.object(direct_python,'current',return_value=info),patch.object(m,'make_owner',return_value=owner):
            result=m.supervise({'project':'direct-child-'+str(os.getpid()),'parent_pid':os.getpid(),'local_port':port},binding=binding,stop=stop,report=report)
        self.assertEqual(result['code'],'STOPPED',result)
        argv,env,_=owner.spawn.call_args.args
        self.assertEqual(argv[0],info['executable'])
        self.assertEqual(env['__PYVENV_LAUNCHER__'],info['selected'])
        self.assertEqual(env['VRCHAT_AGENT_TEST'],'fixture')
        self.assertNotIn('__PYVENV_LAUNCHER__',m.child_environment(source={'__PYVENV_LAUNCHER__':'untrusted'}))
        binding.reload_control.bind.assert_called_once_with(4242)
        self.assertTrue(result['process_cleanup_complete'])

    def test_L025_windows_pid_reaches_reload_supervisor_and_cleanup(self):
        import socket,threading
        from unittest.mock import patch
        from launcher import windows_processes as windows
        m=module(self)
        api=Mock();api.w.WaitForSingleObject.return_value=258
        child=windows.NativeProcess(api,404,303,None,None,pid=4242)
        self.assertEqual(child.pid,4242)
        owner=Mock();owner.spawn.return_value=child;owner.close.side_effect=lambda:child.close() or True
        control=Mock();stop=threading.Event();binding=m.RuntimeBinding({'VRCHAT_AGENT_TEST':'fixture'},threading.Event())
        binding.reload_control=control
        control.bind.side_effect=lambda pid:binding.ready.set()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        raw={'project':'win-pid-adapter','parent_pid':os.getpid(),'local_port':port}
        def report(value):
            if value['phase']=='running':stop.set()
        with patch.object(m,'make_owner',return_value=owner):
            result=m.supervise(raw,binding=binding,stop=stop,report=report)
        control.bind.assert_called_once_with(4242);control.close.assert_called_once()
        self.assertEqual(result['code'],'STOPPED',result)
        self.assertTrue(result['process_cleanup_complete'])
        self.assertEqual(child.pid,4242)
        self.assertIsNone(child.handle)

    def test_L020_windows_assign_before_resume_characterization(self):
        from launcher import windows_processes as m
        api = Mock()
        child = Mock(handle=404, thread=303)
        calls = []
        api.create_suspended.side_effect = lambda *a: calls.append('suspended') or child
        api.assign.side_effect = lambda *a: calls.append('assign')
        api.resume.side_effect = lambda *a: calls.append('resume')
        api.job_empty.return_value = True
        owner = m.OwnedProcesses(77, api=api)
        try:
            self.assertIs(owner.spawn(['approved.exe'], {}), child)
            self.assertEqual(calls, ['suspended', 'assign', 'resume'])
            self.assertTrue(owner.close())
            api.open_parent.assert_called_once_with(77)
        finally:
            owner.close()

    def test_L021_windows_failed_assignment_never_resumes_characterization(self):
        from launcher import windows_processes as m
        api = Mock()
        child = Mock(handle=404, thread=303)
        api.create_suspended.return_value = child
        api.assign.side_effect = OSError('fixture assignment denied')
        api.job_empty.return_value = True
        owner = m.OwnedProcesses(77, api=api)
        try:
            with self.assertRaises(OSError):
                owner.spawn(['approved.exe'], {})
            api.resume.assert_not_called()
            child.stop.assert_called_once()
            child.close.assert_called_once()
        finally:
            self.assertTrue(owner.close())

    def test_L022_reader_byte_bound_and_eof_characterization(self):
        from launcher import windows_processes as m
        for data, expected in ((b'x'*4096, ['x'*4096]), (b'x'*4097, []),
                               (b'x'*6000+b'\nshort-tail', ['short-tail']),
                               (b'Permission denied (publickey).', ['Permission denied (publickey).'])):
            with self.subTest(size=len(data)):
                readfd, writefd = os.pipe()
                lines = []
                child = m.NativeProcess(Mock(), None, None, readfd, lines.append, pid=1)
                child.start_reader()
                try:
                    os.write(writefd, data)
                finally:
                    os.close(writefd)
                child.close()
                self.assertEqual(lines, expected)
                self.assertFalse(child.reader.is_alive())

    @unittest.skipUnless(sys.platform == 'linux', 'Linux fixture only')
    def test_L023_owned_descendant_is_reaped_and_unrelated_child_survives(self):
        import subprocess
        import threading
        m = module(self)
        unrelated = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(30)'])
        owner = m.make_owner(os.getpid())
        ready = threading.Event()
        rows = []
        code = ('import subprocess,sys,time,signal;'
                'p=subprocess.Popen([sys.executable,"-B","-c","import time;time.sleep(30)"]);'
                '\ndef stop(*args):\n p.terminate();p.wait(timeout=3);raise SystemExit(0)'
                '\nsignal.signal(signal.SIGTERM,stop);print(p.pid,file=sys.stderr,flush=True);time.sleep(30)')
        def line(text):
            rows.append(text)
            ready.set()
        try:
            child = owner.spawn([sys.executable, '-B', '-c', code], dict(os.environ), line)
            self.assertTrue(ready.wait(3))
            descendant = int(rows[0])
            self.assertTrue(owner.close())
            self.assertIsNone(unrelated.poll())
            with self.assertRaises(ProcessLookupError):
                os.kill(descendant, 0)
            with self.assertRaises(ProcessLookupError):
                os.killpg(child.pid, 0)
        finally:
            owner.close()
            unrelated.terminate()
            unrelated.wait(timeout=3)


    @unittest.skipUnless(sys.platform == 'linux', 'Linux WNOWAIT ownership test')
    def test_L024_exit_poll_keeps_pid_pinned_until_group_cleanup(self):
        m = module(self)
        owner = m.make_owner(os.getpid())
        try:
            child = owner.spawn([sys.executable, '-B', '-c', 'raise SystemExit(23)'], dict(os.environ))
            deadline = time.monotonic() + 3
            while child.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(child.poll(), 23)
            self.assertIsNone(child.proc.returncode, 'poll must not reap/release the group leader PID')
            info = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            self.assertEqual(info.si_status, 23)
        finally:
            self.assertTrue(owner.close())


if __name__ == '__main__':
    unittest.main()
