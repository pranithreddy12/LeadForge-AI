"""Do-not-contact / opt-out registry (UAE PDPL + Google/Yahoo unsubscribe duty).

An opt-out is honored PERMANENTLY and across channels for the org: once an email,
phone, or domain is listed, no future draft or send may target it. Entries are added
automatically when a reply asks to stop, or manually from the UI.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.company import Company
from app.models.contact import Contact
from app.models.optout import DoNotContact

log = get_logger(__name__)

# Unambiguous opt-out phrases. Kept tight on purpose - "no thanks" or "not interested"
# is a soft no, NOT a legal opt-out; only explicit stop/unsubscribe language counts.
_OPTOUT_PHRASES = (
    "unsubscribe", "opt out", "opt-out", "optout", "remove me", "take me off",
    "stop emailing", "stop contacting", "do not contact", "don't contact",
    "dont contact", "do not email", "don't email", "remove from your list",
    "leave me alone", "stop messaging",
)
# A bare "stop" only counts as a whole word (SMS/WhatsApp convention), so it doesn't
# fire on "stop by" / "bus stop".
_STOP_WORD = re.compile(r"\bstop\b", re.I)


def detect_optout(text: str | None) -> bool:
    if not text:
        return False
    low = text.lower()
    if any(p in low for p in _OPTOUT_PHRASES):
        return True
    # Lone "stop" (typical unsubscribe keyword) but not inside a longer phrase.
    return bool(_STOP_WORD.search(low)) and len(low.split()) <= 4


def normalize_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.strip().lower()


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits or None


def add_optout(db: Session, organization_id: uuid.UUID, value: str, *, kind: str = "email",
               reason: str | None = None, source: str = "manual",
               company_id: uuid.UUID | None = None) -> DoNotContact | None:
    """Idempotent add. Returns the row (existing or new), or None for an empty value."""
    value = (value or "").strip().lower()
    if not value:
        return None
    existing = db.execute(
        select(DoNotContact).where(DoNotContact.organization_id == organization_id,
                                   DoNotContact.value == value)
    ).scalar_one_or_none()
    if existing:
        return existing
    row = DoNotContact(organization_id=organization_id, value=value, kind=kind,
                       reason=(reason or "")[:200] or None, source=source,
                       company_id=company_id)
    db.add(row)
    db.commit()
    log.info("optout_added", org=str(organization_id), kind=kind, source=source)
    return row


def optout_company(db: Session, company: Company, *, reason: str | None = None,
                   source: str = "manual") -> int:
    """Opt out an entire lead: its domain + every known contact email/phone. Returns
    how many identifiers were registered."""
    n = 0
    if company.domain:
        if add_optout(db, company.organization_id, company.domain, kind="domain",
                      reason=reason, source=source, company_id=company.id):
            n += 1
    contacts = db.execute(
        select(Contact).where(Contact.company_id == company.id)).scalars().all()
    phone = ((company.raw or {}).get("places") or {}).get("phone")
    values: list[tuple[str, str]] = []
    for c in contacts:
        if c.email:
            values.append((normalize_email(c.email) or "", "email"))
    if phone:
        values.append((normalize_phone(phone) or "", "phone"))
    for v, k in values:
        if v and add_optout(db, company.organization_id, v, kind=k, reason=reason,
                            source=source, company_id=company.id):
            n += 1
    return n


def optout_reason(db: Session, organization_id: uuid.UUID, *, email: str | None = None,
                  phone: str | None = None, domain: str | None = None) -> str | None:
    """If any identifier is on the do-not-contact list, return a reason string, else
    None. Used by suppression_reason so opt-outs block drafting AND sending."""
    candidates: list[str] = []
    e = normalize_email(email)
    if e:
        candidates.append(e)
    p = normalize_phone(phone)
    if p:
        candidates.append(p)
    if domain:
        candidates.append(domain.strip().lower())
    if not candidates:
        return None
    hit = db.execute(
        select(DoNotContact.value).where(
            DoNotContact.organization_id == organization_id,
            DoNotContact.value.in_(candidates)).limit(1)
    ).scalar_one_or_none()
    return f"opted_out: '{hit}' is on the do-not-contact list" if hit else None
