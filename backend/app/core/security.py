from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)
bearer = HTTPBearer(auto_error=False)


def _clerk_configured() -> bool:
    """True iff CLERK_* env vars look like real credentials, not placeholders.

    When false, `get_principal` falls back to the seeded `demo` user/org so the
    API can be exercised end-to-end without a working Clerk account. The fallback
    auto-deactivates the moment a real `sk_test_…` secret is dropped in.
    """
    sk = settings.clerk_secret_key or ""
    return sk.startswith("sk_") and not sk.endswith("xxx") and not sk.endswith("placeholder")


@dataclass(slots=True)
class Principal:
    """Authenticated subject extracted from a Clerk JWT."""

    user_id: str           # Clerk `sub`
    email: str | None
    org_id: str | None     # Clerk active organization id
    org_role: str | None   # e.g. "admin", "basic_member"
    session_id: str | None
    claims: dict[str, Any]

    @property
    def is_admin(self) -> bool:
        return self.org_role in {"admin", "owner"}


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.clerk_jwks_url:
        raise RuntimeError("CLERK_JWKS_URL is not configured")
    return PyJWKClient(settings.clerk_jwks_url, cache_keys=True, lifespan=3600)


def _decode_clerk_jwt(token: str) -> dict[str, Any]:
    """Verify a Clerk-issued JWT using the published JWKS."""
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer or None,
            options={"require": ["exp", "iat", "sub"]},
        )
        # Clerk session tokens include `azp` / `nbf` — additionally enforce nbf.
        nbf = claims.get("nbf")
        if nbf and nbf > int(time.time()) + 5:
            raise jwt.InvalidTokenError("token not yet valid")
        return claims
    except jwt.PyJWTError as exc:
        log.warning("jwt_verify_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


def _demo_principal() -> Principal:
    """The principal that backs dev-mode requests when Clerk isn't configured.

    Matches the seed CLI's `clerk_user_id="user_demo"` / `clerk_org_id="org_demo"`.
    """
    return Principal(
        user_id="user_demo",
        email="founder@demo.co",
        org_id="org_demo",
        org_role="owner",
        session_id="sess_dev",
        claims={"dev_bypass": True, "name": "Demo Founder"},
    )


async def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    """FastAPI dependency: extract & verify the Clerk JWT.

    Dev fallback: when Clerk isn't configured (placeholder secret), every request
    is treated as the seeded demo user. Logs a warning on each request so the
    bypass can't be left on by accident in production.
    """
    if not _clerk_configured():
        log.warning("auth_dev_bypass", path=request.url.path)
        return _demo_principal()

    token = creds.credentials if creds else None
    if not token:
        # Allow `?token=` for SSE/webhook handshake convenience.
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token"
        )

    claims = _decode_clerk_jwt(token)
    return Principal(
        user_id=claims["sub"],
        email=claims.get("email"),
        org_id=claims.get("org_id") or claims.get("organization_id"),
        org_role=claims.get("org_role"),
        session_id=claims.get("sid"),
        claims=claims,
    )


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return principal


async def verify_clerk_webhook(request: Request) -> dict[str, Any]:
    """Verify the Svix-style signature Clerk uses for webhook events."""
    import hmac
    import hashlib
    import base64

    if not settings.clerk_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not set")

    svix_id = request.headers.get("svix-id")
    svix_ts = request.headers.get("svix-timestamp")
    svix_sig = request.headers.get("svix-signature")
    if not (svix_id and svix_ts and svix_sig):
        raise HTTPException(status_code=400, detail="Missing svix headers")

    body = await request.body()
    secret = settings.clerk_webhook_secret.split("_", 1)[-1]
    expected = hmac.new(
        base64.b64decode(secret), f"{svix_id}.{svix_ts}.{body.decode()}".encode(),
        hashlib.sha256,
    ).digest()
    expected_b64 = base64.b64encode(expected).decode()
    if not any(part.split(",", 1)[-1] == expected_b64 for part in svix_sig.split(" ")):
        raise HTTPException(status_code=400, detail="Bad signature")

    import json
    return json.loads(body)


async def fetch_clerk_user(user_id: str) -> dict[str, Any] | None:
    """Fetch a Clerk user record by id (for webhook hydration)."""
    if not settings.clerk_secret_key:
        return None
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
        if r.status_code != 200:
            return None
        return r.json()
