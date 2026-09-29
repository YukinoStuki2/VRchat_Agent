"""Candidate launcher contracts; no real SSH/config/Unity access."""
import importlib
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(case):
    case.assertTrue((ROOT / 'launcher/candidate_launch.py').is_file(),
                    'candidate launcher contract not implemented')
    return importlib.import_module('launcher.candidate_launch')


def config(**changes):
    value = {'project': 'native-project-hash', 'parent_pid': os.getpid(), 'local_port': 34123}
    value.update(changes)
    return value


class Commands(unittest.TestCase):
    def test_L001_only_bundled_runtime_and_structured_ssh(self):
        m = module(self)
        raw = config(ssh={'host': 'fixture.invalid', 'user': 'fixture', 'port': 22022,
                          'remote_port': 34124})
        runtime, ssh = m.build_commands(raw)
        self.assertEqual(runtime, [sys.executable, '-B', str(ROOT / 'runtime'),
                                   '--project', raw['project'], '--port', '34123'])
        self.assertEqual(ssh[:6], [str(m.SSH), '-F', os.devnull, '-v', '-N', '-T'])
        self.assertIn('BatchMode=yes', ssh)
        self.assertIn('StrictHostKeyChecking=yes', ssh)
        self.assertIn('ExitOnForwardFailure=yes', ssh)
        self.assertIn('ProxyCommand=none', ssh)
        self.assertIn('PermitLocalCommand=no', ssh)
        self.assertEqual(ssh[-3:], ['-R', '127.0.0.1:34124:127.0.0.1:34123',
                                    'fixture@fixture.invalid'])
        self.assertIsNone(m.build_commands(config())[1])
        for patch in ({'local_port': 1023}, {'local_port': True}, {'local_port': 65536},
                      {'parent_pid': 0}, {'project': '--help'}, {'project': ' bad'},
                      {'runtime': '/bin/sh'}, {'argv': ['sh']}, {'environment': {}},
                      {'ssh': {'host': '-oProxyCommand=x', 'remote_port': 31000}},
                      {'ssh': {'host': 'a;whoami', 'remote_port': 31000}},
                      {'ssh': {'host': 'fixture.invalid', 'remote_port': 0}},
                      {'ssh': {'host': 'fixture.invalid', 'remote_port': 31000, 'user': 'x@y'}},
                      {'ssh': {'host': 'fixture.invalid', 'remote_port': 31000, 'command': 'sh'}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                m.build_commands(config(**patch))
        for port in (1024, 65535):
            self.assertEqual(m.build_commands(config(local_port=port))[0][-1], str(port))


class ProcessOwnership(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'linux', 'Linux fixture process test')
    def test_L002_owned_child_stderr_and_cleanup(self):
        import signal
        import tempfile
        import time
        m = module(self)
        self.assertTrue(hasattr(m, 'make_owner'), 'candidate process owner is missing')
        lines = []
        owner = m.make_owner(os.getpid())
        child = None
        try:
            child = owner.spawn([sys.executable, '-B', '-c',
                "import os,time; os.write(2,b'x'*5000+b'\\nPermission denied (publickey).'); time.sleep(30)"],
                dict(os.environ), lines.append)
            self.assertTrue(owner.alive())
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not lines:
                time.sleep(.01)
            self.assertTrue(owner.close())
            self.assertEqual(lines, ['Permission denied (publickey).'])
            self.assertIsNotNone(child.poll())
            self.assertTrue(owner.close())
            with self.assertRaises(ProcessLookupError):
                os.killpg(child.pid, 0)
            self.assertFalse(child.reader.is_alive())
        finally:
            owner.close()

    @unittest.skipUnless(sys.platform == 'linux', 'Linux pidfd test')
    def test_L003_exact_parent_exit_observed(self):
        import subprocess
        m = module(self)
        self.assertTrue(hasattr(m, 'make_owner'), 'candidate process owner is missing')
        parent = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(30)'])
        owner = None
        try:
            owner = m.make_owner(parent.pid)
            self.assertTrue(owner.alive())
            parent.terminate()
            parent.wait(timeout=5)
            self.assertFalse(owner.alive())
            with self.assertRaises(OSError):
                owner.spawn([sys.executable, '-c', 'pass'], {})
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=5)
            if owner:
                self.assertTrue(owner.close())


class ProjectExclusivity(unittest.TestCase):
    def test_L004_project_lease_across_processes_released_on_exit(self):
        import subprocess
        import tempfile
        m = module(self)
        self.assertTrue(hasattr(m, 'ProjectLease'), 'cross-process project lease missing')
        with tempfile.TemporaryDirectory() as tmp:
            lease = m.ProjectLease('project-one', root=Path(tmp))
            code = ('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                    'from launcher.candidate_launch import ProjectLease;'
                    'p=ProjectLease(sys.argv[3],root=Path(sys.argv[2]));p.close()')
            def attempt(project):
                return subprocess.run([sys.executable, '-B', '-c', code, str(ROOT), tmp, project],
                                      capture_output=True, text=True, timeout=5)
            try:
                self.assertNotEqual(attempt('project-one').returncode, 0)
                self.assertEqual(attempt('project-two').returncode, 0)
            finally:
                lease.close()
            self.assertEqual(attempt('project-one').returncode, 0)
            self.assertEqual(len(list(Path(tmp).glob('*.lock'))), 2)
            for path in Path(tmp).glob('*.lock'):
                self.assertEqual(path.read_bytes(), b'0')


class Supervision(unittest.TestCase):
    def test_L005_missing_binding_starts_nothing(self):
        from unittest.mock import patch
        m = module(self)
        self.assertTrue(hasattr(m, 'supervise'), 'candidate supervisor missing')
        with patch.object(m, 'make_owner', side_effect=AssertionError('must not spawn')):
            result = m.supervise(config())
        self.assertEqual(result['code'], 'BINDING_REQUIRED')
        self.assertTrue(result['process_cleanup_complete'])

    @unittest.skipUnless(sys.platform == 'linux', 'Linux real process fixture')
    def test_L006_manual_stop_cleans_owned_runtime(self):
        from unittest.mock import patch
        import socket
        import tempfile
        import threading
        import time
        m = module(self)
        self.assertTrue(hasattr(m, 'supervise'), 'candidate supervisor missing')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        raw = config(local_port=port)
        owner = m.make_owner(os.getpid())
        real_spawn = owner.spawn
        captured = []
        stop = threading.Event()
        ready = threading.Event()
        secret = 'SYNTHETIC-NOT-A-REAL-CREDENTIAL'
        binding = m.RuntimeBinding({'VRCHAT_AGENT_FIXTURE_TOKEN': secret}, ready)
        def spawn(args, env, stderr_line_callback=None):
            self.assertEqual(args, m.build_commands(raw)[0])
            self.assertEqual(env['VRCHAT_AGENT_FIXTURE_TOKEN'], secret)
            child = real_spawn([sys.executable, '-B', '-c', 'import time;time.sleep(30)'], env, stderr_line_callback)
            captured.append(child)
            ready.set()
            return child
        owner.spawn = spawn
        def status(value):
            if value['phase'] == 'running':
                stop.set()
        with tempfile.TemporaryDirectory() as tmp:
            lease = m.ProjectLease
            with patch.object(m, 'make_owner', return_value=owner), patch.object(m, 'ProjectLease', side_effect=lambda p: lease(p, root=tmp)):
                try:
                    result = m.supervise(raw, binding=binding, stop=stop, report=status)
                finally:
                    owner.close()
        self.assertEqual(result['code'], 'STOPPED')
        self.assertTrue(result['process_cleanup_complete'])
        self.assertTrue(binding.cancelled.is_set())
        self.assertNotIn(secret, repr(binding))
        self.assertNotIn(secret, repr(result))
        self.assertEqual(len(captured), 1)
        self.assertIsNotNone(captured[0].poll())
        with self.assertRaises(ProcessLookupError):
            os.killpg(captured[0].pid, 0)


if __name__ == '__main__':
    unittest.main()
