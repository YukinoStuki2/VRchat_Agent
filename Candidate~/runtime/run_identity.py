"""Local owner-only finite credentials; no disk, IPC, renewal, or brand proof.

The caller must deliver each bearer only to its assigned client over a separately
verified channel. Possessing these objects is NOT a trusted bootstrap. Python
cannot guarantee secret erasure from process memory; do not log/serialize them.
"""
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
import secrets
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt
from joserfc.jwk import RSAKey


@dataclass(frozen=True, slots=True)
class Credential:
    principal: str
    audience: str
    scope: str
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class RunIdentity:
    issuer: str
    public_key: str
    expires_at: int
    credentials: Mapping[str, Credential] = field(repr=False)


def issue_run_identity(*, lifetime=600):
    """Return distinct signed run roles; discard the signing-key reference."""
    if type(lifetime) is not int or not 30 <= lifetime <= 3600:
        raise ValueError('invalid_run_lifetime')
    run = secrets.token_hex(24)
    issuer = 'urn:vrchat-agent:run:' + run
    now = int(time.time())
    expiry = now + lifetime
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
    key = RSAKey.import_key(private)
    credentials = {}
    for role in ('hermes', 'codex', 'unity', 'probe'):
        principal = role + ':' + run
        scope = 'candidate:unity' if role == 'unity' else 'candidate:mcp'
        audience = issuer + (':unity' if role == 'unity' else ':mcp')
        claims = {'iss': issuer, 'sub': principal, 'client_id': principal,
                  'aud': audience, 'scope': scope, 'iat': now, 'nbf': now,
                  'exp': expiry, 'jti': secrets.token_hex(24)}
        token = jwt.encode({'alg': 'RS256', 'typ': 'JWT'}, claims, key,
                           algorithms=['RS256'])
        credentials[role] = Credential(principal, audience, scope, token)
    return RunIdentity(issuer, public, expiry, MappingProxyType(credentials))
