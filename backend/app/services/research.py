"""Account research orchestration (Phase 6).

Gathers every available source on an account and synthesizes a deep brief:
    firmographics + signals + contacts + tech stack + fresh web research
        -> research_engine.synthesize_research -> AccountResearch row

Reuses already-stored enrichment/signals (cheap) and does a small number of
fresh web searches (news + careers) for recency. Never fabricates: on provider
error, nothing is persisted and the caller gets the error surfaced.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.research_engine import synthesize_research
from app.core.logging import get_logger
from app.models.company import Company
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.research import AccountResearch
from app.models.signal import Signal
from app.services.search import serper_search, tavily_search

log = get_logger(__name__)


def _row(r) -> dict:
    return {c.key: getattr(r, c.key) for c in r.__table__.columns} if r else {}


def _safe_http_url(url: str | None) -> bool:
    """Only keep http(s) source URLs — never persist javascript:/data:/file: links
    from third-party search providers (defense in depth, the UI renders these)."""
    if not url:
        return False
    from urllib.parse import urlparse
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def _gather_web(company: Company) -> tuple[str, list[dict]]:
    """Fresh web research — recent news + hiring. Runs the two providers
    concurrently so the search phase is bounded by the slowest single call
    (not the sum), and validates every source URL scheme. Returns (text, sources)."""
    from concurrent.futures import ThreadPoolExecutor

    name = company.name
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_tav = pool.submit(tavily_search, f"{name} news 2026", max_results=4)
        f_ser = pool.submit(serper_search, f"{name} hiring OR launches OR funding",
                            max_results=4, kind="news")
        tav = f_tav.result()
        ser = f_ser.result()

    blocks: list[str] = []
    sources: list[dict] = []
    for hit in tav:
        blocks.append(f"NEWS: {hit.get('title')} — {(hit.get('content') or '')[:280]}")
        if _safe_http_url(hit.get("url")):
            sources.append({"title": hit.get("title"), "url": hit.get("url"), "kind": "news"})
    for hit in ser:
        blocks.append(f"NEWS: {hit.get('title')} — {(hit.get('snippet') or '')[:240]}")
        if _safe_http_url(hit.get("link")):
            sources.append({"title": hit.get("title"), "url": hit.get("link"), "kind": "news"})
    return "\n".join(blocks), sources


def research_company(db: Session, *, organization_id: uuid.UUID,
                     company_id: uuid.UUID) -> AccountResearch | None:
    """Run deep research on a company and persist the brief.

    Returns the new AccountResearch, or None when the AI provider is unavailable
    (nothing is fabricated/persisted in that case)."""
    company = db.get(Company, company_id)
    if not company or company.organization_id != organization_id:
        raise ValueError("company not found")

    icp = db.get(ICP, company.icp_id) if company.icp_id else None
    signals = db.execute(
        select(Signal).where(Signal.company_id == company.id).limit(25)
    ).scalars().all()
    contacts = db.execute(
        select(Contact).where(Contact.company_id == company.id).limit(15)
    ).scalars().all()

    seller_offering = ""
    if icp and icp.project is not None:
        seller_offering = icp.project.business_description or ""
        if icp.project.target_offering:
            seller_offering += f"\nOffering: {icp.project.target_offering}"

    web_text, sources = _gather_web(company)

    brief = synthesize_research(
        company=_row(company),
        icp=_row(icp) if icp else None,
        seller_offering=seller_offering,
        signals=[_row(s) for s in signals],
        contacts=[_row(c) for c in contacts],
        web_snippets=web_text,
    )

    # Reject provider-down AND partial/malformed briefs (no usable summary) — never
    # persist a hollow row. complete_json on the non-strict Gemini path can return
    # JSON missing required fields.
    if not brief or brief.get("_provider_error") or not brief.get("summary"):
        log.warning("research_unavailable_or_partial", company_id=str(company_id))
        return None

    def _conf(v) -> int:
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0

    row = AccountResearch(
        organization_id=organization_id,
        company_id=company.id,
        summary=brief.get("summary"),
        pain_points=brief.get("pain_points") or [],
        current_initiatives=brief.get("current_initiatives") or [],
        growth_signals=brief.get("growth_signals") or [],
        key_facts=brief.get("key_facts") or [],
        recommended_pitch=brief.get("recommended_pitch"),
        suggested_contact_title=brief.get("suggested_contact_title"),
        confidence=_conf(brief.get("confidence")),
        sources=sources,
        raw=brief,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_research(db: Session, company_id: uuid.UUID) -> AccountResearch | None:
    return db.execute(
        select(AccountResearch).where(AccountResearch.company_id == company_id)
        .order_by(AccountResearch.created_at.desc()).limit(1)
    ).scalar_one_or_none()
