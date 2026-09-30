"""Owner-created per-run child configuration, not Unity/client delivery proof.

Never deserialize RuntimeBinding from JSON. Only a local owner invokes
new_local_run and retains the certificate pin and role credentials. The child
receives public verification policy plus TLS private material via its restricted
environment; it receives no bearer tokens or JWT signing key. Environment
possession alone is not brand identity or proof of which process owns a port.
"""
from dataclasses import dataclass, field
import json
import os
import re
import threading
from typing import Any
import time

from run_identity import RunIdentity, issue_run_identity
from tls_context import TlsMaterial, issue_tls_material

ENVIRONMENT_KEY = 'VRCHAT_AGENT_BOOTSTRAP'


def target(project, port):
    if (type(project) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', project) is None
            or type(port) is not int or not 1024 <= port <= 65535):
        raise ValueError('invalid_bootstrap_target')


@dataclass(slots=True)
class LocalRun:
    project: str
    port: int
    identity: RunIdentity = field(repr=False)
    tls: TlsMaterial = field(repr=False)
    _used: bool = field(default=False, init=False, repr=False)
    _lock: Any = field(default_factory=threading.Lock, init=False, repr=False)

    def take_environment(self):
        with self._lock:
            if self._used:
                raise ValueError('bootstrap_already_consumed')
            self._used = True
        doc = {'version': 1, 'project': self.project, 'port': self.port,
               'issuer': self.identity.issuer, 'expires_at': self.identity.expires_at,
               'public_key': self.identity.public_key,
               'certificate': self.tls.certificate.decode('ascii'),
               'tls_private_key': self.tls.private_key.decode('ascii'), 'pin': self.tls.pin}
        return {ENVIRONMENT_KEY: json.dumps(doc, separators=(',', ':'))}


def new_local_run(project, port, *, lifetime=600):
    target(project, port)
    identity = issue_run_identity(lifetime=lifetime)
    tls = issue_tls_material(lifetime=lifetime)
    return LocalRun(project, port, identity, tls)


@dataclass(frozen=True, slots=True)
class ChildConfiguration:
    project: str
    port: int
    issuer: str
    expires_at: int
    public_key: str = field(repr=False)
    tls: TlsMaterial = field(repr=False)

    def verifiers(self):
        from candidate_auth import CandidateJWTVerifier
        run = self.issuer.removeprefix('urn:vrchat-agent:run:')
        common = {'public_key': self.public_key, 'issuer': self.issuer}
        return (CandidateJWTVerifier(**common, audience=self.issuer+':mcp',
                    principals=['hermes:'+run, 'codex:'+run, 'probe:'+run], required_scope='candidate:mcp'),
                CandidateJWTVerifier(**common, audience=self.issuer+':unity',
                    principals=['unity:'+run], required_scope='candidate:unity'))


def consume_environment(project, port, *, environment=None):
    target(project, port)
    environment = os.environ if environment is None else environment
    raw = environment.pop(ENVIRONMENT_KEY, None)
    if raw is None:
        raise ValueError('BINDING_REQUIRED')
    try:
        if type(raw) is not str or not 1 <= len(raw) <= 16384:
            raise ValueError()
        def unique(pairs):
            doc = {}
            for key, value in pairs:
                if key in doc:
                    raise ValueError()
                doc[key] = value
            return doc
        doc = json.loads(raw, object_pairs_hook=unique)
        if type(doc) is not dict or set(doc) != {'version','project','port','issuer',
                'expires_at','public_key','certificate','tls_private_key','pin'}:
            raise ValueError()
        if (type(doc['version']) is not int or doc['version'] != 1
                or doc['project'] != project or type(doc['port']) is not int or doc['port'] != port
                or type(doc['expires_at']) is not int or not time.time() < doc['expires_at'] <= time.time()+3600
                or type(doc['issuer']) is not str
                or re.fullmatch(r'urn:vrchat-agent:run:[0-9a-f]{48}',doc['issuer']) is None
                or any(type(doc[k]) is not str or not doc[k] for k in
                       ('public_key','certificate','tls_private_key','pin'))):
            raise ValueError()
        tls = TlsMaterial(doc['certificate'].encode('ascii'), doc['tls_private_key'].encode('ascii'),doc['pin'])
        return ChildConfiguration(project,port,doc['issuer'],doc['expires_at'],doc['public_key'],tls)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ValueError('BINDING_INVALID') from None
