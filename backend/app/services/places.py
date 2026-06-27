"""Google Places (New) — compliant local-business discovery.

For the local-SMB ICP (dentists, salons, home services, clinics...) whose business is
a great fit for AI voice agents / speed-to-lead. The v1 Text Search returns name +
website + phone + address + rating + reviews in ONE call (vs the legacy endpoint's N+1
Place Details calls). ToS-allowed, unlike scraping a bot-protected directory.

NOTHING-STATIC: with no API key we return {"_provider_error": True} and NO results.

Cost note: requesting `places.reviews` is a higher-tier SKU. Callers cap results and
fan-out so a med-spa x city sweep doesn't run up quota.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = ("places.displayName,places.websiteUri,places.nationalPhoneNumber,"
               "places.formattedAddress,places.id,places.primaryType,"
               "places.businessStatus,places.rating,places.userRatingCount,"
               "places.reviews")


def is_configured(api_key: str | None = None) -> bool:
    return bool(api_key or settings.google_maps_api_key)


def search_local_businesses(text_query: str, *, max_results: int = 20,
                            api_key: str | None = None) -> dict:
    """One Text Search. `api_key` (resolved from Settings) overrides the global .env
    key. Returns {"results": [{name, website, phone, address, place_id, type, rating,
    review_count, reviews, business_status}, ...]} or {"_provider_error": True}."""
    key = api_key or settings.google_maps_api_key
    if not key:
        log.info("places_not_configured")
        return {"_provider_error": True, "results": []}
    try:
        r = httpx.post(
            _ENDPOINT,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": _FIELD_MASK,
            },
            json={"textQuery": text_query, "maxResultCount": min(max_results, 20)},
            timeout=20.0,
        )
        r.raise_for_status()
        out = []
        for p in r.json().get("places", []):
            reviews = [
                {"text": ((rv.get("text") or {}).get("text") or ""),
                 "rating": rv.get("rating"),
                 "when": rv.get("relativePublishTimeDescription")}
                for rv in (p.get("reviews") or [])
            ]
            out.append({
                "name": (p.get("displayName") or {}).get("text"),
                "website": p.get("websiteUri"),
                "phone": p.get("nationalPhoneNumber"),
                "address": p.get("formattedAddress"),
                "place_id": p.get("id"),
                "type": p.get("primaryType"),
                "rating": p.get("rating"),
                "review_count": p.get("userRatingCount"),
                "business_status": p.get("businessStatus"),
                "reviews": reviews,
            })
        return {"results": out}
    except Exception as e:
        log.warning("places_search_failed", error=str(e))
        return {"_provider_error": True, "results": []}
