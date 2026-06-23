from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    """Run Tavily + Serper and synthesize a deduped candidate list."""
    queries = build_queries(icp, extra_keywords)
    seen: dict[str, DiscoveredCompany] = {}

    for q in queries:
        for hit in tavily_search(q, max_results=10):
            _ingest(seen, hit.get("title"), hit.get("url"), hit.get("content"),
                    source="tavily")
        for hit in serper_search(q, max_results=10):
            _ingest(seen, hit.get("title"), hit.get("link"), hit.get("snippet"),
                    source="serper")
        if len(seen) >= limit * 2:
            break

    return list(seen.values())[:limit]


def _ingest(seen: dict, title: str | None, url: str | None, snippet: str | None,
            *, source: str) -> None:
    if not (title and url):
        return
    domain = _domain_from_url(url)
    if _is_excluded(domain):
        return
    if domain in seen:
        return
    seen[domain] = DiscoveredCompany(
        name=_normalize_name(title),
        domain=domain,
        website=f"https://{domain}",
        description=(snippet or "")[:1000] or None,
        linkedin_url=None,
        source=source,
    )


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
            source=c.source,
        )
        db.add(row)
        out.append(row)
    db.commit()
    for row in out:
        db.refresh(row)
    return out
