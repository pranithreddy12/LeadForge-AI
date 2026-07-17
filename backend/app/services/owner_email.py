"""Turn a scraped OWNER NAME + their domain into a real decision-maker inbox.

Local businesses publish info@ and hide the owner. But we often scrape the owner's
NAME ("Dr. Ahsan Ullah") from the site. From a name + domain we can recover a personal
address two ways, in order of trust:

  1. Hunter Email Finder — Hunter's guess for that specific person, with a confidence
     score. Trusted at score >= 70.
  2. Pattern construction + verification — build the common corporate patterns
     (a.ullah@, ahsan@, ahsanullah@ ...) and VERIFY each against MX + NeverBounce.
     Only a candidate that verifies is kept.

NOTHING-STATIC: an unverifiable guess is NEVER persisted as a sendable email. A wrong
owner address bounces (hurting sender reputation) or reaches a stranger — both worse
than falling back to WhatsApp. If nothing verifies, we store nothing and say so.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.company import Company
from app.models.contact import Contact

log = get_logger(__name__)

_HUNTER_TRUST = 70   # Hunter score at/above which we trust the finder result outright


def _split_name(name: str) -> tuple[str, str] | None:
    """('Dr. Ahsan Ullah') -> ('ahsan', 'ullah'). Drops titles, keeps first + last."""
    parts = [p for p in re.split(r"\s+", re.sub(r"[^A-Za-z\s'-]", " ", name or "")) if p]
    parts = [p for p in parts if p.lower().strip(".") not in
             ("dr", "mr", "mrs", "ms", "prof", "doctor", "the")]
    if len(parts) < 2:
        return None
    return parts[0].lower(), parts[-1].lower()


def _patterns(first: str, last: str, domain: str) -> list[str]:
    """Common corporate local-part patterns, most-likely first."""
    f, l, fi, li = first, last, first[:1], last[:1]
    locals_ = [f, f"{f}.{l}", f"{fi}{l}", f"{f}{l}", f"{f}_{l}", f"{fi}.{l}",
               f"{f}{li}", l]
    seen: list[str] = []
    for lp in locals_:
        e = f"{lp}@{domain}"
        if e not in seen:
            seen.append(e)
    return seen


def find_owner_email(db: Session, company: Company) -> dict:
    """Best-effort: find + persist a verified decision-maker email for this company.
    Returns {found, email?, name?, method?, confidence?, reason?}."""
    domain = company.domain
    if not domain:
        return {"found": False, "reason": "no_domain"}

    # The owner's name: a named contact first, else scrape the site.
    named = db.execute(
        select(Contact).where(Contact.company_id == company.id,
                              Contact.name.is_not(None)).limit(1)
    ).scalar_one_or_none()
    name = named.name if named else None
    if not name:
        from app.services.scraper import scrape_decision_makers
        names = scrape_decision_makers(domain)
        name = names[0] if names else None
    if not name:
        return {"found": False, "reason": "no_owner_name"}
    split = _split_name(name)
    if not split:
        return {"found": False, "reason": "unparseable_name", "name": name}
    first, last = split

    from app.services.email_validation import _has_real_key, validate_email
    from app.services.settings_resolver import resolve_credential

    # 1) Hunter Email Finder — trusted at a good score.
    from app.services.hunter import find_person_email
    key = resolve_credential(db, company.organization_id, "hunter_api_key") or None
    hit = find_person_email(domain, first, last, api_key=key)
    chosen = None
    if hit and hit["confidence"] >= _HUNTER_TRUST:
        chosen = {"email": hit["email"], "method": "hunter",
                  "confidence": hit["confidence"]}

    # 2) Pattern construction + verification (also verifies a low-score Hunter guess).
    #    ONLY when a REAL validator is configured — without one, validate_email returns
    #    fabricated demo data, and persisting a guessed address on fake proof is exactly
    #    the bounce risk we must avoid.
    if chosen is None and _has_real_key():
        candidates = _patterns(first, last, domain)
        if hit and hit.get("email") and hit["email"] not in candidates:
            candidates.insert(0, hit["email"])   # verify Hunter's low-score guess too
        for cand in candidates:
            v = validate_email(cand)
            if v.status == "valid":   # provider confirms it can receive
                chosen = {"email": cand, "method": f"verified/{v.provider}",
                          "confidence": v.confidence or 0}
                break

    if chosen is None:
        reason = "no_verified_email" if _has_real_key() else "needs_hunter_or_neverbounce_key"
        return {"found": False, "reason": reason, "name": name}

    # Persist as a high-influence decision-maker contact, deduped by email.
    email = chosen["email"].lower()
    existing = db.execute(
        select(Contact).where(Contact.company_id == company.id,
                              Contact.email == email)
    ).scalar_one_or_none()
    if existing is None:
        db.add(Contact(
            organization_id=company.organization_id, company_id=company.id,
            name=name, first_name=first.title(), last_name=last.title(),
            title="Owner / Decision-maker", seniority="cxo",
            buying_power="decision_maker", influence_score=90, email=email))
        db.commit()
    log.info("owner_email_found", company=str(company.id), method=chosen["method"],
             confidence=chosen["confidence"])
    return {"found": True, "email": email, "name": name,
            "method": chosen["method"], "confidence": chosen["confidence"]}
