from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.signal_engine import extract_signals_from_text, signal_kinds_for_hiring
from app.core.logging import get_logger
from app.models.company import Company
from app.models.signal import Signal
from app.services.scraper import fetch_static
from app.services.search import serper_search, tavily_search

log = get_logger(__name__)

# Heuristic source URLs we try per company.
def _candidate_career_urls(domain: str) -> list[str]:
    if not domain:
        return []
    base = f"https://{domain}"
    return [
        f"{base}/careers",
        f"{base}/jobs",
        f"{base}/work-with-us",
        f"{base}/about",
    ]


def detect_for_company(db: Session, company: Company, icp_keywords: list[str]) -> list[Signal]:
    """Run the full signal sweep for one company. Returns persisted signals."""
    found: list[dict] = []

    # ---- 1. Hiring (Serper /jobs) -------------------------------------------
    if company.domain:
        jobs = serper_search(f"site:{company.domain} jobs", max_results=10, kind="jobs")
        for j in jobs[:8]:
            found.append({
                "kind": "hiring",
                "label": f"Hiring: {j.get('title', 'Open role')}",
                "description": j.get("description", "Open role detected.")[:400],
                "severity": 0.7,
                "confidence": 0.8,
                "url": j.get("link") or j.get("url"),
                "observed_at": j.get("date"),
                "source": "serper",
            })
        found.extend({**s, "source": "serper"}
                     for s in signal_kinds_for_hiring(jobs, icp_keywords))

    # ---- 2. Funding / news (Serper News + Tavily) ---------------------------
    name = company.name
    news_results = serper_search(f"{name} funding OR raises OR Series", max_results=5, kind="news")
    news_text = "\n\n".join(
        f"{n.get('title')}\n{n.get('snippet')}\nURL: {n.get('link')}\nDate: {n.get('date', '')}"
        for n in news_results
    )
    if news_text:
        for s in extract_signals_from_text(
            company_name=name, source="news", text=news_text
        ):
            s["source"] = "news"
            found.append(s)

    tav = tavily_search(f"{name} product launch OR hiring OR funding 2026", max_results=5)
    tav_text = "\n\n".join(
        f"{t.get('title')}\n{t.get('content')[:500]}\nURL: {t.get('url')}"
        for t in tav
    )
    if tav_text:
        for s in extract_signals_from_text(
            company_name=name, source="tavily", text=tav_text
        ):
            s["source"] = "tavily"
            found.append(s)

    # ---- 3. Careers page tech_install / growth ------------------------------
    for url in _candidate_career_urls(company.domain or "")[:2]:
        page = fetch_static(url)
        if not page:
            continue
        for s in extract_signals_from_text(
            company_name=name, source="careers", text=page, url=url
        ):
            s["source"] = "careers"
            found.append(s)

    return _persist_signals(db, company, found)


def _persist_signals(db: Session, company: Company, found: list[dict]) -> list[Signal]:
    if not found:
        return []
    # Dedupe within this batch by (kind, label).
    seen: dict[tuple[str, str], dict] = {}
    for s in found:
        key = (s["kind"], s["label"][:120].lower())
        if key not in seen:
            seen[key] = s

    # Skip ones we already have for the company with same key.
    existing = db.execute(
        select(Signal.kind, Signal.label).where(Signal.company_id == company.id)
    ).all()
    existing_keys = {(k, (l or "")[:120].lower()) for k, l in existing}

    out: list[Signal] = []
    for (k, _), s in seen.items():
        if (k, s["label"][:120].lower()) in existing_keys:
            continue
        row = Signal(
            organization_id=company.organization_id,
            company_id=company.id,
            kind=s["kind"],
            label=s["label"][:200],
            description=s.get("description"),
            severity=float(s.get("severity") or 0.5),
            confidence=float(s.get("confidence") or 0.7),
            url=s.get("url"),
            source=s.get("source"),
            observed_at=s.get("observed_at"),
            payload=s.get("payload") or {},
        )
        db.add(row)
        out.append(row)
    db.commit()
    for row in out:
        db.refresh(row)
    return out


def list_signals(db: Session, *, company_id: uuid.UUID, limit: int = 50) -> list[Signal]:
    return db.execute(
        select(Signal).where(Signal.company_id == company_id)
        .order_by(Signal.created_at.desc()).limit(limit)
    ).scalars().all()
