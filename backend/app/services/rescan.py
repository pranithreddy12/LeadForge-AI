"""Fresh-signal re-scan (2026 'right-time' outreach): a lead qualified once, but its
facts drift — ratings drop, hours change, a booking widget appears, review counts jump.
This re-checks UNCONTACTED leads against live sources and:

  - refreshes Places facts (rating / review count / phone / hours) via Place Details
  - re-runs local signal detection (deduped by kind - only genuinely NEW ones persist)
  - RESOLVES no_online_booking when a booking widget has since appeared (the pain is
    gone; the draft angle would now be false)
  - re-scores any lead whose signals changed

NOTHING-STATIC: a failed refresh keeps the old data and changes nothing.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.logging import get_logger
from app.models.company import Company
from app.models.signal import Signal
from app.services.local_signals import _booking_status, detect_local_signals
from app.services.places import fetch_place_details

log = get_logger(__name__)

_REFRESH_FIELDS = ("rating", "review_count", "phone", "phone_intl", "hours",
                   "business_status")


def rescan_company(db: Session, company: Company, api_key: str | None) -> dict:
    """Re-check one lead. Returns {changes, new, resolved} — all empty when nothing
    moved (the common case)."""
    places = dict((company.raw or {}).get("places") or {})
    changes: dict = {}

    # 1. Fresh Places facts (only when we have a place_id + key; else skip silently).
    if places.get("place_id") and api_key:
        fresh = fetch_place_details(places["place_id"], api_key, db=db)
        if fresh:
            for k in _REFRESH_FIELDS:
                new_v = fresh.get(k)
                if new_v is not None and new_v != places.get(k):
                    changes[k] = {"from": places.get(k), "to": new_v}
                    places[k] = new_v
            if fresh.get("website") and not company.website:
                company.website = fresh["website"]
            if changes:
                company.raw = {**(company.raw or {}), "places": places}
                flag_modified(company, "raw")

    # 2. Booking status can flip: widget added since discovery -> the no_online_booking
    #    signal (and any draft angle built on it) is now FALSE. Resolve it.
    resolved: list[str] = []
    has_book, _ = _booking_status(company.website)
    if has_book is True:
        stale = db.execute(
            select(Signal).where(Signal.company_id == company.id,
                                 Signal.kind == "no_online_booking")
        ).scalars().all()
        for s in stale:
            db.delete(s)
            resolved.append("no_online_booking")
        dossier = dict((company.raw or {}).get("dossier") or {})
        if dossier and dossier.get("online_booking") is not True:
            dossier["online_booking"] = True
            company.raw = {**(company.raw or {}), "dossier": dossier}
            flag_modified(company, "raw")
    db.commit()

    # 3. New signals off the refreshed facts (kind-deduped -> only genuinely new rows).
    new = detect_local_signals(db, company)

    if changes or new or resolved:
        log.info("rescan_changed", company=company.name, changes=list(changes),
                 new=[s.kind for s in new], resolved=resolved)
    return {"changes": changes, "new": [s.kind for s in new], "resolved": resolved}
