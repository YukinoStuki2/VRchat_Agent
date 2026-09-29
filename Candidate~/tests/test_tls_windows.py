"""Real Windows-only memory TLS loader tests. No Unity/product acceptance."""
import os
from pathlib import Path
import ssl
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'runtime'), str(ROOT / 'tests')]
import tls_context
from test_tls_context import handshake


class WindowsTlsTests(unittest.TestCase):
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
