"""Local-business buying signals from Google reviews + website (Step 6).

Local SMBs don't have funding rounds or hiring spikes — their buying intent shows up
in their REVIEWS and operations. These persist as real Signal rows (source=
"google_reviews"), so the existing fit x intent scorer uses them directly and outreach
can cite them verifiably ("12 of your recent reviews mention missed calls").

NOTHING-STATIC / REAL-VERIFIABLE: every signal is sourced from actual Places review
text or rating, or a real check of the company's website — never invented.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.company import Company
from app.models.signal import Signal

log = get_logger(__name__)

_MISSED_CALL = ("missed call", "no answer", "never answer", "couldn't reach",
                "could not reach", "couldnt reach", "voicemail", "didn't pick up",
                "didnt pick up", "unable to reach", "no one answered", "won't answer")
_SLOW = ("wait time", "long wait", "slow response", "slow to respond", "took forever",
         "waited", "waiting forever", "hours to respond", "days to respond")
_BOOKING_HINTS = ("book", "booking", "schedule", "appointment", "reserve", "calendly",
                  "booksy", "vagaro", "squareup", "acuity", "setmore", "schedulicity")


def _make(company: Company, kind: str, label: str, *, severity: float, detail: str) -> Signal:
    return Signal(
        organization_id=company.organization_id, company_id=company.id,
        kind=kind, label=label[:200], description=detail,
        severity=severity, confidence=0.8, source="google_reviews",
    )


def _has_booking_link(website: str | None) -> bool:
    """Best-effort: does the homepage reference an online-booking option?"""
    if not website:
        return True  # unknown -> don't fire the signal
    from app.services.scraper import fetch_raw_html
    html = (fetch_raw_html(website) or "").lower()
    if not html:
        return True  # couldn't fetch -> don't invent a signal
    return any(h in html for h in _BOOKING_HINTS)


def detect_local_signals(db: Session, company: Company) -> list[Signal]:
    """Inspect the company's persisted Places reviews + rating + website, persist any
    matched local signals (deduped by kind), return the new rows."""
    places = (company.raw or {}).get("places") or {}
    reviews = places.get("reviews") or []
    rating = places.get("rating")
    review_text = " ".join((r.get("text") or "") for r in reviews).lower()

    existing = {
        k for (k,) in db.execute(
            select(Signal.kind).where(Signal.company_id == company.id,
                                      Signal.source == "google_reviews")
        )
    }
    new: list[Signal] = []

    def hits(words):
        return sum(1 for w in words if w in review_text)

    n_missed = hits(_MISSED_CALL)
    if n_missed and "missed_calls_complaint" not in existing:
        new.append(_make(company, "missed_calls_complaint",
                         f"{n_missed} recent review phrase(s) mention missed/unanswered calls",
                         severity=0.85, detail=f"matched in Google reviews: {n_missed} phrase(s)"))
    n_slow = hits(_SLOW)
    if n_slow and "slow_response_complaint" not in existing:
        new.append(_make(company, "slow_response_complaint",
                         f"{n_slow} review phrase(s) mention slow response / wait times",
                         severity=0.6, detail=f"matched in Google reviews: {n_slow} phrase(s)"))
    if rating is not None and rating < 4.0 and "low_rating" not in existing:
        new.append(_make(company, "low_rating", f"Google rating {rating} (below 4.0)",
                         severity=0.4, detail=f"Google rating {rating}"))
    if "no_online_booking" not in existing and not _has_booking_link(company.website):
        new.append(_make(company, "no_online_booking",
                         "No online-booking link found on the website",
                         severity=0.55, detail="homepage scan found no booking/scheduling link"))

    for s in new:
        db.add(s)
    if new:
        db.commit()
    log.info("local_signals_detected", company=str(company.id), n=len(new),
             kinds=[s.kind for s in new])
    return new
