from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.company import Company
from app.models.contact import Contact
from app.services.email_validation import validate_email
from app.services.search import serper_search

log = get_logger(__name__)

TARGET_TITLES = [
    "CEO", "Chief Executive Officer",
    "Founder", "Co-Founder", "Co Founder",
    "CTO", "Chief Technology Officer",
    "VP Engineering", "VP of Engineering",
    "Head of Engineering",
    "Head of Sales", "VP Sales", "VP of Sales",
    "Head of Operations", "COO",
    "Head of Marketing", "VP Marketing",
]


def _seniority_for(title: str) -> str:
    t = (title or "").lower()
    # Gatekeeper/assistant roles must NOT be promoted to cxo by a 'chief' substring.
    if "chief of staff" in t or "executive assistant" in t:
        return "manager"
    # C-level: whole-word acronyms or "chief … officer", plus founder.
    if re.search(r"\b(ceo|cto|coo|cfo|cmo|ciso|cpo|cro)\b", t) \
            or re.search(r"\bchief\b.*\bofficer\b", t) \
            or re.search(r"\b(founder|co-?founder)\b", t):
        return "cxo"
    if re.search(r"\b(vp|svp|evp)\b", t) or "vice president" in t:
        return "vp"
    if "head of" in t or re.search(r"\bdirector\b", t):
        return "director"
    # 'lead' as a whole word (Tech Lead, Team Lead) — but not "lead generation".
    if "lead generation" in t:
        return "ic"
    if re.search(r"\bmanager\b", t) or re.search(r"\blead\b", t):
        return "manager"
    return "ic"


def _department_for(title: str) -> str | None:
    t = (title or "").lower()
    if any(k in t for k in ["engineer", "technology", "cto", "tech"]):
        return "engineering"
    if any(k in t for k in ["sales", "revenue", "growth", "biz dev"]):
        return "sales"
    if "market" in t:
        return "marketing"
    if "operation" in t or "coo" in t:
        return "operations"
    if "ceo" in t or "founder" in t or "president" in t:
        return "leadership"
    return None


def _normalize_linkedin_url(url: str) -> str | None:
    if not url or "linkedin.com/in/" not in url:
        return None
    return url.split("?")[0].rstrip("/")


def _icp_personas(db: Session, company: Company) -> list[str]:
    if not company.icp_id:
        return []
    from app.models.icp import ICP
    icp = db.get(ICP, company.icp_id)
    return (icp.buyer_personas or []) if icp else []


def discover_contacts_for_company(db: Session, company: Company) -> list[Contact]:
    """Find decision-maker contacts. Email finding is Hunter-FIRST (highest-confidence
    emails), falling back to website scraping when Hunter returns nothing. Also runs
    SERP/LinkedIn discovery for names/titles. For LOCAL businesses the Places phone is
    the PRIMARY contact (WhatsApp uses it); Hunter/scraped email is secondary.
    Persists Contact rows (deduped per (company, linkedin or email or name))."""
    from app.services.settings_resolver import (pipeline_config, resolve_credential,
                                                settings_row)
    s = settings_row(db, company.organization_id)
    cfg = pipeline_config(db, company.organization_id)
    is_local = bool(s and s.discovery_mode == "local")
    personas = _icp_personas(db, company)
    new_contacts: list[Contact] = []

    # ---- 1. SERP-driven LinkedIn discovery (names/titles) --------------------
    for title in (TARGET_TITLES if cfg["contact_find_linkedin"] else []):
        q = f'site:linkedin.com/in/ "{title}" "{company.name}"'
        for hit in serper_search(q, max_results=3):
            link = hit.get("link") or ""
            li_url = _normalize_linkedin_url(link)
            if not li_url:
                continue
            heading = (hit.get("title") or "").split(" - ")
            name = heading[0].strip() if heading else hit.get("title", "").strip()
            if len(name) < 3 or len(name) > 80:
                continue
            new_contacts.append(_make_contact(company, name=name, title=title,
                                              linkedin_url=li_url, personas=personas))

    # ---- 2. LOCAL: the Places phone is the PRIMARY contact -------------------
    places_phone = ((company.raw or {}).get("places") or {}).get("phone")
    if places_phone:
        from app.services.whatsapp_sender import normalize_phone
        phone = normalize_phone(places_phone) or places_phone
        new_contacts.append(_make_contact(
            company, name=f"{company.name} (main line)", title="Owner/Manager",
            phone=phone, personas=personas, is_primary=True))

    # ---- 3. Email: Hunter FIRST, website-scrape FALLBACK (both Settings-gated) ----
    if company.domain:
        key = resolve_credential(db, company.organization_id, "hunter_api_key")
        from app.services import hunter
        hits = (hunter.find_email(company.domain, company.name, api_key=key or None)
                if cfg["contact_find_hunter"] else [])
        if hits:
            for i, h in enumerate(hits):
                fn, ln = (h.get("first_name") or ""), (h.get("last_name") or "")
                name = (fn + " " + ln).strip() or h["email"]
                new_contacts.append(_make_contact(
                    company, name=name, title=h.get("position") or "Decision maker",
                    email=h["email"], email_confidence=h["confidence"],
                    personas=personas,
                    # The single highest-confidence email is the primary contact in
                    # B2B mode (in local mode the phone already claimed primary).
                    is_primary=(i == 0 and not places_phone)))
            log.info("contacts_source", company=str(company.id), source="hunter",
                     n=len(hits), top_confidence=hits[0]["confidence"])
        elif cfg["contact_find_scrape"]:
            from app.services.scraper import scrape_emails_for_domain
            scraped = scrape_emails_for_domain(company.domain)
            for j, addr in enumerate(scraped):
                local = addr.split("@")[0]
                title = "Sales" if local in ("sales", "hello", "info", "contact") else "Contact"
                new_contacts.append(_make_contact(
                    company, name=f"{company.name} ({local}@)", title=title,
                    email=addr, personas=personas,
                    is_primary=(j == 0 and not places_phone)))
            log.info("contacts_source", company=str(company.id),
                     source="scraped", n=len(scraped),
                     hunter_empty=True)

    persisted = _persist(db, company, new_contacts)
    return persisted


def _make_contact(company: Company, *, name: str, title: str,
                  email: str | None = None,
                  email_confidence: int | None = None,
                  phone: str | None = None,
                  linkedin_url: str | None = None,
                  is_primary: bool = False,
                  personas: list[str] | None = None) -> Contact:
    from app.services.contact_intelligence import compute_influence
    first, _, last = name.partition(" ")
    seniority = _seniority_for(title)
    department = _department_for(title)
    influence, buying_power = compute_influence(
        title=title, seniority=seniority, department=department,
        buyer_personas=personas,
    )
    return Contact(
        organization_id=company.organization_id,
        company_id=company.id,
        name=name,
        first_name=first or None,
        last_name=last or None,
        title=title,
        seniority=seniority,
        department=department,
        influence_score=influence,
        buying_power=buying_power,
        email=email,
        email_confidence=email_confidence,
        phone=phone,
        linkedin_url=linkedin_url,
        is_primary=is_primary,
    )


def _persist(db: Session, company: Company, candidates: list[Contact]) -> list[Contact]:
    if not candidates:
        return []
    existing = db.execute(
        select(Contact).where(Contact.company_id == company.id)
    ).scalars().all()
    existing_keys = {(c.linkedin_url or "", (c.email or "").lower(), c.name.lower())
                     for c in existing}

    persisted: list[Contact] = []
    for c in candidates:
        key = (c.linkedin_url or "", (c.email or "").lower(), c.name.lower())
        # Match by any of linkedin / email / name to dedupe loosely.
        if any(
            (c.linkedin_url and ek[0] == c.linkedin_url)
            or (c.email and ek[1] == c.email.lower())
            or (ek[2] == c.name.lower())
            for ek in existing_keys
        ):
            continue
        existing_keys.add(key)
        db.add(c)
        persisted.append(c)
    db.commit()
    for c in persisted:
        db.refresh(c)
    return persisted


def validate_and_store(db: Session, contact_id: uuid.UUID) -> Contact | None:
    contact = db.get(Contact, contact_id)
    if not contact or not contact.email:
        return contact
    result = validate_email(contact.email)
    contact.email_status = result.status
    contact.email_confidence = result.confidence
    from sqlalchemy import func
    contact.email_validated_at = func.now()
    db.commit()
    db.refresh(contact)
    return contact
