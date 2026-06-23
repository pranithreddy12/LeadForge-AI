from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.ai import demo_data
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class EmailValidationResult:
    email: str
    status: str           # valid | risky | invalid | unknown
    confidence: int       # 0..100
    provider: str         # hunter | neverbounce | none


def _via_hunter(email: str) -> EmailValidationResult | None:
    if not settings.hunter_api_key:
        return None
    try:
        r = httpx.get(
            "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": settings.hunter_api_key},
            timeout=10.0,
        )
        r.raise_for_status()
        d = r.json().get("data") or {}
        result = (d.get("result") or "unknown").lower()
        # Hunter results: deliverable, undeliverable, risky, unknown
        status = {
            "deliverable": "valid",
            "undeliverable": "invalid",
            "risky": "risky",
            "unknown": "unknown",
        }.get(result, "unknown")
        return EmailValidationResult(
            email=email,
            status=status,
            confidence=int(d.get("score") or 0),
            provider="hunter",
        )
    except Exception as e:
        log.info("hunter_verify_failed", error=str(e))
        return None


def _via_neverbounce(email: str) -> EmailValidationResult | None:
    if not settings.neverbounce_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.neverbounce.com/v4/single/check",
            data={
                "key": settings.neverbounce_api_key,
                "email": email,
                "address_info": 1,
                "credits_info": 0,
                "timeout": 10,
            },
            timeout=12.0,
        )
        r.raise_for_status()
        d = r.json()
        result = (d.get("result") or "unknown").lower()
        status = {
            "valid": "valid",
            "invalid": "invalid",
            "disposable": "risky",
            "catchall": "risky",
            "unknown": "unknown",
        }.get(result, "unknown")
        return EmailValidationResult(
            email=email,
            status=status,
            confidence={"valid": 95, "invalid": 0, "risky": 50, "unknown": 30}[status],
            provider="neverbounce",
        )
    except Exception as e:
        log.info("neverbounce_verify_failed", error=str(e))
        return None


def _has_real_key() -> bool:
    h = (settings.hunter_api_key or "").strip()
    n = (settings.neverbounce_api_key or "").strip()
    return (bool(h) and not h.endswith("xxx")) or (bool(n) and not n.endswith("xxx"))


def validate_email(email: str) -> EmailValidationResult:
    """Validate an email, preferring Hunter then NeverBounce. Demo fallback when neither is set."""
    if not _has_real_key():
        d = demo_data.demo_email_validation(email)
        return EmailValidationResult(email=email, status=d["status"],
                                     confidence=d["confidence"], provider=d["provider"])
    return (
        _via_hunter(email)
        or _via_neverbounce(email)
        or EmailValidationResult(email=email, status="unknown", confidence=0, provider="none")
    )


def find_emails_for_domain(domain: str) -> list[dict]:
    """Hunter Domain Search — returns list of email patterns / found emails for a company."""
    if not settings.hunter_api_key or not domain:
        return []
    try:
        r = httpx.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": settings.hunter_api_key, "limit": 25},
            timeout=15.0,
        )
        r.raise_for_status()
        return (r.json().get("data") or {}).get("emails", []) or []
    except Exception as e:
        log.info("hunter_domain_search_failed", error=str(e))
        return []
