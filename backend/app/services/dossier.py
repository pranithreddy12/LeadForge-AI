"""Per-lead dossier — 'note everything' about a local business BEFORE scoring/drafting.

Collected from sources we can honestly read (no paid SKUs, no login-walled scraping):
  - their WEBSITE: service/treatment menu (headings), about snippet, booking method
  - PLACES facts already persisted: rating, review count, type, address, opening hours
  - SOCIALS: platforms + best-effort Instagram bio/followers from public profile meta
    (Instagram often exposes 'X Followers, Y Posts' in og:description without login;
    when it doesn't, we skip — never invent)

Stored on company.raw['dossier'] and fed into scoring (limited-hours pain) and
drafting (real service names, follower counts) so every message cites real facts.
"""
from __future__ import annotations

import html as _html
import re

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.logging import get_logger
from app.models.company import Company
from app.services.scraper import fetch_raw_html

log = get_logger(__name__)

_SERVICE_PATHS = ("", "/services", "/treatments", "/menu", "/our-services", "/pricing")
_HEADING_RE = re.compile(r"<h[123][^>]*>(.*?)</h[123]>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_META_DESC_RE = re.compile(
    r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]+)"', re.I)
_IG_FOLLOWERS_RE = re.compile(r"([\d,.]+[KkMm]?)\s+Followers", re.I)

# headings that are navigation/boilerplate, not services
_HEADING_JUNK = {"home", "about", "about us", "contact", "contact us", "gallery", "blog",
                 "faq", "faqs", "testimonials", "reviews", "our team", "team", "menu",
                 "services", "our services", "why choose us", "book now", "location",
                 "opening hours", "follow us", "newsletter", "subscribe"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG_RE.sub(" ", text))).strip()


def _website_menu(domain: str) -> tuple[list[str], str | None]:
    """(service/treatment headings from the site, about/meta snippet)."""
    if not domain:
        return [], None
    services: list[str] = []
    snippet: str | None = None
    for path in _SERVICE_PATHS[:4]:
        htmldoc = fetch_raw_html(f"https://{domain}{path}")
        if not htmldoc:
            continue
        if snippet is None:
            m = _META_DESC_RE.search(htmldoc)
            if m:
                snippet = _clean(m.group(1))[:240] or None
        for h in _HEADING_RE.findall(htmldoc):
            t = _clean(h)
            if 3 <= len(t) <= 60 and t.lower() not in _HEADING_JUNK and t not in services:
                services.append(t)
        if len(services) >= 12:
            break
    return services[:12], snippet


def _instagram_public_meta(ig_url: str) -> dict:
    """Best-effort public facts from an Instagram profile's meta tags (no login).
    Returns {} when IG serves the login wall — we never fabricate."""
    htmldoc = fetch_raw_html(ig_url)
    if not htmldoc:
        return {}
    m = _META_DESC_RE.search(htmldoc)
    if not m:
        return {}
    desc = _clean(m.group(1))
    out: dict = {}
    fm = _IG_FOLLOWERS_RE.search(desc)
    if fm:
        out["followers"] = fm.group(1)
    if desc:
        out["bio_snippet"] = desc[:200]
    return out


def _hours_gaps(hours: list[str] | None) -> list[str]:
    """Human-readable after-hours gaps from Places weekdayDescriptions, e.g.
    ['Closed on Friday', 'Closes by 6 PM most days']. Conservative: only states
    what the hours literally say."""
    if not hours:
        return []
    gaps: list[str] = []
    closed_days = [h.split(":")[0].strip() for h in hours if "closed" in h.lower()]
    if closed_days:
        gaps.append(f"Closed on {', '.join(closed_days[:3])}")
    # AUDIT C7: the old bar (closes by 6 PM on >=4 days) fired for virtually every
    # normal business, making "limited hours" noise dressed as insight. A 5 PM close
    # is genuinely early for a clinic/spa (evening is their peak enquiry window), and
    # requiring 5+ days makes it a real pattern rather than a one-off.
    early = 0
    for h in hours:
        m = re.search(r"(?:–|-|to)\s*([0-9]{1,2})(?::[0-9]{2})?\s*PM", h, re.I)
        if m and int(m.group(1)) <= 5:
            early += 1
    if early >= 5:
        gaps.append("Closes by 5 PM most days (evening enquiries unanswered)")
    return gaps


def build_dossier(db: Session, company: Company) -> dict:
    """Collect + persist everything we can verifiably note about this business.
    Idempotent: overwrites company.raw['dossier']."""
    places = (company.raw or {}).get("places") or {}
    socials = (company.raw or {}).get("socials") or {}

    services, about = _website_menu(company.domain or "")
    ig_meta = _instagram_public_meta(socials["instagram"]) if socials.get("instagram") else {}

    # Tri-state POSITIVE booking detection (True/False/None) — the no_online_booking
    # signal only records the negative; the cohort stat needs confirmed positives too.
    from app.services.local_signals import _booking_status
    has_booking, _ = _booking_status(company.website or
                                     (f"https://{company.domain}" if company.domain else None))

    dossier = {
        "online_booking": has_booking,
        "services": services,
        "about_snippet": about,
        "rating": places.get("rating"),
        "review_count": places.get("review_count"),
        "business_type": places.get("type"),
        "hours": places.get("hours"),
        "hours_gaps": _hours_gaps(places.get("hours")),
        "social_platforms": sorted(socials.keys()),
        "instagram": ({"url": socials.get("instagram"), **ig_meta}
                      if socials.get("instagram") else None),
        "booking": ("no online booking" if any(
            s.kind == "no_online_booking" for s in getattr(company, "signals", []) or [])
            else None),
    }
    company.raw = {**(company.raw or {}), "dossier": dossier}
    flag_modified(company, "raw")
    db.commit()
    log.info("dossier_built", company=company.name,
             services=len(services), ig="followers" in ig_meta,
             hours_gaps=len(dossier["hours_gaps"]))
    return dossier


def cohort_booking_stat(db: Session, company: Company) -> str | None:
    """Honest market-context line for drafts: of the businesses WE actually scanned in
    this org (tri-state online_booking recorded in their dossiers), how many take
    bookings online. Only returns a line when the target itself LACKS online booking
    and we have >= 5 confirmed datapoints — otherwise None (never invent urgency)."""
    my_dossier = (company.raw or {}).get("dossier") or {}
    if my_dossier.get("online_booking") is not False:
        return None  # target has booking (True) or unknown (None) -> no angle
    rows = db.query(Company.raw).filter(
        Company.organization_id == company.organization_id,
        Company.id != company.id).all()
    known = with_booking = 0
    for (raw,) in rows:
        ob = ((raw or {}).get("dossier") or {}).get("online_booking")
        if ob is not None:
            known += 1
            if ob:
                with_booking += 1
    if known < 5 or with_booking == 0:
        return None
    return (f"market: {with_booking} of the {known} similar local businesses we "
            f"checked already take bookings online")
