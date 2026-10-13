"""Access tokens issued by the server and signed with its Ed25519 key."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KINDS = {"client", "agent", "run"}


class TokenInvalid(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    kind: str
    uid: str | None
    exp: int
    jti: str
    run_id: str | None
    job_id: str | None


class TokenService:
    def __init__(self, signing_key: Ed25519PrivateKey, issuer: str, default_ttl: int) -> None:
        self._key = signing_key
        self._public = signing_key.public_key()
        self._issuer = issuer.rstrip("/")
        self._ttl = default_ttl

    def issue(
        self,
        sub: str,
        kind: str,
        uid: str | None = None,
        run_id: str | None = None,
        job_id: str | None = None,
        ttl: int | None = None,
    ) -> tuple[str, int]:
        if kind not in KINDS:
            raise ValueError(f"unknown token kind {kind!r}")
        lifetime = self._ttl if ttl is None else ttl
        now = int(time.time())
        claims = {
            "iss": self._issuer,
            "sub": sub,
            "kind": kind,
            "iat": now,
            "exp": now + lifetime,
            "jti": uuid.uuid4().hex,
        }
        if uid:
            claims["uid"] = uid
        if run_id:
            claims["run_id"] = run_id
        if job_id:
            claims["job_id"] = job_id
        return jwt.encode(claims, self._key, algorithm="EdDSA"), lifetime

    def verify(self, token: str) -> TokenClaims:
        try:
            claims = jwt.decode(
                token,
                self._public,
                algorithms=["EdDSA"],
                issuer=self._issuer,
                options={"require": ["exp", "iss", "sub", "kind", "jti"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenInvalid("invalid token") from exc
        if claims["kind"] not in KINDS:
            raise TokenInvalid("invalid token kind")
        return TokenClaims(
            sub=claims["sub"],
            kind=claims["kind"],
            uid=claims.get("uid"),
            exp=claims["exp"],
            jti=claims["jti"],
            run_id=claims.get("run_id"),
            job_id=claims.get("job_id"),
        )
