"""Real Linux synthetic child tests; no actual runtime/SSH connection."""
import contextlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from test_launcher_candidate import module, config, ROOT


class ProcessHarness:
    def __init__(self, case, runtime='import time;time.sleep(30)', ssh=None, parent=None):
        self.case, self.m = case, module(case)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.raw = config(local_port=port, **({'parent_pid': parent} if parent else {}))
        if ssh is not None:
            self.raw['ssh'] = {'host': 'fixture.invalid', 'remote_port': 34567}
        self.runtime, self.ssh = runtime, ssh
        self.children, self.reports, self.environments = [], [], []
        self.stop = threading.Event()
        self.binding = self.m.RuntimeBinding({'VRCHAT_AGENT_FIXTURE_TOKEN': 'synthetic-secret'}, threading.Event())
        self.owner = self.m.make_owner(self.raw['parent_pid'])
        self.auto_ready = True
        self.on_status = lambda status: None

    def run(self):
        spawn = self.owner.spawn
        commands = self.m.build_commands(self.raw)
        def fixture_spawn(args, env, stderr_line_callback=None):
            role = 'runtime' if args == commands[0] else 'ssh'
            self.case.assertEqual(args, commands[0 if role == 'runtime' else 1])
            code = self.runtime if role == 'runtime' else self.ssh
            child = spawn([sys.executable, '-B', '-c', code], env, stderr_line_callback)
            self.children.append(child)
            self.environments.append((role, env))
            if role == 'runtime' and self.auto_ready:
                self.binding.ready.set()
            return child
        def report(status):
            self.reports.append(status)
            self.on_status(status)
        with tempfile.TemporaryDirectory() as tmp:
            lease = self.m.ProjectLease
            with patch.object(self.m, 'make_owner', return_value=self.owner), \
                    patch.object(self.m, 'ProjectLease', side_effect=lambda p: lease(p, root=tmp)), \
                    patch.object(self.owner, 'spawn', side_effect=fixture_spawn), \
                    patch.object(self.m, 'START_TIMEOUT', .25):
                try:
                    result = self.m.supervise(self.raw, binding=self.binding, stop=self.stop, report=report)
                finally:
                    self.owner.close()
        for child in self.children:
            self.case.assertIsNotNone(child.poll())
            with self.case.assertRaises(ProcessLookupError):
                os.killpg(child.pid, 0)
            if child.reader:
                self.case.assertFalse(child.reader.is_alive())
        self.case.assertTrue(result['process_cleanup_complete'])
        return result


@unittest.skipUnless(sys.platform == 'linux', 'Linux real process fixture')
class SupervisedProcesses(unittest.TestCase):
    def test_L026_invalid_binding_environment_starts_nothing(self):
        # None must not select the credential-free environment used by SSH.
        for environment in (None, {}, [], '', False, {'VRCHAT_AGENT_TOKEN': ''}):
            with self.subTest(environment=environment):
                h = ProcessHarness(self)
                h.binding.environment = environment
                h.on_status = lambda status: h.stop.set() if status['phase'] == 'running' else None
                result = h.run()
                self.assertEqual(result['code'], 'BINDING_INVALID')
                self.assertEqual(result['phase'], 'blocked')
                self.assertEqual(h.children, [])
                self.assertEqual(h.reports, [])
                self.assertFalse(h.binding.used)
                self.assertFalse(h.binding.started.is_set())

    def test_L007_ssh_auth_classification_survives_exit_255_and_eof(self):
        h = ProcessHarness(self, ssh="import os;os.write(2,b'Permission denied (publickey). synthetic-secret');raise SystemExit(255)")
        result = h.run()
        self.assertEqual(result['code'], 'SSH_AUTH_FAILED')
        self.assertEqual(result['component'], 'ssh')
        self.assertEqual(result['stage'], 'ssh_connecting')
        self.assertNotIn('synthetic-secret', repr(result))
        self.assertEqual(len(h.children), 2)
        self.assertNotIn('VRCHAT_AGENT_FIXTURE_TOKEN', h.environments[1][1])

    def test_L008_runtime_dependency_failure_classified(self):
        h = ProcessHarness(self, runtime="import os;os.write(2,b'ModuleNotFoundError: no module named secret');raise SystemExit(1)")
        h.auto_ready = False
        result = h.run()
        self.assertEqual(result['code'], 'RUNTIME_DEPENDENCY')
        self.assertEqual(result['exit_code'], 1)
        self.assertEqual(result['stage'], 'runtime_starting')

    def test_L009_exact_forward_ack_then_stop(self):
        h = ProcessHarness(self, ssh='')
        marker = f"debug1: remote forward success for: listen 127.0.0.1:34567, connect 127.0.0.1:{h.raw['local_port']}"
        h.ssh = f"import os,time;os.write(2,{(marker + chr(10)).encode()!r});time.sleep(30)"
        h.on_status = lambda status: h.stop.set() if status['code'] == 'FORWARD_ESTABLISHED' else None
        result = h.run()
        self.assertEqual(result['code'], 'STOPPED')
        self.assertTrue(any(s['code'] == 'FORWARD_ESTABLISHED' for s in h.reports))

    def test_L010_parent_exit_stops_running_child(self):
        parent = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(30)'])
        try:
            h = ProcessHarness(self, parent=parent.pid)
            def report(status):
                if status['phase'] == 'running':
                    parent.terminate()
                    parent.wait(timeout=3)
            h.on_status = report
            result = h.run()
            self.assertEqual(result['code'], 'PARENT_EXITED')
        finally:
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=3)

    def test_L011_unknown_listener_is_not_adopted_or_killed(self):
        m = module(self)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            raw = config(local_port=listener.getsockname()[1])
            binding = m.RuntimeBinding({'VRCHAT_AGENT_FIXTURE_TOKEN': 'synthetic'}, threading.Event())
            with tempfile.TemporaryDirectory() as tmp:
                lease = m.ProjectLease
                with patch.object(m, 'ProjectLease', side_effect=lambda p: lease(p, root=tmp)), \
                        patch.object(m, 'make_owner', side_effect=AssertionError('unknown listener must be left alone')):
                    result = m.supervise(raw, binding=binding)
            self.assertEqual(result['code'], 'LOCAL_PORT_BUSY')
            with socket.create_connection(listener.getsockname(), timeout=1) as client:
                accepted, _ = listener.accept()
                accepted.close()

    def test_L012_readiness_deadline_stops_child_without_tunnel(self):
        h = ProcessHarness(self, ssh='raise SystemExit(55)')
        h.auto_ready = False
        result = h.run()
        self.assertEqual(result['code'], 'START_TIMEOUT')
        self.assertEqual(len(h.children), 1)

    def test_L013_binding_failure_revokes_remote_process(self):
        h = ProcessHarness(self)
        h.on_status = lambda status: h.binding.failed.set() if status['phase'] == 'running' else None
        result = h.run()
        self.assertEqual(result['code'], 'BINDING_FAILED')

    def test_L014_stop_does_not_reclassify_cleanup_output_as_auth_failure(self):
        h = ProcessHarness(self, runtime="import os,time;os.write(2,b'ModuleNotFoundError: secret');time.sleep(30)")
        h.on_status = lambda status: h.stop.set() if status['phase'] == 'running' else None
        self.assertEqual(h.run()['code'], 'STOPPED')


class EnvironmentAndDiagnostics(unittest.TestCase):
    def test_L015_environment_does_not_inherit_credentials_or_python_injection(self):
        m = module(self)
        src = {'PATH': '/fixture', 'HOME': '/fixture-home', 'PYTHONPATH': '/injection',
               'LD_PRELOAD': 'bad.so', 'UNITY_MCP_HTTP_HOST': '0.0.0.0', 'HTTP_PROXY': 'bad',
               'VRCHAT_AGENT_SECRET': 'must-not-inherit', 'UNRELATED_API_KEY': 'secret'}
        env = m.child_environment(source=src)
        self.assertEqual(set(src) & set(env), {'PATH', 'HOME'})
        for extra in ({}, {'PYTHONPATH': '/bad'}, {'VRCHAT_AGENT_TOKEN': ''},
                      {'VRCHAT_AGENT_TOKEN': 'a\x00b'}, {'VRCHAT_AGENT_TOKEN': 'x' * 16385}):
            with self.subTest(keys=list(extra)), self.assertRaises(ValueError):
                m.child_environment(extra, src)

    def test_L016_progress_discards_raw_text_and_checks_exact_ports(self):
        m = module(self)
        self.assertTrue(hasattr(m, 'Progress'), 'safe progress classifier missing')
        p = m.Progress('ssh', 34567, 34568)
        p.line('debug1: remote forward success for: listen 127.0.0.1:34567, connect 127.0.0.1:9999')
        self.assertFalse(p.ready)
        p.line('debug1: remote forward success for: listen 127.0.0.1:34567, connect 127.0.0.1:34568')
        self.assertTrue(p.ready)
        p.line('x'*4097 + 'Permission denied')
        self.assertIsNone(p.error)
        p.line('Host key verification failed. secret-path')
        self.assertEqual(p.error, 'SSH_HOSTKEY_FAILED')
        self.assertNotIn('secret-path', repr(vars(p)))


if __name__ == '__main__':
    unittest.main()
