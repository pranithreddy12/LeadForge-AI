"""Enrichment orchestration (Phase 2).

Pipeline for one company:
    website scrape  ─┐
    funding search   ├─→ LLM extract ─→ merge ─→ persist (+ tech_install signals)
    raw-html tech ───┘  (deterministic)

Guarantees:
- Never fabricates: if the LLM provider is unavailable, we still persist the
  deterministic tech-stack (real) and leave firmographic fields untouched.
- Idempotent: safe to re-run; only fills/overwrites with non-null values.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.enrichment_engine import (
    employee_range_for,
    extract_profile,
    revenue_range_for,
)
from app.core.logging import get_logger
from app.models.company import Company
from app.models.signal import Signal
from app.services.scraper import fetch_raw_html, fetch_static
from app.services.search import serper_search, tavily_search
from app.services.techstack import detect_tech, product_names, tech_to_signals

log = get_logger(__name__)


def _gather_website_text(company: Company) -> str:
    if not company.domain:
        return ""
    parts: list[str] = []
    for path in ("", "/about", "/about-us", "/company"):
        url = f"https://{company.domain}{path}"
        text = fetch_static(url)
        if text:
            parts.append(f"[{url}]\n{text}")
        if sum(len(p) for p in parts) > 14000:
            break
    return "\n\n".join(parts)


def _gather_search_snippets(company: Company) -> str:
    name = company.name
    queries = [
        f"{name} number of employees headquarters",
        f"{name} funding round raised valuation",
    ]
    blocks: list[str] = []
    for q in queries:
        for hit in tavily_search(q, max_results=3):
            blocks.append(f"{hit.get('title')}: {hit.get('content', '')[:300]}")
        for hit in serper_search(q, max_results=3):
            blocks.append(f"{hit.get('title')}: {hit.get('snippet', '')[:300]}")
    return "\n".join(blocks)


def enrich_company(db: Session, company: Company) -> dict:
    """Enrich a single company in place. Returns a summary of what changed."""
    summary = {"tech": 0, "fields_set": 0, "signals": 0, "provider_error": False,
               "llm_skipped": False}

    # --- 1. Deterministic tech-stack (always real, no LLM) -------------------
    tech: list[dict] = []
    if company.domain:
        raw = fetch_raw_html(f"https://{company.domain}")
        tech = detect_tech(raw)
        if tech:
            existing = set(company.tech_stack or [])
            merged = sorted(existing | set(product_names(tech)))
            company.tech_stack = merged
            summary["tech"] = len(tech)
            # persist tech_install signals (deduped by label)
            sig_summary = _persist_tech_signals(db, company, tech_to_signals(tech))
            summary["signals"] = sig_summary

    # --- 2. LLM firmographic extraction -------------------------------------
    website_text = _gather_website_text(company)
    search_snippets = _gather_search_snippets(company)
    profile = extract_profile(
        company_name=company.name, domain=company.domain,
        website_text=website_text, search_snippets=search_snippets,
    )

    if profile.get("_provider_error"):
        summary["provider_error"] = True
    elif not profile:
        summary["llm_skipped"] = True
    else:
        summary["fields_set"] = _apply_profile(company, profile)

    # mark enriched only if we actually got firmographic data OR tech.
    if summary["fields_set"] or summary["tech"]:
        company.enriched = True
        from sqlalchemy import func
        company.last_enriched_at = func.now()
        # request a fresh embedding next cycle since the corpus changed
        company.embedding_pending = True

    db.add(company)
    db.commit()
    db.refresh(company)
    log.info("enriched_company", company_id=str(company.id), **summary)
    return summary


def _apply_profile(company: Company, p: dict) -> int:
    """Fill non-null fields only. Returns count of fields set."""
    n = 0

    def setif(attr: str, value, *, overwrite_empty_only: bool = True):
        nonlocal n
        if value in (None, "", []):
            return
        cur = getattr(company, attr, None)
        if overwrite_empty_only and cur not in (None, "", [], 0):
            return
        setattr(company, attr, value)
        n += 1

    setif("description", p.get("description"))
    setif("industry", p.get("industry"))
    if p.get("sub_industries"):
        company.sub_industries = p["sub_industries"]; n += 1
    if p.get("employee_count"):
        company.employee_count = p["employee_count"]
        company.employee_range = p.get("employee_range") or employee_range_for(p["employee_count"])
        n += 1
    if p.get("revenue_usd"):
        company.revenue_usd = p["revenue_usd"]
        company.revenue_range = p.get("revenue_range") or revenue_range_for(p["revenue_usd"])
        n += 1
    setif("country", p.get("country"))
    setif("city", p.get("city"))
    setif("region", p.get("region"))
    setif("founded_year", p.get("founded_year"))
    setif("linkedin_url", p.get("linkedin_url"))

    # funding data lives in raw (no dedicated columns) — keep it queryable.
    funding = {
        "funding_total_usd": p.get("funding_total_usd"),
        "last_funding_stage": p.get("last_funding_stage"),
    }
    if any(funding.values()):
        company.raw = {**(company.raw or {}), "funding": funding,
                       "enrichment_confidence": p.get("confidence")}
        n += 1
    return n


def _persist_tech_signals(db: Session, company: Company, signals: list[dict]) -> int:
    if not signals:
        return 0
    existing = {
        (k, (l or "").lower()) for k, l in db.execute(
            select(Signal.kind, Signal.label).where(Signal.company_id == company.id)
        ).all()
    }
    added = 0
    for s in signals:
        key = (s["kind"], s["label"].lower())
        if key in existing:
            continue
        db.add(Signal(
            organization_id=company.organization_id,
            company_id=company.id,
            kind=s["kind"],
            label=s["label"][:200],
            description=s.get("description"),
            severity=s.get("severity", 0.5),
            confidence=s.get("confidence", 0.8),
            source=s.get("source", "techstack"),
        ))
        existing.add(key)
        added += 1
    return added


def enrich_batch(db: Session, *, organization_id: uuid.UUID,
                 company_ids: list[uuid.UUID] | None = None, limit: int = 25) -> dict:
    """Enrich many companies (unenriched first)."""
    stmt = select(Company).where(Company.organization_id == organization_id)
    if company_ids:
        stmt = stmt.where(Company.id.in_(company_ids))
    else:
        stmt = stmt.where(Company.enriched.is_(False))
    companies = db.execute(stmt.limit(limit)).scalars().all()
    totals = {"companies": 0, "tech": 0, "fields_set": 0, "signals": 0}
    for c in companies:
        s = enrich_company(db, c)
        totals["companies"] += 1
        totals["tech"] += s["tech"]
        totals["fields_set"] += s["fields_set"]
        totals["signals"] += s["signals"] if isinstance(s["signals"], int) else 0
    return totals
