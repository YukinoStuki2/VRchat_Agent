"""Finite per-run identity policy on the fixed native JWT verifier.

No token issuance, key storage, OAuth protocol or server-identity proof here.
The local owner must supply unique run-scoped issuer/audience and public key.
"""
import time
from fastmcp.server.auth.providers.jwt import JWTVerifier


class CandidateJWTVerifier(JWTVerifier):
    def __init__(self, *, public_key, issuer, audience, principals, required_scope):
        def identifier(value):
            return (type(value) is str and 0 < len(value) <= 256
                    and value == value.strip() and not any(ord(c) < 32 for c in value))
        if (not all(identifier(v) for v in (issuer, audience, required_scope))
                or type(principals) not in (tuple, list) or not 1 <= len(principals) <= 16
                or not all(identifier(v) and v != 'unknown' for v in principals)
                or len(set(principals)) != len(principals)):
            raise ValueError('explicit_finite_auth_policy_required')
        self._principals = frozenset(principals)
        super().__init__(public_key=public_key, algorithm='RS256', issuer=issuer,
                         audience=audience, required_scopes=[required_scope])

    async def verify_token(self, token):
        access = await super().verify_token(token)
        if access is None:
            return None
        # Only signed claims returned by upstream verification are inspected.
        claims = access.claims
        client = claims.get('client_id')
        expiry = claims.get('exp')
        if (type(client) is not str or client not in self._principals
                or type(expiry) is not int or expiry <= time.time()
                or claims.get('iss') != self.issuer or claims.get('aud') != self.audience):
            return None
        return access
