"""Synthetic in-memory issuer checks, not trusted IPC or client acceptance."""
import importlib
import importlib.util
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from candidate_auth import CandidateJWTVerifier


class RunIdentityTests(unittest.IsolatedAsyncioTestCase):
    def implementation(self):
        self.assertIsNotNone(importlib.util.find_spec('run_identity'),
                             'owner-only per-run credential issuer is missing')
        return importlib.import_module('run_identity')

    async def test_RI005_internal_probe_has_its_own_nonclient_credential(self):
        identity = self.implementation().issue_run_identity()
        self.assertIn('probe', identity.credentials, 'readiness must not impersonate Hermes')
        self.assertTrue(identity.credentials['probe'].principal.startswith('probe:'))
        self.assertNotEqual(identity.credentials['probe'].token, identity.credentials['hermes'].token)
        from owner_bootstrap import new_local_run, consume_environment
        owner = new_local_run('fixture-project', 18081)
        mcp_auth, unity_auth = consume_environment(owner.project, owner.port,
            environment=owner.take_environment()).verifiers()
        self.assertIsNotNone(await mcp_auth.verify_token(owner.identity.credentials['probe'].token))
        self.assertIsNone(await unity_auth.verify_token(owner.identity.credentials['probe'].token))

    async def test_RI003_new_run_and_expiry_do_not_reuse_authority(self):
        # Characterization of the already implemented randomness and verifier.
        first = self.implementation().issue_run_identity(lifetime=30)
        second = self.implementation().issue_run_identity(lifetime=30)
        self.assertNotEqual(first.issuer, second.issuer)
        self.assertNotEqual(first.public_key, second.public_key)
        for role in first.credentials:
            credential = first.credentials[role]
            verifier = CandidateJWTVerifier(public_key=first.public_key,
                issuer=first.issuer, audience=credential.audience,
                principals=[credential.principal], required_scope=credential.scope)
            self.assertIsNone(await verifier.verify_token(second.credentials[role].token))
            with patch('candidate_auth.time.time', return_value=first.expires_at + 1):
                self.assertIsNone(await verifier.verify_token(credential.token))
        from dataclasses import FrozenInstanceError
        with self.assertRaises(FrozenInstanceError):
            first.expires_at = first.expires_at + 10
        with self.assertRaises(TypeError):
            first.credentials['extra'] = first.credentials['hermes']
        self.assertFalse(any('private' in name or 'signing' in name for name in first.__slots__))

    def test_RI004_issuer_makes_no_files_or_connections(self):
        module = self.implementation()
        import os
        import socket
        import subprocess
        with patch('builtins.open', side_effect=AssertionError('file open')), \
             patch.object(os, 'open', side_effect=AssertionError('OS file open')), \
             patch.object(socket, 'socket', side_effect=AssertionError('network')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('process')):
            identity = module.issue_run_identity(lifetime=60)
        self.assertEqual(len(identity.credentials), 4)

    def test_RI002_lifetime_is_bounded_before_key_generation(self):
        module = self.implementation()
        with patch.object(module.rsa, 'generate_private_key', side_effect=AssertionError('key generation reached')) as generate:
            for lifetime in (None, True, 0, -1, 29, 3601, 3.5, '60'):
                with self.subTest(lifetime=lifetime), self.assertRaisesRegex(ValueError, 'invalid_run_lifetime'):
                    module.issue_run_identity(lifetime=lifetime)
            generate.assert_not_called()

    async def test_RI001_finite_disjoint_principals_verified_by_real_auth(self):
        identity = self.implementation().issue_run_identity(lifetime=120)
        self.assertEqual(set(identity.credentials), {'hermes', 'codex', 'unity', 'probe'})
        self.assertEqual(len({v.principal for v in identity.credentials.values()}), 4)
        self.assertGreater(identity.expires_at, time.time())
        self.assertLessEqual(identity.expires_at, time.time() + 120)
        for role, credential in identity.credentials.items():
            verifier = CandidateJWTVerifier(public_key=identity.public_key,
                issuer=identity.issuer, audience=credential.audience,
                principals=[credential.principal], required_scope=credential.scope)
            accepted = await verifier.verify_token(credential.token)
            self.assertIsNotNone(accepted)
            self.assertEqual(accepted.client_id, credential.principal)
            self.assertEqual(accepted.claims['sub'], credential.principal)
            self.assertEqual(accepted.claims['exp'], identity.expires_at)
            self.assertNotIn(credential.token, repr(identity))
            self.assertNotIn(credential.token, repr(credential))
            for other in identity.credentials.values():
                if other is not credential:
                    self.assertIsNone(await verifier.verify_token(other.token))
        self.assertEqual(identity.credentials['hermes'].audience, identity.credentials['codex'].audience)
        self.assertNotEqual(identity.credentials['unity'].audience, identity.credentials['codex'].audience)


if __name__ == '__main__':
    unittest.main(verbosity=2)
