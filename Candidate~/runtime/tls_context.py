"""Ephemeral loopback TLS material; no filesystem or global trust changes.

PEM bytes are only for an owned child loader, not logs/argv/client config.
This module does not establish trusted bootstrap or client delivery.
"""
from dataclasses import dataclass, field
import datetime
import hashlib
import ipaddress
import os
import ssl
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@dataclass(frozen=True, slots=True)
class TlsMaterial:
    certificate: bytes
    private_key: bytes = field(repr=False)
    pin: str


def issue_tls_material(*, lifetime=600):
    if type(lifetime) is not int or not 30 <= lifetime <= 3600:
        raise ValueError('invalid_tls_lifetime')
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'VRChat Agent one-run loopback')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(private.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(seconds=30))
        .not_valid_after(now + datetime.timedelta(seconds=lifetime))
        .add_extension(x509.SubjectAlternativeName([
            x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(private, hashes.SHA256()))
    return TlsMaterial(cert.public_bytes(serialization.Encoding.PEM),
        private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()),
        hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest())


def load_tls_context(material):
    """No plaintext file fallback. Unsupported kernels fail before listening."""
    if (type(material) is not TlsMaterial or type(material.certificate) is not bytes
            or type(material.private_key) is not bytes or type(material.pin) is not str
            or not 1 <= len(material.certificate) <= 16384
            or not 1 <= len(material.private_key) <= 16384):
        raise ValueError('invalid_tls_material')
    try:
        der = x509.load_pem_x509_certificate(material.certificate).public_bytes(serialization.Encoding.DER)
    except ValueError:
        raise ValueError('invalid_tls_material') from None
    if hashlib.sha256(der).hexdigest() != material.pin:
        raise ValueError('invalid_tls_material')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if sys.platform == 'win32':
        from tls_windows import load_windows_pem
        load_windows_pem(context, material.certificate, material.private_key)
        return context
    if sys.platform != 'linux':
        raise OSError('memory_tls_loader_unavailable')
    import fcntl
    fd = os.memfd_create('vrchat-agent-tls', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.fchmod(fd, 0o600)
        content = memoryview(material.certificate + b'\n' + material.private_key)
        while content:
            written = os.write(fd, content)
            if written <= 0:
                raise OSError('short_tls_memory_write')
            content = content[written:]
        # Linux UAPI: F_LINUX_SPECIFIC_BASE(1024)+9, seals 1|2|4|8.
        # Some standalone CPython builds omit these exported constants.
        fcntl.fcntl(fd, getattr(fcntl, 'F_ADD_SEALS', 1033), 0x000F)
        def no_encrypted_key():
            raise ValueError('encrypted_tls_key_not_supported')
        context.load_cert_chain('/proc/self/fd/' + str(fd), password=no_encrypted_key)
    finally:
        os.close(fd)
    return context
