"""Synthetic TLS material and actual CPython SSL; no real credentials."""
import datetime
import hashlib
import importlib
import importlib.util
import ipaddress
import os
import ssl
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from cryptography import x509
from cryptography.hazmat.primitives import serialization


def handshake(context, certificate):
    client_context = ssl.create_default_context(cadata=certificate.decode('ascii'))
    sin, sout, cin, cout = [ssl.MemoryBIO() for _ in range(4)]
    server = context.wrap_bio(sin, sout, server_side=True)
    client = client_context.wrap_bio(cin, cout, server_side=False, server_hostname='127.0.0.1')
    complete = [False, False]
    for _ in range(100):
        for index, actor in enumerate((server, client)):
            if not complete[index]:
                try:
                    actor.do_handshake()
                    complete[index] = True
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    pass
        data = sout.read()
        if data: cin.write(data)
        data = cout.read()
        if data: sin.write(data)
        if all(complete): return
    raise AssertionError('TLS handshake incomplete')


class TlsContextTests(unittest.TestCase):
    def implementation(self):
        self.assertIsNotNone(importlib.util.find_spec('tls_context'), 'memory TLS loader missing')
        return importlib.import_module('tls_context')

    @unittest.skipUnless(sys.platform == 'linux', 'Linux memfd test; not Windows proof')
    def test_TC003_sealed_anonymous_loader_actual_TLS_and_fd_cleanup(self):
        module = self.implementation()
        self.assertTrue(hasattr(module, 'load_tls_context'), 'owned memory loader missing')
        import fcntl
        material = module.issue_tls_material(lifetime=60)
        original = ssl.SSLContext.load_cert_chain
        fds = []
        def observe(context, certfile, keyfile=None, password=None):
            self.assertIsNone(keyfile)
            self.assertRegex(certfile, r'^/proc/self/fd/[0-9]+$')
            fd = int(certfile.rsplit('/', 1)[1]); fds.append(fd)
            self.assertEqual(os.fstat(fd).st_nlink, 0)
            self.assertFalse(os.get_inheritable(fd))
            # Independent readback uses the stable Linux UAPI constants.
            self.assertEqual(fcntl.fcntl(fd, 1034), 0x000F)
            with self.assertRaises(OSError): os.write(fd, b'no')
            return original(context, certfile, keyfile, password)
        with patch.object(ssl.SSLContext, 'load_cert_chain', observe):
            context = module.load_tls_context(material)
        self.assertEqual(len(fds), 1)
        for fd in fds:
            with self.assertRaises(OSError): os.fstat(fd)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        handshake(context, material.certificate)
        with self.assertRaises(ssl.SSLCertVerificationError):
            handshake(context, module.issue_tls_material(lifetime=60).certificate)

    def test_TC002_bad_lifetime_refused_before_making_a_key(self):
        module = self.implementation()
        with patch.object(module.rsa, 'generate_private_key', side_effect=AssertionError('key generation reached')) as generate:
            for lifetime in (None, True, -1, 0, 29, 3601, 1.5, '60'):
                with self.subTest(lifetime=lifetime), self.assertRaisesRegex(ValueError, 'invalid_tls_lifetime'):
                    module.issue_tls_material(lifetime=lifetime)
            generate.assert_not_called()

    def test_TC001_finite_loopback_certificate_with_exact_pin(self):
        module = self.implementation()
        self.assertTrue(hasattr(module, 'issue_tls_material'), 'TLS material issuer missing')
        material = module.issue_tls_material(lifetime=120)
        cert = x509.load_pem_x509_certificate(material.certificate)
        self.assertEqual(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value,
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]))
        self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertEqual(list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value),
            [x509.ExtendedKeyUsageOID.SERVER_AUTH])
        now = datetime.datetime.now(datetime.timezone.utc)
        self.assertLessEqual(cert.not_valid_before_utc, now)
        self.assertGreater(cert.not_valid_after_utc, now)
        self.assertLessEqual(cert.not_valid_after_utc, now + datetime.timedelta(seconds=120))
        private = serialization.load_pem_private_key(material.private_key, password=None)
        self.assertEqual(private.public_key().public_numbers(), cert.public_key().public_numbers())
        self.assertEqual(material.pin, hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest())
        self.assertNotIn(material.private_key.decode(), repr(material))
        other = module.issue_tls_material(lifetime=120)
        self.assertNotEqual(material.pin, other.pin)
        self.assertFalse(material.private_key == other.private_key)


if __name__ == '__main__':
    unittest.main(verbosity=2)
