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

import time

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Places Details is per-minute QPS limited. A discovery run fans out one detail call
# per search result, so a burst (a run + the re-scan loop + beats) trips 429s and,
# with no retry, every candidate is silently dropped -> a 0-lead run. Back off and
# retry on 429 (honoring Retry-After) so a transient burst degrades instead of failing.
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.6  # seconds: 0.6, 1.2, 2.4


def _get_with_retry(url: str, *, headers: dict, timeout: float) -> httpx.Response | None:
    """GET with exponential backoff on HTTP 429. Returns the final Response (which may
    still be non-200), or None if every attempt raised a transport error."""
    resp: httpx.Response | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = httpx.get(url, headers=headers, timeout=timeout)
        except Exception as e:
            log.info("place_get_error", url=url[-40:], error=str(e)[:120])
            resp = None
        if resp is not None and resp.status_code == 429 and attempt < _MAX_RETRIES:
            # A per-DAY quota ("GetPlaceRequest per day" / RESOURCE_EXHAUSTED) will not
            # recover by retrying — bail immediately so we don't burn 3 slow retries and
            # so the caller logs a clear daily-quota status. Only per-minute limits retry.
            body = (resp.text or "")[:400].lower()
            if "per day" in body or "resource_exhausted" in body:
                log.warning("places_daily_quota_exhausted")
                return resp
            ra = resp.headers.get("Retry-After")
            try:
                wait = float(ra) if ra else _BACKOFF_BASE * (2 ** attempt)
            except ValueError:
                wait = _BACKOFF_BASE * (2 ** attempt)
            log.info("places_rate_limited_backoff", attempt=attempt + 1, wait=wait)
            time.sleep(min(wait, 8.0))
            continue
        return resp
    return resp

_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = ("places.displayName,places.websiteUri,places.nationalPhoneNumber,"
               "places.internationalPhoneNumber,places.regularOpeningHours,"
               "places.formattedAddress,places.id,places.primaryType,"
               "places.businessStatus,places.rating,places.userRatingCount,"
               "places.reviews")


_DETAILS_ENDPOINT = "https://places.googleapis.com/v1/places/"


def is_configured(api_key: str | None = None) -> bool:
    return bool(api_key or settings.google_maps_api_key)


# ---- Place Details cache (cuts the GetPlaceRequest-per-day quota) ----------
# Reviews/rating/hours drift slowly, so a fresh cached payload is reused instead of
# re-paying quota. TTLs: reviews change rarely; the rescan wants fresher details.
_REVIEWS_TTL_DAYS = 30
_DETAILS_TTL_DAYS = 7


def _cache_get(db, place_id: str, kind: str, ttl_days: int):
    """Return the cached payload if a row exists and is younger than ttl_days, else
    None. Any DB hiccup -> None (fall through to a live fetch; never crash discovery)."""
    if db is None or not place_id:
        return None
    from datetime import datetime, timedelta, timezone

    from app.models.place_cache import PlaceCache
    try:
        from sqlalchemy import select
        row = db.execute(
            select(PlaceCache).where(PlaceCache.place_id == place_id,
                                     PlaceCache.kind == kind)
        ).scalar_one_or_none()
        if row is None:
            return None
        age_ok = row.updated_at >= datetime.now(timezone.utc) - timedelta(days=ttl_days)
        return row.payload if age_ok else None
    except Exception as e:
        log.info("place_cache_get_error", place_id=place_id, error=str(e)[:120])
        return None


def _cache_put(db, place_id: str, kind: str, payload) -> None:
    """Upsert the payload for (place_id, kind). Best-effort; a failure never blocks."""
    if db is None or not place_id or payload is None:
        return
    from app.models.place_cache import PlaceCache
    try:
        from sqlalchemy import select
        row = db.execute(
            select(PlaceCache).where(PlaceCache.place_id == place_id,
                                     PlaceCache.kind == kind)
        ).scalar_one_or_none()
        if row is None:
            db.add(PlaceCache(place_id=place_id, kind=kind, payload=payload))
        else:
            row.payload = payload  # onupdate bumps updated_at -> resets freshness
        db.commit()
    except Exception as e:
        log.info("place_cache_put_error", place_id=place_id, error=str(e)[:120])
        try:
            db.rollback()
        except Exception:
            pass


def _normalize_reviews(raw_reviews: list) -> list[dict]:
    return [
        {"text": ((rv.get("text") or {}).get("text") or ""),
         "rating": rv.get("rating"),
         "when": rv.get("relativePublishTimeDescription")}
        for rv in (raw_reviews or [])
    ]


def fetch_place_reviews(place_id: str, key: str, db=None) -> list[dict]:
    """Place Details call to pull actual review TEXT (searchText only returns rating/
    count, not review bodies). Returns up to Google's ~5 reviews. Best-effort: [] on
    error. This is the source of the missed-call / slow-response local signals.

    When `db` is given, a fresh cached payload is reused instead of spending quota."""
    if not place_id or not key:
        return []
    cached = _cache_get(db, place_id, "reviews", _REVIEWS_TTL_DAYS)
    if cached is not None:
        log.info("place_reviews_cache_hit", place_id=place_id)
        return _normalize_reviews(cached.get("reviews"))
    try:
        r = _get_with_retry(
            f"{_DETAILS_ENDPOINT}{place_id}",
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "reviews"},
            timeout=15.0,
        )
        if r is None or r.status_code != 200:
            log.info("place_details_failed", place_id=place_id,
                     status=(r.status_code if r is not None else "no_response"))
            return []
        body = r.json()
        _cache_put(db, place_id, "reviews", {"reviews": body.get("reviews") or []})
        return _normalize_reviews(body.get("reviews"))
    except Exception as e:
        log.info("place_details_error", place_id=place_id, error=str(e)[:140])
        return []


def fetch_place_details(place_id: str, key: str, db=None) -> dict | None:
    """Fresh Place Details for the RE-SCAN loop: rating / review count / phone / hours
    can all change after discovery. Returns the same shape as a search result subset,
    or None on any error (NOTHING-STATIC: caller keeps the old data, invents nothing).

    When `db` is given, a fresh cached payload is reused instead of spending quota."""
    if not place_id or not key:
        return None
    cached = _cache_get(db, place_id, "details", _DETAILS_TTL_DAYS)
    if cached is not None:
        log.info("place_details_cache_hit", place_id=place_id)
        return cached
    try:
        r = _get_with_retry(
            f"{_DETAILS_ENDPOINT}{place_id}",
            headers={"X-Goog-Api-Key": key,
                     "X-Goog-FieldMask": ("rating,userRatingCount,nationalPhoneNumber,"
                                          "internationalPhoneNumber,regularOpeningHours,"
                                          "businessStatus,websiteUri")},
            timeout=15.0,
        )
        if r is None or r.status_code != 200:
            log.info("place_refresh_failed", place_id=place_id,
                     status=(r.status_code if r is not None else "no_response"))
            return None
        p = r.json()
        out = {
            "rating": p.get("rating"),
            "review_count": p.get("userRatingCount"),
            "phone": p.get("nationalPhoneNumber"),
            "phone_intl": p.get("internationalPhoneNumber"),
            "business_status": p.get("businessStatus"),
            "website": p.get("websiteUri"),
            "hours": (p.get("regularOpeningHours") or {}).get("weekdayDescriptions"),
        }
        _cache_put(db, place_id, "details", out)
        return out
    except Exception as e:
        log.info("place_refresh_error", place_id=place_id, error=str(e)[:140])
        return None


def search_local_businesses(text_query: str, *, max_results: int = 20,
                            api_key: str | None = None,
                            fetch_reviews: bool = True, db=None) -> dict:
    """One Text Search. `api_key` (resolved from Settings) overrides the global .env
    key. Returns {"results": [{name, website, phone, address, place_id, type, rating,
    review_count, reviews, business_status}, ...]} or {"_provider_error": True}.

    Pass `db` to reuse cached review payloads and cut the per-day GetPlace quota."""
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
            reviews = _normalize_reviews(p.get("reviews"))
            # searchText usually omits review bodies -> pull them via Place Details so
            # the review-based signals (missed calls, slow response) can actually fire.
            if fetch_reviews and not reviews and p.get("userRatingCount"):
                reviews = fetch_place_reviews(p.get("id"), key, db=db)
            out.append({
                "name": (p.get("displayName") or {}).get("text"),
                "website": p.get("websiteUri"),
                "phone": p.get("nationalPhoneNumber"),
                "phone_intl": p.get("internationalPhoneNumber"),
                "address": p.get("formattedAddress"),
                "place_id": p.get("id"),
                "type": p.get("primaryType"),
                "rating": p.get("rating"),
                "review_count": p.get("userRatingCount"),
                "business_status": p.get("businessStatus"),
                "hours": (p.get("regularOpeningHours") or {}).get("weekdayDescriptions"),
                "reviews": reviews,
            })
        return {"results": out}
    except Exception as e:
        log.warning("places_search_failed", error=str(e))
        return {"_provider_error": True, "results": []}
