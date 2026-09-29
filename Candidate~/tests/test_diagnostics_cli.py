"""Local operator approval and bounded stdio lifetime; synthetic fixtures only."""
import asyncio
import importlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'diagnostics'))
import snapshot


class Console(io.StringIO):
    """Simulated local terminal, not a claim of human approval."""
    def __init__(self, accept=True):
        super().__init__()
        self.accept = accept
    def isatty(self):
        return True
    def readline(self, *args):
        import re
        digest = re.search(r'APPROVE ([a-f0-9]{64})', self.getvalue())
        return ('APPROVE ' + digest.group(1) if self.accept and digest else 'no') + '\n'


class OperatorTests(unittest.TestCase):
    def module(self):
        self.assertTrue((BASE / 'diagnostics/cli.py').exists(), 'standalone local approval CLI missing')
        return importlib.import_module('cli')

    @unittest.skipUnless(sys.platform == 'linux', 'POSIX no-console subprocess test')
    def test_DC004_cli_rejects_piped_approval_without_local_console(self):
        import os
        import subprocess
        with tempfile.TemporaryDirectory(prefix='dc-no-console-') as home:
            source = Path(home) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('synthetic not delivered')
            env = {'HOME': home, 'TMPDIR': home, 'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'}
            result = subprocess.run([sys.executable, '-B', str(BASE / 'diagnostics/cli.py'), 'serve',
                '--root', str(source), '--file', 'Editor.log', '--task', 'fixture'],
                input='APPROVE anything\n', capture_output=True, text=True, env=env,
                start_new_session=True, timeout=15)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertNotIn('synthetic not delivered', result.stderr)
            self.assertIn('local_console', result.stderr)
            self.assertEqual(sorted(p.name for p in Path(home).iterdir()), ['source'])

    def test_DC001_full_redacted_preview_before_exact_local_confirmation(self):
        cli = self.module()
        with tempfile.TemporaryDirectory(prefix='dc-preview-') as home:
            source = Path(home) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('token=synthetic-only-secret\ncompiler 中文 error\n')
            with snapshot.capture(source, ['Editor.log'], task_id='fixture-preview', temp_parent=home) as snap:
                console = Console()
                digest = cli.preview_confirm(snap, console, console)
                self.assertRegex(digest, r'^[a-f0-9]{64}$')
                self.assertIn('[REDACTED]', console.getvalue())
                self.assertNotIn('synthetic-only-secret', console.getvalue())
                self.assertIn('compiler', console.getvalue())
                self.assertIn('fixture-preview', console.getvalue())
                self.assertIn('Editor.log', console.getvalue())
                self.assertEqual(digest, cli.snapshot_digest(snap))
                declined = Console(accept=False)
                self.assertIsNone(cli.preview_confirm(snap, declined, declined))
                with self.assertRaisesRegex(ValueError, 'local_console'):
                    cli.preview_confirm(snap, io.StringIO('yes\n'), io.StringIO())
            self.assertFalse(snap.root.parent.exists())


class ApprovedServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_DC003_deadline_or_server_failure_revokes_and_awaits_cleanup(self):
        from dataclasses import replace
        from unittest.mock import patch
        import time
        import cli
        self.assertTrue(hasattr(cli, 'serve_snapshot'), 'bounded stdio owner missing')
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory(prefix='dc-lifetime-') as home:
                source = Path(home) / 'source'
                source.mkdir()
                (source / 'Editor.log').write_text('fixture')
                finalized = asyncio.Event()
                class Server:
                    async def run_stdio_async(self, **kwargs):
                        try:
                            if fail:
                                raise RuntimeError('fixture-server-failure')
                            await asyncio.Event().wait()
                        finally:
                            await asyncio.sleep(0)
                            finalized.set()
                with snapshot.capture(source, ['Editor.log'], task_id='fixture', temp_parent=home) as original:
                    snap = replace(original, expires_at=time.monotonic() + 0.05)
                    digest = cli.snapshot_digest(snap)
                    with patch('server.create_server', return_value=Server()):
                        if fail:
                            with self.assertRaisesRegex(RuntimeError, 'fixture-server-failure'):
                                await cli.serve_snapshot(snap, digest)
                        else:
                            await asyncio.wait_for(cli.serve_snapshot(snap, digest), 3)
                    self.assertTrue(finalized.is_set())
                    self.assertFalse(snap.valid())
                    self.assertFalse(snap._active.is_set())
                self.assertFalse(snap.root.parent.exists())

    async def test_DC002_approved_digest_blocks_modified_snapshot_before_backend(self):
        from fastmcp import Client
        from server import create_server
        import cli
        with tempfile.TemporaryDirectory(prefix='dc-approved-') as home:
            source = Path(home) / 'source'
            source.mkdir()
            (source / 'Editor.log').write_text('fixture compiler error')
            with snapshot.capture(source, ['Editor.log'], task_id='fixture', temp_parent=home) as snap:
                console = Console()
                digest = cli.preview_confirm(snap, console, console)
                self.assertIn('approved_digest', __import__('inspect').signature(create_server).parameters,
                              'server cannot bind operator preview digest')
                server = create_server(snap, approved_digest=digest)
                target = snap.root / 'Editor.log'
                target.chmod(0o600)
                target.write_text('changed after operator preview')
                async with Client(server) as client:
                    with self.assertRaises(Exception) as denied:
                        await client.list_tools()
                    self.assertIn('approved_snapshot_changed', str(denied.exception))
                self.assertFalse(snap.valid())


if __name__ == '__main__':
    unittest.main(verbosity=2)
