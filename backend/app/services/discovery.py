from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
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
    """Synthesize 4-8 queries from an ICP."""
    kws = list(icp.keywords or [])[:8]
    if extra_keywords:
        kws.extend(extra_keywords)
    countries = (icp.countries or [])[:2] or [""]
    industries = (icp.industries or [])[:3] or [""]

    queries: list[str] = []
    for ind in industries:
        for country in countries:
            for kw in kws[:3]:
                q = f"{ind} companies {kw} {country}".strip()
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

    for q in queries:
        for hit in tavily_search(q, max_results=10):
            src = "demo" if hit.get("demo") else "tavily"
            _collect(raw, hit.get("title"), hit.get("url"), hit.get("content"), source=src)
        for hit in serper_search(q, max_results=10):
            src = "demo" if hit.get("demo") else "serper"
            _collect(raw, hit.get("title"), hit.get("link"), hit.get("snippet"), source=src)
        # collect a bit more than `limit` so qualification has room to reject.
        if len(raw) >= limit * 4:
            break

    candidates = list(raw.values())
    accepted, stats = qualify_candidates(candidates)
    log.info("discovery_qualified", **stats)

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
        ))
    return out


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
            raw={"qualification_confidence": c.confidence,
                 "ai_verified": c.ai_verified},
        )
        db.add(row)
        out.append(row)
    db.commit()
    for row in out:
        db.refresh(row)
    return out
