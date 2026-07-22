"""Find a local business OWNER's LinkedIn profile via a Google search.

LinkedIn is the strongest direct-to-owner channel for these SMBs (far better than an
info@ inbox), and a plain Google query "{business} {city} owner linkedin" reliably
surfaces the owner's name + profile. We read the SERP (Serper/Google, Tavily fallback) —
we do NOT scrape LinkedIn — and surface the profile URL for a MANUAL DM (LinkedIn bans
automated outreach, same as Instagram).

The hard part is disambiguation: a name like "Oasis Med Spa" returns owners in Phoenix,
Woodinville, Minnesota... all different businesses. So every candidate is scored on
business-name + city + a role word, and we attach an owner ONLY when the match clearly
belongs to THIS lead. Below the bar we return found=False and persist nothing (the app's
nothing-static rule) — a wrong owner is worse than no owner.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.company import Company
from app.models.contact import Contact
from app.services.owner_email import _split_name

log = get_logger(__name__)

# Role words that mark a decision-maker (owner tier). "Manager" is deliberately NOT here:
# a "Medical Spa Manager" is staff, not the owner we want.
_ROLE = re.compile(
    r"\b(owner|co-?owner|founder|co-?founder|ceo|managing director|proprietor|"
    r"principal|medical director|md/owner)\b", re.I)

# Generic med-spa words carry no identifying signal — the DISTINCTIVE words do.
_GENERIC_BIZ = {
    "spa", "med", "medi", "medspa", "medical", "center", "centre", "clinic", "laser",
    "skin", "skincare", "aesthetic", "aesthetics", "beauty", "wellness", "salon", "care",
    "cosmetic", "cosmetics", "dermatology", "derma", "health", "healthcare", "the", "and",
    "of", "llc", "inc", "ltd", "co", "group", "surgery", "plastic",
}

# "... owner, Louisa Proulx" / "Louisa Proulx, owner" — owner name stated inline in a
# snippet (often the business's own LinkedIn page result).
_OWNER_BEFORE = re.compile(
    r"owner[,:\-]?\s+((?:[A-Z][A-Za-z'’.-]+\s){1,2}[A-Z][A-Za-z'’.-]+)")
_OWNER_AFTER = re.compile(
    r"((?:[A-Z][A-Za-z'’.-]+\s){1,2}[A-Z][A-Za-z'’.-]+)[,\s]+(?:is\s+the\s+)?"
    r"(?:owner|founder|co-?owner|ceo)")
# "the owner of X (based in Dubai) is Dr. Sana Sajan" — the AI-overview / prose phrasing.
_OWNER_IS = re.compile(
    r"\b(?:owner|founder|co-?owner|proprietor)\b[^.]{0,90}?\bis\s+(?:Dr\.?\s+)?"
    r"((?:[A-Z][A-Za-z'’.-]+\s){1,2}[A-Z][A-Za-z'’.-]+)")


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def _distinctive(company_name: str) -> list[str]:
    """The identifying words in a business name (drop generic med-spa filler)."""
    return [t for t in _tokens(company_name) if t not in _GENERIC_BIZ and len(t) > 2]


def _person_from_title(title: str) -> str | None:
    """'Louise Proulx - Owner at Renew' -> 'Louise Proulx'. Returns None when the head
    isn't a plausible two-word person name."""
    head = re.split(r"\s[-|–—]\s", title or "", maxsplit=1)[0].strip()
    return head if _split_name(head) else None


def score_candidate(*, name: str, url: str, title: str, snippet: str,
                    company_name: str, city: str | None) -> dict:
    """Score how confidently this SERP result is THIS business's owner. Pure + testable.
    Returns {score, accept, business, city_hit, role, profile}."""
    text = f"{title}\n{snippet}"
    low = text.lower()
    dist = _distinctive(company_name)
    biz_hits = sum(1 for t in dist if t in low)
    full_name_in = bool(company_name) and company_name.lower() in low
    city_hit = bool(city) and city.lower() in low
    role_hit = bool(_ROLE.search(text))
    is_profile = "/in/" in (url or "")

    score = 0
    score += 5 if full_name_in else biz_hits * 2
    score += 4 if city_hit else 0
    score += 3 if role_hit else 0
    score += 1 if is_profile else 0

    # ACCEPT only when the match clearly belongs to this lead: a real business match
    # (full name, or >=2 distinctive tokens) AND a role word AND the city lines up.
    # City is the anti-wrong-town guard — without it, Phoenix/Minnesota namesakes pass.
    business_ok = full_name_in or biz_hits >= 2
    accept = business_ok and role_hit and city_hit
    return {"score": score, "accept": accept, "business": business_ok,
            "city_hit": city_hit, "role": role_hit, "profile": is_profile}


def _owner_names_in_snippet(snippet: str) -> list[str]:
    """Owner names stated inline in a snippet, e.g. 'owner, Louisa Proulx'."""
    out: list[str] = []
    for pat in (_OWNER_BEFORE, _OWNER_AFTER, _OWNER_IS):
        for m in pat.finditer(snippet or ""):
            cand = m.group(1).strip()
            if _split_name(cand) and cand.lower() not in (c.lower() for c in out):
                out.append(cand)
    return out


def _normalize_results(raw: list[dict]) -> list[dict]:
    """Serper (title/link/snippet) + Tavily (title/url/content) -> one shape."""
    out = []
    for r in raw or []:
        out.append({
            "title": r.get("title") or "",
            "url": r.get("link") or r.get("url") or "",
            "snippet": r.get("snippet") or r.get("content") or "",
        })
    return out


def find_owner_linkedin_from_results(results: list[dict], *, company_name: str,
                                     city: str | None) -> dict:
    """The pure decision core: given SERP results, pick the best owner match (or none).
    Split out so it can be unit-tested against real SERP snippets without a network call."""
    best: dict | None = None
    for r in _normalize_results(results):
        url, title, snippet = r["url"], r["title"], r["snippet"]
        # candidate A: a LinkedIn /in/ profile whose title names a person
        if "/in/" in url:
            nm = _person_from_title(title)
            if nm:
                sc = score_candidate(name=nm, url=url, title=title, snippet=snippet,
                                     company_name=company_name, city=city)
                if sc["accept"] and (best is None or sc["score"] > best["_score"]):
                    best = {"name": nm, "linkedin_url": url.split("?")[0],
                            "title": "Owner", "_score": sc["score"],
                            "evidence": (title or snippet)[:200]}
        # candidate B: an owner name stated inline (often the business's own page).
        # Requires the business to actually be named in the same snippet.
        if company_name.lower() in f"{title} {snippet}".lower():
            for nm in _owner_names_in_snippet(f"{title} {snippet}"):
                # inline owner statement on a business result is a strong signal; still
                # require the city to appear to avoid a wrong-town namesake.
                city_hit = bool(city) and city.lower() in f"{title} {snippet}".lower()
                if not city_hit:
                    continue
                sc_score = 8
                if best is None or sc_score > best["_score"]:
                    li = url if "/in/" in url else None
                    best = {"name": nm, "linkedin_url": li, "title": "Owner",
                            "_score": sc_score, "evidence": snippet[:200]}
    if not best:
        return {"found": False}
    best.pop("_score", None)
    return {"found": True, **best}


def find_owner_linkedin(company: Company) -> dict:
    """Search Google for this company's owner LinkedIn and return the best match, or
    {found: False}. Never guesses — a low-confidence result is dropped."""
    from app.services.search import serper_search, tavily_search
    city = ((company.raw or {}).get("places") or {}).get("city") or company.city or ""
    q = f'{company.name} {city} owner OR founder linkedin'.strip()
    results = serper_search(q, max_results=10)
    if not results:
        results = tavily_search(q, max_results=10)
    res = find_owner_linkedin_from_results(results, company_name=company.name, city=city or None)
    log.info("owner_linkedin_search", company=str(company.id), city=city,
             found=res.get("found"), name=res.get("name"))
    return res


def attach_owner_linkedin(db: Session, company: Company) -> dict:
    """Find the owner on LinkedIn and, if confident, persist them as a top contact
    (deduped). Returns {found, name?, linkedin_url?}."""
    res = find_owner_linkedin(company)
    if not res.get("found"):
        return res
    name, li = res["name"], res.get("linkedin_url")
    # Dedup: skip if we already have this person (by name or LinkedIn URL).
    existing = db.execute(
        select(Contact).where(Contact.company_id == company.id)).scalars().all()
    for c in existing:
        if (li and c.linkedin_url == li) or c.name.strip().lower() == name.strip().lower():
            return {"found": True, "name": name, "linkedin_url": li or c.linkedin_url,
                    "already": True}
    from app.services.contacts import _make_contact
    first, _, last = name.partition(" ")
    contact = _make_contact(company, name=name, title="Owner",
                            linkedin_url=li, is_primary=False)
    db.add(contact)
    db.commit()
    return {"found": True, "name": name, "linkedin_url": li, "created": True}
