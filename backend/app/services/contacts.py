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

    # ---- 3. Email WATERFALL: every configured source runs, results merge, then rank.
    # Previously Hunter and scraping were either/or (elif), so one weak Hunter hit
    # blocked scraping entirely. A waterfall runs both, dedupes, and ranks by QUALITY
    # so a named person's address always beats a generic info@ as the recipient.
    if company.domain:
        found: dict[str, dict] = {}   # email -> {name, title, confidence, source}

        def _offer(email: str | None, *, name: str, title: str,
                   confidence: int | None, source: str) -> None:
            if not email:
                return
            e = email.strip().lower()
            prev = found.get(e)
            # keep the richest record for a duplicate address
            if prev is None or (confidence or 0) > (prev.get("confidence") or 0):
                found[e] = {"name": name, "title": title,
                            "confidence": confidence, "source": source}

        # tier 1 — Hunter domain search (named people + positions when it has them)
        if cfg["contact_find_hunter"]:
            key = resolve_credential(db, company.organization_id, "hunter_api_key")
            from app.services import hunter
            for h in hunter.find_email(company.domain, company.name, api_key=key or None):
                nm = ((h.get("first_name") or "") + " " + (h.get("last_name") or "")).strip()
                _offer(h.get("email"), name=nm or h["email"],
                       title=h.get("position") or "Decision maker",
                       confidence=h.get("confidence"), source="hunter")

        # tier 2 — the company's own website (free, and often the only source that works
        # for local SMBs). Runs even when Hunter returned something.
        if cfg["contact_find_scrape"]:
            from app.services.scraper import scrape_emails_for_domain
            for addr in scrape_emails_for_domain(company.domain):
                local = addr.split("@")[0]
                _offer(addr, name=f"{company.name} ({local}@)",
                       title="Sales" if local in ("sales", "hello", "info", "contact") else "Contact",
                       confidence=None, source="scraped")

        # rank: a real person's mailbox outranks a shared front desk, and a verified
        # address outranks an unverified one. The top of this list becomes the primary
        # contact -> the draft's recipient.
        ranked = sorted(
            found.items(),
            key=lambda kv: (_email_quality(kv[0]), kv[1].get("confidence") or 0),
            reverse=True)
        for i, (addr, info) in enumerate(ranked):
            new_contacts.append(_make_contact(
                company, name=info["name"], title=info["title"], email=addr,
                email_confidence=info.get("confidence"), personas=personas,
                is_primary=(i == 0 and not places_phone)))
        if ranked:
            log.info("contacts_waterfall", company=str(company.id), n=len(ranked),
                     sources=sorted({v["source"] for _, v in ranked}),
                     best=ranked[0][0], best_quality=_email_quality(ranked[0][0]))

    # ---- 4. Decision-maker names (Dr./owner) from About/Team pages -----------
    if company.domain and cfg["contact_find_scrape"]:
        from app.services.scraper import scrape_decision_makers
        people = scrape_decision_makers(company.domain)
        for i, full_name in enumerate(people):
            new_contacts.append(_make_contact(
                company, name=full_name, title="Owner/Dentist", personas=personas,
                # The named decision-maker leads the greeting; primary only if no phone.
                is_primary=(i == 0 and not places_phone)))
        if people:
            log.info("decision_makers_found", company=str(company.id), names=people[:3])

    # ---- 5. Social profiles (Instagram/Facebook/LinkedIn/TikTok/YouTube/WhatsApp)
    # from their own website — for local SMBs Instagram is often THE channel.
    if company.domain and cfg["contact_find_scrape"]:
        from sqlalchemy.orm.attributes import flag_modified
        from app.services.scraper import scrape_social_links
        socials = scrape_social_links(company.domain)
        if socials:
            company.raw = {**(company.raw or {}), "socials": socials}
            flag_modified(company, "raw")
            db.commit()
            log.info("socials_found", company=str(company.id),
                     platforms=list(socials.keys()))

    persisted = _persist(db, company, new_contacts)

    # ---- 6. Waterfall's LAST tier: turn the owner's NAME into their own mailbox.
    # Runs only when we still have no person-level address (i.e. every email we found
    # is a front desk) — that's the whole info@ problem. Persists nothing unless the
    # address is verified, so a guess can never bounce.
    if company.domain and cfg["contact_find_scrape"]:
        best = max((_email_quality(c.email) for c in persisted if c.email), default=0)
        if best < 2:
            try:
                from app.services.owner_email import find_owner_email
                res = find_owner_email(db, company)
                if res.get("found"):
                    log.info("owner_email_waterfall", company=str(company.id),
                             method=res.get("method"))
                    persisted = db.execute(
                        select(Contact).where(Contact.company_id == company.id)
                    ).scalars().all()
            except Exception as e:
                log.info("owner_email_skipped", error=str(e)[:120])
    return persisted


_GENERIC_MAILBOXES = (
    "info", "contact", "contactus", "hello", "hi", "admin", "office", "reception",
    "enquiry", "enquiries", "inquiry", "inquiries", "support", "customersupport",
    "help", "book", "booking", "bookings", "appointment", "appointments",
    "reservations", "reservation", "sales", "mail", "email", "welcome", "care",
    "wecare", "team", "clinic", "spa", "general", "frontdesk", "desk", "billing",
    "accounts", "finance", "marketing", "press", "media", "partnership",
    "partnerships", "feedback", "complaints", "orders", "shop", "store",
    # role / industry words that read like a name but are a shared inbox
    "leads", "lead", "aesthetic", "aesthetics", "wellness", "medical", "health",
    "healthcare", "beauty", "skin", "laser", "derma", "dermatology", "dental",
    "doctor", "doctors", "reception1", "frontoffice", "crm", "newpatients",
)
# BRANCH / LOCATION aliases (dubai@, jumeirah@, marina@). These read like a person's
# given name to a naive check but are a site inbox — pitching them lands at a branch
# front desk, not the owner. Multi-branch clinics use these constantly.
_LOCATION_MAILBOXES = (
    "dubai", "abudhabi", "abu", "sharjah", "ajman", "fujairah", "rak",
    "rasalkhaimah", "ummalquwain", "uae", "emirates", "jumeirah", "marina",
    "downtown", "deira", "burdubai", "difc", "jbr", "albarsha", "barsha",
    "motorcity", "silicon", "mirdif", "karama", "satwa", "tecom", "jlt",
    "branch", "hq", "head", "headoffice", "main", "city", "mall", "riyadh",
    "doha", "london", "india", "usa",
)


def _email_quality(email: str) -> int:
    """Rank an address by how likely it reaches a DECISION-MAKER.

      2 = a person's mailbox (sarah@, a.ullah@)  -> the one worth pitching
      1 = unknown shape                          -> maybe a person
      0 = a shared front desk (info@, bookings@) -> a receptionist reads this

    Local businesses publish info@ and hide the owner, so without this ranking the
    draft's recipient is whatever source answered first — usually the front desk.
    """
    local = (email or "").split("@")[0].lower()
    if not local:
        return 0
    base = re.split(r"[.\-_+]", local)[0]
    if local in _GENERIC_MAILBOXES or base in _GENERIC_MAILBOXES:
        return 0
    # A branch/location alias (dubai@, jumeirah@) is a site inbox, not a person —
    # even though it looks like a given name.
    if local in _LOCATION_MAILBOXES or base in _LOCATION_MAILBOXES:
        return 0
    # A mailbox that echoes the BRAND is an alias, not a person:
    # healthcallclinic@healthcall.ae, jumeirahone@jumeirah.com. General rule — no
    # word list can keep up with every brand, but the domain always names the brand.
    domain_root = (email or "").split("@")[-1].split(".")[0].lower()
    a, b = re.sub(r"[^a-z]", "", local), re.sub(r"[^a-z]", "", domain_root)
    if a and b and len(b) >= 4 and (a in b or b in a):
        return 0
    # first.last / f.last / a person's given name reads as an individual
    if re.fullmatch(r"[a-z]+([._-][a-z]+)+", local) or re.fullmatch(r"[a-z]{3,}", local):
        return 2
    return 1


def _make_contact(company: Company, *, name: str, title: str,
                  email: str | None = None,
                  email_confidence: int | None = None,
                  phone: str | None = None,
                  linkedin_url: str | None = None,
                  is_primary: bool = False,
                  personas: list[str] | None = None) -> Contact:
    from app.services.contact_intelligence import compute_influence
    from app.services.owner_email import _is_person_name
    first, _, last = name.partition(" ")
    seniority = _seniority_for(title)
    department = _department_for(title)
    influence, buying_power = compute_influence(
        title=title, seniority=seniority, department=department,
        buyer_personas=personas,
    )
    # A front-desk mailbox ("info@"), an email-as-name, or the "{business} (main line)"
    # phone pseudo-contact is NOT a decision-maker — never let one outrank a real named
    # person in the influence sort. Capped low so the top-influence contact (and the
    # draft recipient) is the actual person whenever we have one. Also cap when the email
    # itself is a generic front-desk address, regardless of the display name.
    is_person = ("@" not in (name or "")) and _is_person_name(name, company.name)
    generic_mailbox = bool(email) and _email_quality(email) == 0
    if not is_person or generic_mailbox:
        influence = min(influence, 10)
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
