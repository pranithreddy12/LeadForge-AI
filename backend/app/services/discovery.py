from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.qualification_engine import Candidate, qualify_candidates
from app.core.logging import get_logger
from app.models.company import Company
from app.models.icp import ICP
from app.services.search import serper_search, tavily_search

log = get_logger(__name__)

# domains we don't want to ingest as "companies"
EXCLUDED_DOMAINS = {
    "linkedin.com", "wikipedia.org", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "youtube.com", "crunchbase.com", "producthunt.com",
    "github.com", "medium.com", "reddit.com", "news.ycombinator.com",
    "indeed.com", "glassdoor.com", "google.com",
}


@dataclass
class DiscoveredCompany:
    name: str
    domain: str | None
    website: str | None
    description: str | None
    linkedin_url: str | None
    source: str
    industry: str | None = None
    confidence: int | None = None
    ai_verified: bool = True
    # Buying signal attached when this company was EXTRACTED from a signal source
    # (funding news / own careers page). Persisted as a real Signal row so scoring +
    # the UI see the intent — not just an in-memory artifact.
    signal: dict | None = None
    # Gate outcome: None for confirmed buyers; "held_unknown" for candidates the gate
    # couldn't confirm (provider error / low confidence). Held rows ARE persisted (so a
    # retry can re-classify and outreach can suppress them) but kept OUT of the scoring
    # pipeline until confirmed.
    classification_status: str | None = None


def _domain_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else "https://" + url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    return host or None


def _is_excluded(domain: str | None) -> bool:
    if not domain:
        return True
    return any(domain == d or domain.endswith("." + d) for d in EXCLUDED_DOMAINS)


def _normalize_name(name: str) -> str:
    n = re.sub(r"\s+", " ", name).strip(" -–—|").strip()
    n = re.sub(r"\s*[-|–—]\s*.+$", "", n)   # strip suffix after dash
    return n[:200]


def build_queries(icp: ICP, extra_keywords: list[str] | None = None) -> list[str]:
    """Buyer-intent queries, in priority order:
      1. The ICP's stored `search_queries` (generated to find buyers, not competitors).
      2. On-the-fly LLM generation from the ICP + seller's business description.
      3. Deterministic templating fallback (when no LLM is available).
    """
    extra = list(extra_keywords or [])

    # 1. Stored buyer-intent queries.
    stored = [q for q in (getattr(icp, "search_queries", None) or []) if q]
    if stored:
        return _dedup(stored + extra)[:12]

    # 2. Generate on the fly from the seller's offering + ICP.
    try:
        from app.ai.query_engine import generate_search_queries
        business = ""
        if icp.project is not None:
            business = (icp.project.business_description or "")
            if icp.project.target_offering:
                business += f"\nOffering: {icp.project.target_offering}"
        icp_dict = {
            "industries": icp.industries, "buyer_personas": icp.buyer_personas,
            "buying_signals": icp.buying_signals, "countries": icp.countries,
            "keywords": icp.keywords,
            "employee_min": icp.employee_min, "employee_max": icp.employee_max,
        }
        generated = generate_search_queries(business_description=business, icp=icp_dict, limit=10)
        if generated:
            return _dedup(generated + extra)[:12]
    except Exception as e:  # never let query-gen failure block discovery
        log.info("query_gen_failed_fallback_template", error=str(e))

    # 3. Deterministic templating fallback — intent-flavored, not service-flavored.
    return _template_queries(icp, extra)


def _dedup(items: list[str]) -> list[str]:
    """Order-preserving de-duplication (case-insensitive)."""
    seen: set[str] = set()
    out: list[str] = []
    for q in items:
        k = q.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(q)
    return out


def _template_queries(icp: ICP, extra_keywords: list[str]) -> list[str]:
    """Deterministic fallback. Bias toward buying-signal phrasing over the
    seller's service terms so we still lean at buyers, not competitors."""
    kws = list(icp.keywords or [])[:6] + list(extra_keywords or [])
    countries = (icp.countries or [])[:2] or [""]
    industries = (icp.industries or [])[:3] or [""]
    signals = (icp.buying_signals or [])[:2]

    queries: list[str] = []
    for ind in industries:
        for country in countries:
            # signal-led queries find buyers in growth mode
            for sig in signals:
                q = f"{ind} {sig} {country}".strip()
                if q and q not in queries:
                    queries.append(q)
            for kw in kws[:2]:
                q = f"{ind} {kw} {country}".strip()
                if q and q not in queries:
                    queries.append(q)
    if not queries:
        queries.append(" ".join(filter(None, [icp.industries[0] if icp.industries else "", "companies"])))
    return queries[:8]


def discover_via_search(icp: ICP, *, limit: int = 25,
                        extra_keywords: list[str] | None = None) -> list[DiscoveredCompany]:
    """Run Tavily + Serper, then run every raw result through the Company
    Qualification Engine so only real operating companies are returned.

    Returns deduped, qualified companies with AI-cleaned names + industries.
    """
    queries = build_queries(icp, extra_keywords)
    raw: dict[str, Candidate] = {}   # keyed by domain to dedupe early

    from app.services.serp_filter import process_hit

    def _two_track(title, url, snippet, src):
        # Track 1 drop junk; track 2 extract named companies from funding/job sources.
        cand = process_hit(title=title, url=url, snippet=snippet, source=src,
                           drop_junk=True, extract=True)
        if cand and cand.domain and not _is_excluded(cand.domain) and cand.domain not in raw:
            raw[cand.domain] = cand

    for q in queries:
        for hit in tavily_search(q, max_results=10):
            src = "demo" if hit.get("demo") else "tavily"
            _two_track(hit.get("title"), hit.get("url"), hit.get("content"), src)
        for hit in serper_search(q, max_results=10):
            src = "demo" if hit.get("demo") else "serper"
            _two_track(hit.get("title"), hit.get("link"), hit.get("snippet"), src)
        # collect a bit more than `limit` so qualification has room to reject.
        if len(raw) >= limit * 4:
            break

    candidates = list(raw.values())
    seller = None
    if icp.project is not None:
        seller = icp.project.business_description or None
        if seller and icp.project.target_offering:
            seller += f"\nOffering: {icp.project.target_offering}"
    accepted, stats, held = qualify_candidates(candidates, seller_description=seller)
    log.info("discovery_qualified", total=stats["total"], accepted=stats["accepted"],
             held=stats["held_unknown"], by_label=stats["by_label"])

    out: list[DiscoveredCompany] = []
    for a in accepted[:limit]:
        c: Candidate = a["candidate"]
        out.append(DiscoveredCompany(
            name=a["company_name"] or _normalize_name(c.title),
            domain=c.domain,
            website=f"https://{c.domain}",
            description=(c.snippet or "")[:1000] or None,
            linkedin_url=None,
            source=c.source,
            industry=a["industry"] or None,
            confidence=a["confidence"],
            ai_verified=a.get("ai_verified", True),
            signal=c.signal,
        ))
    # `held` (unknown / provider-error) candidates ARE persisted, marked held_unknown,
    # so a future pass can re-classify them and outreach can suppress them — but they
    # are kept OUT of the scoring/outreach pipeline until confirmed (the worker filters
    # company_ids by classification_status). Nothing-static: a transient LLM error
    # holds the candidate, never silently sends it and never drops it.
    for h in held:
        c = h["candidate"]
        if not c.domain:
            continue
        out.append(DiscoveredCompany(
            name=_clean_held_name(c), domain=c.domain, website=f"https://{c.domain}",
            description=(c.snippet or "")[:1000] or None, linkedin_url=None,
            source=c.source, industry=None, confidence=None, ai_verified=False,
            signal=c.signal, classification_status="held_unknown",
        ))
    if held:
        log.info("discovery_held_unknown", n=len(held),
                 domains=[h["candidate"].domain for h in held][:20])
    return out


def _clean_held_name(c) -> str:
    from app.ai.qualification_engine import _clean_title
    return _clean_title(c.title) or (c.domain or "unknown")


def _collect(seen: dict, title: str | None, url: str | None, snippet: str | None,
             *, source: str) -> None:
    """Gather a raw candidate (pre-qualification), deduped by domain."""
    if not (title and url):
        return
    domain = _domain_from_url(url)
    if _is_excluded(domain) or domain in seen:
        return
    seen[domain] = Candidate(title=title, url=url, domain=domain,
                             snippet=snippet, source=source)


def persist_candidates(
    db: Session,
    *,
    organization_id: uuid.UUID,
    icp: ICP,
    candidates: list[DiscoveredCompany],
) -> list[Company]:
    """Insert new companies, ignoring duplicates by (org, domain)."""
    out: list[Company] = []
    existing = {
        d for d, in db.execute(
            select(Company.domain).where(
                Company.organization_id == organization_id,
                Company.domain.in_([c.domain for c in candidates if c.domain]),
            )
        )
    }
    for c in candidates:
        if not c.domain or c.domain in existing:
            continue
        row = Company(
            organization_id=organization_id,
            project_id=icp.project_id,
            icp_id=icp.id,
            name=c.name,
            domain=c.domain,
            website=c.website,
            linkedin_url=c.linkedin_url,
            description=c.description,
            industry=c.industry,
            source=c.source,
            classification_status=c.classification_status,
            raw={"qualification_confidence": c.confidence,
                 "ai_verified": c.ai_verified},
        )
        db.add(row)
        out.append((row, c.signal))
    db.flush()  # assign company ids before attaching signals

    # Persist EXTRACTED buying signals as real Signal rows so scoring + the UI see the
    # intent (not just an in-memory artifact), and so a re-discovery tomorrow doesn't
    # start the company cold. Signal-source extraction already established the fact.
    from app.models.signal import Signal
    for row, signal in out:
        if not signal:
            continue
        db.add(Signal(
            organization_id=organization_id, company_id=row.id,
            kind=signal.get("type", "other"),
            label=(signal.get("detail") or signal.get("type", "signal"))[:200],
            description=signal.get("detail"),
            severity=0.6, confidence=0.7,
            source="discovery_extract", observed_at=func.now(),
            payload={"extracted": True, "type": signal.get("type")},
        ))
    db.commit()
    companies = [row for row, _ in out]
    for row in companies:
        db.refresh(row)
    return companies
