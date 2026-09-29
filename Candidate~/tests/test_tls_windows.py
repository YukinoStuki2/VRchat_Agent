"""Real Windows-only memory TLS loader tests. No Unity/product acceptance."""
import os
from pathlib import Path
import ssl
import sys
import threading
import unittest
from unittest.mock import patch
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'runtime'), str(ROOT / 'tests')]
import tls_context
from test_tls_context import handshake


class WindowsTlsTests(unittest.TestCase):
    def assert_pipe_absent(self, name):
        import pywintypes
        import win32file
        with self.assertRaises(pywintypes.error) as caught:
            handle = win32file.CreateFile(name, win32file.GENERIC_READ, 0, None,
                win32file.OPEN_EXISTING, 0, None)
            handle.Close()
        self.assertEqual(caught.exception.winerror, 2)

    def test_WT002_private_noninheritable_first_instance_and_timeout(self):
        import pywintypes, win32api, win32file, win32pipe, win32security
        from tls_windows import _PemPipe
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
        try:
            owner = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, 1)[0])
        finally:
            token.Close()
        with _PemPipe(b'synthetic-pem-placeholder', timeout=.2) as pipe:
            descriptor = win32security.GetSecurityInfo(pipe.handle, win32security.SE_KERNEL_OBJECT,
                win32security.DACL_SECURITY_INFORMATION)
            self.assertTrue(descriptor.GetSecurityDescriptorControl()[0] & 0x1000)
            dacl = descriptor.GetSecurityDescriptorDacl()
            self.assertEqual(dacl.GetAceCount(), 2)
            sids = set()
            for i in range(dacl.GetAceCount()):
                flags, mask, sid = dacl.GetAce(i)
                self.assertEqual(flags[0], 0)
                sids.add(win32security.ConvertSidToStringSid(sid))
            self.assertEqual(sids, {owner, 'S-1-5-18'})
            self.assertFalse(win32api.GetHandleInformation(pipe.handle) & 1)
            with self.assertRaises(pywintypes.error):
                intruder = win32pipe.CreateNamedPipe(pipe.path,
                    win32pipe.PIPE_ACCESS_OUTBOUND | 0x00080000, 0, 1, 1024, 0, 0, None)
                intruder.Close()
            pipe.worker.join(2)
            self.assertFalse(pipe.worker.is_alive())
            self.assertEqual(pipe.error, 'TimeoutError')
        self.assert_pipe_absent(pipe.path)

    def test_WT003_other_process_rejected_before_any_PEM_byte(self):
        from tls_windows import _PemPipe
        code = """import json,sys,pywintypes,win32file
handle=win32file.CreateFile(sys.argv[1],win32file.GENERIC_READ,0,None,win32file.OPEN_EXISTING,0,None)
try:
 try: count=len(win32file.ReadFile(handle,16384)[1])
 except pywintypes.error as error:
  if error.winerror not in (109,232,233): raise
  count=0
 print(json.dumps({'byte_count':count}))
finally: handle.Close()
"""
        with _PemPipe(b'private-synthetic-placeholder') as pipe:
            with subprocess.Popen([sys.executable, '-I', '-B', '-c', code, pipe.path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
                try:
                    out, err = process.communicate(timeout=8)
                    self.assertEqual(process.returncode, 0, err)
                    self.assertEqual(json.loads(out)['byte_count'], 0)
                    pipe.worker.join(2)
                    self.assertEqual(pipe.error, 'PermissionError')
                finally:
                    if process.poll() is None: process.kill()
                    process.communicate(timeout=5)
        self.assert_pipe_absent(pipe.path)

    def test_WT004_SSL_exception_cancels_unconnected_pipes(self):
        names = []
        def fail(context, certfile, keyfile=None, password=None):
            names.extend((certfile, keyfile))
            raise RuntimeError('synthetic_SSL_failure')
        material = tls_context.issue_tls_material(lifetime=60)
        start = time.monotonic()
        with patch.object(ssl.SSLContext, 'load_cert_chain', fail), self.assertRaisesRegex(RuntimeError, 'synthetic_SSL_failure'):
            tls_context.load_tls_context(material)
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(len(names), 2)
        for name in names: self.assert_pipe_absent(name)
        self.assertFalse([t for t in threading.enumerate() if t.name.startswith('vrchat-tls-pem-')])

    def test_WT005_TerminateProcess_leaves_no_TLS_pipe_or_file(self):
        import msvcrt, tempfile, win32pipe
        code = """import json,os,ssl,sys
sys.path.insert(0,sys.argv[1])
import tls_context
material=tls_context.issue_tls_material(lifetime=60)
def blocked(self,certfile,keyfile=None,password=None):
 print(json.dumps({'pipes':[certfile,keyfile]}),flush=True)
 sys.stdin.read()
 raise RuntimeError('parent must kill child')
ssl.SSLContext.load_cert_chain=blocked
tls_context.load_tls_context(material)
"""
        with tempfile.TemporaryDirectory(prefix='tls-kill-fixture-') as temp:
            with subprocess.Popen([sys.executable, '-I', '-B', '-c', code, str(ROOT / 'runtime')],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=temp, text=True) as process:
                try:
                    handle = msvcrt.get_osfhandle(process.stdout.fileno())
                    deadline = time.monotonic() + 10
                    while win32pipe.PeekNamedPipe(handle, 0)[1] == 0:
                        self.assertIsNone(process.poll(), 'child exited before TLS load')
                        self.assertLess(time.monotonic(), deadline, 'child readiness timeout')
                        time.sleep(.01)
                    names = json.loads(process.stdout.readline())['pipes']
                    self.assertEqual(len(names), 2)
                    for name in names: win32pipe.WaitNamedPipe(name, 100)
                    process.kill()
                    _, err = process.communicate(timeout=5)
                    self.assertIsNotNone(process.returncode)
                    self.assertNotIn('ResourceWarning', err)
                    for name in names: self.assert_pipe_absent(name)
                    self.assertEqual(list(Path(temp).iterdir()), [])
                finally:
                    if process.poll() is None: process.kill()
                    process.communicate(timeout=5)

    def test_WT001_real_memory_pipe_load_and_TLS(self):
        material = tls_context.issue_tls_material(lifetime=60)
        context = tls_context.load_tls_context(material)
        handshake(context, material.certificate)
        with self.assertRaises(ssl.SSLCertVerificationError):
            handshake(context, tls_context.issue_tls_material(lifetime=60).certificate)
        self.assertFalse([t for t in threading.enumerate() if t.name.startswith('vrchat-tls-pem-')])


if __name__ == '__main__':
    if sys.platform != 'win32':
        print('Windows kernel required; not verified on this platform')
        raise SystemExit(2)
    unittest.main(verbosity=2)
