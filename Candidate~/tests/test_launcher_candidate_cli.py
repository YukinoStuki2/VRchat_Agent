"""CLI tests: executes only fail-closed paths, not a real runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from test_launcher_candidate import ROOT, module


class CLI(unittest.TestCase):
    def command(self, *extra):
        self.assertTrue((ROOT / 'launcher/__main__.py').exists(), 'candidate CLI missing')
        return subprocess.run([sys.executable, '-B', str(ROOT / 'launcher'), *extra],
                              capture_output=True, text=True, timeout=5)

    def test_L017_cli_absent_binding_fails_closed(self):
        result = self.command('--project', 'fixture-native-hash', '--parent-pid', str(os.getpid()), '--local-port', '32123')
        self.assertEqual(result.returncode, 2)
        value = json.loads(result.stdout)
        self.assertEqual(value['code'], 'BINDING_REQUIRED')
        self.assertTrue(value['process_cleanup_complete'])
        self.assertEqual(result.stderr, '')

    def test_L018_cli_rejects_shell_and_redacts_invalid_values(self):
        result = self.command('--project', 'fixture', '--parent-pid', str(os.getpid()), '--local-port', '32123',
                              '--shell', 'SYNTHETIC-SECRET')
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('SYNTHETIC-SECRET', result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['code'], 'CONFIG_INVALID')

    def test_L019_import_is_inert(self):
        code = ('import sys;sys.path.insert(0,sys.argv[1]);from unittest.mock import patch;'
                '\nwith patch("subprocess.Popen",side_effect=AssertionError("spawn at import")):'
                '\n import launcher.candidate_launch,launcher.windows_processes,launcher.__main__')
        result = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')


    def test_L025_fixed_binding_adapter_contract_with_synthetic_values(self):
        import tempfile
        from unittest.mock import patch
        from launcher import cli
        raw = {'project': 'fixture', 'parent_pid': os.getpid(), 'local_port': 34567}
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'runtime'
            runtime.mkdir()
            path = runtime / 'launcher_binding.py'
            with patch.object(cli, 'ROOT', Path(tmp)):
                self.assertEqual(cli.load_binding(raw), (None, None))
                path.write_text('from launcher.candidate_launch import RuntimeBinding\n'
                                'import threading\n'
                                'def create_launch_binding(config):\n'
                                ' return RuntimeBinding({"VRCHAT_AGENT_FIXTURE_TOKEN":"synthetic"},threading.Event())\n'
                                'def close_launch_binding(binding):\n return True\n')
                binding, close = cli.load_binding(raw)
                self.assertFalse(binding.ready.is_set())
                self.assertTrue(close(binding))
                path.write_text('def create_launch_binding(config):\n return None\n')
                with self.assertRaises(ValueError):
                    cli.load_binding(raw)


if __name__ == '__main__':
    unittest.main()
