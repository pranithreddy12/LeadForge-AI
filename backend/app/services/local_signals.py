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
# Real online-booking WIDGETS/platforms — presence = they already have online booking.
# Wellness/spa + medical/dental + MENA platforms. Any hit => they HAVE booking.
_BOOKING_PLATFORMS = (
    # spa / salon / wellness
    "fresha.com", "booksy.com", "vagaro.com", "zenoti.com", "mindbodyonline.com",
    "setmore.com", "squareup.com/appointments", "schedulicity.com", "simplybook",
    "timely.com", "phorest", "noona", "getflit", "book.app", "widget.fresha",
    # generic schedulers
    "calendly.com", "acuityscheduling.com", "app.acuityscheduling", "cal.com",
    "youcanbook.me", "hubspot.com/meetings", "savvycal.com",
    # medical / dental (US + intl) — these were MISSING and caused false positives
    "zocdoc.com", "localmed.com", "nexhealth.com", "dentrix", "opendental",
    "weave.com", "solutionreach.com", "curve dental", "denticon", "carestack",
    "doctolib", "okadoc", "vezeeta", "practo.com", "healthengine", "cliniko",
    "jane.app", "mytime.com", "sesamecommunications", "revenuewell",
)
# Plain booking CALLS-TO-ACTION. A site with a "Book Now" / "Book an Appointment"
# button HAS a booking path — the old detector required the literal word "online",
# so these slipped through and produced FALSE "no online booking" core-fit claims.
# NOTE: fetch_static returns STRIPPED TEXT, not raw HTML, so markup tokens
# (class="booking", href=/booking ...) can never match there — they live in
# _BOOKING_MARKUP and are only used against raw HTML.
_BOOKING_CTA = (
    "book online", "online booking", "schedule online", "book now online",
    "book an appointment online", "book now", "book an appointment",
    "book appointment", "book a consultation", "book consultation",
    "schedule an appointment", "schedule appointment", "request an appointment",
    "request appointment", "make an appointment", "book your appointment",
    "book your visit", "reserve your spot", "booking form", "appointment request",
)
# BOOKING-FLOW markers: a date/time picker, a booking cart, or a practitioner
# selector is unambiguous proof of a LIVE online booking system, whatever it's
# called. "Book Now" wording is optional; a booking flow is not. These are what
# mylondonskinclinic.ae actually renders — its site never says "book now".
_BOOKING_FLOW = (
    "add to booking", "booking summary", "your booking", "select a date",
    "select a time", "select date", "select time", "date & time", "date and time",
    "select your doctor", "select your location", "select a location",
    "choose a date", "choose a time", "available slots", "time slots",
    "no time slots", "appointment date", "preferred date", "preferred time",
    "book your consultation", "schedule your visit",
)
# Only meaningful against RAW html (not the stripped text fetch_static returns).
_BOOKING_MARKUP = (
    'class="booking', "class='booking", 'id="booking', "id='booking",
    "data-booking", 'href="/book', 'href="/booking', 'href="/appointment',
    "bookingsummary", "bookinglocationselect", "booking-summary",
)
# Pages a booking button commonly lives on when the homepage doesn't show one.
_BOOKING_PATHS = ("/book", "/booking", "/book-now", "/appointments", "/appointment",
                  "/book-appointment", "/schedule", "/contact")
# Manual-only booking phrases -> a CONCRETE 'no online booking' signal + how they book.
_MANUAL_BOOK = {
    "dm to book": "takes bookings via Instagram DM only",
    "dm us to book": "takes bookings via Instagram DM only",
    "message to book": "takes bookings by DM/message only",
    "message us to book": "takes bookings by DM/message only",
    "whatsapp to book": "takes bookings via WhatsApp only",
    "book via whatsapp": "takes bookings via WhatsApp only",
    "book on whatsapp": "takes bookings via WhatsApp only",
    "call to book": "takes bookings by phone only",
    "call us to book": "takes bookings by phone only",
    "call now to book": "takes bookings by phone only",
    "book by phone": "takes bookings by phone only",
    "to book, call": "takes bookings by phone only",
    "to book call": "takes bookings by phone only",
    "book your appointment by calling": "takes bookings by phone only",
}


def _make(company: Company, kind: str, label: str, *, severity: float, detail: str,
          source: str = "google_reviews", url: str | None = None) -> Signal:
    """A signal must be able to prove itself: `url` is the page/listing the claim was
    read from, `observed_at` is when we read it (audit A1/A8 — a signal with neither
    can't be checked or aged out)."""
    from datetime import datetime, timezone
    return Signal(
        organization_id=company.organization_id, company_id=company.id,
        kind=kind, label=label[:200], description=detail,
        severity=severity, confidence=0.8, source=source,
        url=url, observed_at=datetime.now(timezone.utc),
    )


def _booking_status(website: str | None) -> tuple[bool | None, str | None]:
    """Back-compat wrapper: (has_online_booking, manual_detail)."""
    has, detail, _url = booking_status_evidence(website)
    return (has, detail)


def booking_status_evidence(website: str | None) -> tuple[bool | None, str | None, str | None]:
    """Decide whether a business already takes bookings online. Returns
    (has_online_booking, manual_detail, evidence_url).

      (True,  None,   url)  -> a booking platform OR a booking CTA was found at `url`
      (False, detail, url)  -> we READ real pages and found no booking path
      (None,  None,   None) -> we could not read the site -> assert NOTHING

    This is the CORE-FIT signal, so it is deliberately biased toward "they HAVE
    booking": a false 'no online booking' tells a clinic with a Book Now button that
    it doesn't have one, which destroys credibility instantly. We therefore
      (a) match plain CTAs ("book now", "book an appointment"), not just the literal
          word "online" (the old bug),
      (b) look on the common /book, /appointments... pages, not just the homepage,
      (c) fall back to a JS render, since most booking widgets are script-injected,
      (d) return None (no signal) whenever the fetch fails, instead of guessing.
    """
    if not website:
        return (None, None, None)
    from urllib.parse import urljoin

    from app.services.scraper import fetch_raw_html, fetch_static

    def _hit(text: str) -> bool:
        """Any booking platform, CTA, or booking-FLOW marker => they have booking."""
        return (any(p in text for p in _BOOKING_PLATFORMS)
                or any(c in text for c in _BOOKING_CTA)
                or any(f in text for f in _BOOKING_FLOW))

    def _hit_raw(html: str) -> bool:
        return _hit(html) or any(m in html for m in _BOOKING_MARKUP)

    home = (fetch_static(website, timeout=8.0, allow_playwright=False) or "").lower()
    if home and _hit(home):
        return (True, None, website)

    # fetch_static strips markup, so a widget identified only by its id/class/href
    # is invisible to it. Check the RAW html before concluding anything.
    raw = (fetch_raw_html(website) or "").lower()
    if raw and _hit_raw(raw):
        return (True, None, website)

    if not home and not raw:
        # Couldn't read the site at all -> assert NOTHING (never guess "no booking").
        rendered = (fetch_static(website, timeout=15.0, allow_playwright=True) or "").lower()
        if rendered and _hit(rendered):
            return (True, None, website)
        if not rendered:
            return (None, None, None)
        home = rendered

    # Booking buttons often live on a dedicated page, not the homepage.
    for path in _BOOKING_PATHS:
        url = urljoin(website, path)
        page = (fetch_static(url, timeout=6.0, allow_playwright=False) or "").lower()
        if page and _hit(page):
            return (True, None, url)

    # LAST RESORT before making the damaging claim: most booking widgets are injected
    # by JavaScript, so a static miss proves nothing. Render the page once. We only pay
    # this cost on the negative path — i.e. exactly when we're about to tell a clinic
    # it has no online booking, which is the one claim we must never get wrong.
    rendered = (fetch_static(website, timeout=20.0, allow_playwright=True) or "").lower()
    if rendered and _hit(rendered):
        return (True, None, website)

    haystack = home or rendered or raw
    if not haystack:
        return (None, None, None)
    for phrase, detail in _MANUAL_BOOK.items():
        if phrase in haystack:
            return (False, detail, website)
    return (False, None, website)


def detect_local_signals(db: Session, company: Company) -> list[Signal]:
    """Inspect the company's persisted Places reviews + rating + website, persist any
    matched local signals (deduped by kind), return the new rows."""
    places = (company.raw or {}).get("places") or {}
    reviews = places.get("reviews") or []
    rating = places.get("rating")
    review_text = " ".join((r.get("text") or "") for r in reviews).lower()

    # Dedup across ALL sources — limited_hours / no_online_booking persist with
    # source="website_scan", and a re-scan must not duplicate them.
    existing = {
        k for (k,) in db.execute(
            select(Signal.kind).where(Signal.company_id == company.id)
        )
    }
    new: list[Signal] = []
    # Evidence URL for review/rating/hours claims = the company's own Google listing.
    pid = places.get("place_id")
    gmaps = f"https://www.google.com/maps/place/?q=place_id:{pid}" if pid else None

    def hits(words):
        return sum(1 for w in words if w in review_text)

    n_missed = hits(_MISSED_CALL)
    if n_missed and "missed_calls_complaint" not in existing:
        new.append(_make(company, "missed_calls_complaint",
                         f"{n_missed} recent review phrase(s) mention missed/unanswered calls",
                         severity=0.85, detail=f"matched in Google reviews: {n_missed} phrase(s)",
                         url=gmaps))
    n_slow = hits(_SLOW)
    if n_slow and "slow_response_complaint" not in existing:
        new.append(_make(company, "slow_response_complaint",
                         f"{n_slow} review phrase(s) mention slow response / wait times",
                         severity=0.6, detail=f"matched in Google reviews: {n_slow} phrase(s)",
                         url=gmaps))
    if rating is not None and rating < 4.0 and "low_rating" not in existing:
        new.append(_make(company, "low_rating", f"Google rating {rating} (below 4.0)",
                         severity=0.4, detail=f"Google rating {rating}", url=gmaps))
    # Limited opening hours (from Places weekdayDescriptions): closed days / closes
    # early -> after-hours enquiries have nowhere to go. Pairs with the offer.
    if "limited_hours" not in existing:
        from app.services.dossier import _hours_gaps
        gaps = _hours_gaps(places.get("hours"))
        if gaps:
            new.append(_make(company, "limited_hours", "; ".join(gaps)[:200],
                             severity=0.5, detail="; ".join(gaps),
                             source="places_hours", url=gmaps))

    if "no_online_booking" not in existing:
        has_book, manual, ev_url = booking_status_evidence(company.website)
        if has_book is False:
            # A CONCRETE, scraped pain signal (no Google Enterprise SKU needed). When the
            # site states how they book (DM/call), lead with that; else a softer version.
            if manual:
                label = f"No online booking, {manual}"
                detail = f"website scan: no booking widget; site says it {manual}"
                sev = 0.7
            else:
                label = "No online booking widget on the website"
                detail = "website scan found no online-booking platform (bookings by call/DM)"
                sev = 0.5
            new.append(_make(company, "no_online_booking", label, severity=sev,
                             detail=detail, source="website_scan", url=ev_url))

    for s in new:
        db.add(s)
    if new:
        db.commit()
    log.info("local_signals_detected", company=str(company.id), n=len(new),
             kinds=[s.kind for s in new])
    return new
