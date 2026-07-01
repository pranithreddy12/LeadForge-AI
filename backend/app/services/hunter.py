"""Hunter.io Domain Search — find the best emails for a company domain.

GET https://api.hunter.io/v2/domain-search?domain=&company=&api_key=&limit=5

NOTHING-STATIC: a missing key, a 429, or any API error returns [] (logged) and never
crashes the caller. Results are normalized to
{email, first_name, last_name, position, confidence} and sorted by confidence desc.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_ENDPOINT = "https://api.hunter.io/v2/domain-search"


def find_email(domain: str, company_name: str | None = None, *,
               api_key: str | None = None, limit: int = 5) -> list[dict]:
    """Return up to `limit` emails for `domain`, highest confidence first.

    `api_key` lets callers pass an org-resolved key (Settings first, else .env);
    if omitted it falls back to the global .env key.
    """
    key = (api_key or settings.hunter_api_key or "").strip()
    # Treat empty / placeholder ("xxx") / obviously-too-short keys as unconfigured so
    # the demo .env value never fires a doomed 401 call — scraping fallback handles it.
    if not key or key.endswith("xxx") or len(key) < 20:
        log.info("hunter_not_configured")
        return []
    if not domain:
        return []
    params = {"domain": domain, "api_key": key, "limit": limit}
    if company_name:
        params["company"] = company_name
    try:
        r = httpx.get(_ENDPOINT, params=params, timeout=15.0)
    except Exception as e:
        log.warning("hunter_request_failed", domain=domain, error=str(e)[:200])
        return []
    if r.status_code == 429:
        log.warning("hunter_rate_limited", domain=domain)
        return []
    if r.status_code >= 400:
        log.warning("hunter_api_error", domain=domain, status=r.status_code,
                    body=r.text[:300])
        return []
    try:
        emails = ((r.json().get("data") or {}).get("emails")) or []
    except Exception as e:
        log.warning("hunter_bad_json", domain=domain, error=str(e)[:200])
        return []
    out = [
        {
            "email": e.get("value"),
            "first_name": e.get("first_name"),
            "last_name": e.get("last_name"),
            "position": e.get("position"),
            "confidence": int(e.get("confidence") or 0),
        }
        for e in emails if e.get("value")
    ]
    out.sort(key=lambda x: x["confidence"], reverse=True)
    log.info("hunter_domain_search", domain=domain, found=len(out),
             top_confidence=(out[0]["confidence"] if out else None))
    return out
