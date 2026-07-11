from __future__ import annotations

import re
import uuid
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.signal_engine import extract_signals_from_text, signal_kinds_for_hiring
from app.core.logging import get_logger
from app.models.company import Company
from app.models.signal import Signal
from app.services.scraper import fetch_static
from app.services.search import serper_search, tavily_search
from app.services.serp_filter import registrable_domain

log = get_logger(__name__)

# Business suffixes stripped before an exact company-name match.
_BIZ_SUFFIX = re.compile(
    r"\b(inc|llc|l\.l\.c|ltd|corp|co|pc|p\.c|pllc|dds|dmd|md|group|clinic|"
    r"dental|dentistry|associates|partners|company|gmbh|plc)\.?\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _name_core(name: str) -> str:
    """Distinctive core of a company name (suffixes removed, normalized)."""
    core = _BIZ_SUFFIX.sub(" ", name or "")
    return re.sub(r"\s+", " ", _norm(core)).strip()


def _domain_match(company: Company, url: str | None) -> bool:
    comp = registrable_domain(company.domain or "")
    if not (comp and url):
        return False
    try:
        sig = registrable_domain(urlparse(url).netloc)
    except Exception:
        return False
    return bool(sig) and sig == comp


def _name_in(company: Company, text: str | None) -> bool:
    core = _name_core(company.name or "")
    return bool(core) and len(core) >= 4 and core in _norm(text or "")


def source_about_company(company: Company, *, title: str | None = None,
                         snippet: str | None = None, url: str | None = None) -> bool:
    """DETECTION-time check on the ORIGINAL article (title+snippet+url), before the LLM
    ever sees it. Domain match OR the company name appears in the real article text."""
    return _domain_match(company, url) or _name_in(company, f"{title or ''} {snippet or ''}")


def signal_attribution_ok(company: Company, *, url: str | None,
                          label: str | None = None, description: str | None = None) -> bool:
    """HARD guard used at persist + prune. Attribution is judged ONLY on the SOURCE
    (url/domain), NEVER the LLM-written description — because the extractor is handed the
    company name and dutifully writes it into every description ("...practices like X"),
    which would defeat a name match. So: the source URL is on the company's own domain,
    OR the company's name is literally in the URL. Third-party news about a *different*
    entity has neither and is dropped."""
    if _domain_match(company, url):
        return True
    core = _name_core(company.name or "")
    if core and len(core) >= 4 and url:
        if core.replace(" ", "") in _norm(url).replace(" ", ""):
            return True
    return False

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
    # Attribution pre-filter: only keep articles actually about THIS company (domain or
    # name in the real title/snippet) before the LLM extracts — no misattribution.
    news_results = [n for n in news_results if source_about_company(
        company, title=n.get("title"), snippet=n.get("snippet"), url=n.get("link"))]
    news_text = "\n\n".join(
        f"{n.get('title')}\n{n.get('snippet')}\nURL: {n.get('link')}\nDate: {n.get('date', '')}"
        for n in news_results
    )
    if news_text:
        for s in extract_signals_from_text(
            company_name=name, source="news", text=news_text
        ):
            # setdefault, NOT assignment: a demo fixture already carries
            # source="demo" — never relabel it as a real provider source.
            s.setdefault("source", "news")
            found.append(s)

    tav = tavily_search(f"{name} product launch OR hiring OR funding 2026", max_results=5)
    tav = [t for t in tav if source_about_company(
        company, title=t.get("title"), snippet=t.get("content"), url=t.get("url"))]
    tav_text = "\n\n".join(
        f"{t.get('title')}\n{t.get('content')[:500]}\nURL: {t.get('url')}"
        for t in tav
    )
    if tav_text:
        for s in extract_signals_from_text(
            company_name=name, source="tavily", text=tav_text
        ):
            s.setdefault("source", "tavily")
            found.append(s)

    # ---- 3. Careers page tech_install / growth ------------------------------
    for url in _candidate_career_urls(company.domain or "")[:2]:
        page = fetch_static(url)
        if not page:
            continue
        for s in extract_signals_from_text(
            company_name=name, source="careers", text=page, url=url
        ):
            s.setdefault("source", "careers")
            found.append(s)

    return _persist_signals(db, company, found)


def _coerce_observed_at(val):
    """LLM/SERP dates come in messy ('2026-06', '2026', 'June 2026', full ISO). The
    column is TIMESTAMPTZ, so a partial like '2026-06' crashes the insert. Coerce to a
    real datetime (partials -> first of month/year), else None — never raise."""
    import re
    from datetime import datetime
    if not val or not isinstance(val, str):
        return val if not isinstance(val, str) else None
    s = val.strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{2})$", s)      # 2026-06 -> 2026-06-01
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), 1)
        except ValueError:
            return None
    if re.match(r"^\d{4}$", s):                # 2026 -> 2026-01-01
        return datetime(int(s), 1, 1)
    for fmt in ("%B %Y", "%b %Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _persist_signals(db: Session, company: Company, found: list[dict]) -> list[Signal]:
    if not found:
        return []
    # ATTRIBUTION GUARD: a signal may only be kept if its source is actually about THIS
    # company (domain or exact-name match). Drops competitor-funding / unrelated-school
    # articles that the news search swept in. This is the fix for misattributed signals.
    kept = []
    for s in found:
        if signal_attribution_ok(company, url=s.get("url"), label=s.get("label"),
                                 description=s.get("description")):
            kept.append(s)
        else:
            log.info("signal_dropped_misattributed", company=company.name,
                     label=(s.get("label") or "")[:80], url=s.get("url"))
    found = kept
    if not found:
        return []
    # Defense in depth: if a REAL LLM provider is configured, never persist a
    # demo-sourced signal. Demo signals only legitimately exist in zero-key mode.
    from app.ai.openai_client import current_provider
    if current_provider() != "demo":
        found = [s for s in found if s.get("source") != "demo"]
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
            observed_at=_coerce_observed_at(s.get("observed_at")),
            payload=s.get("payload") or {},
        )
        db.add(row)
        out.append(row)
    db.commit()
    for row in out:
        db.refresh(row)
    return out


def prune_misattributed_signals(db: Session, organization_id: uuid.UUID) -> dict:
    """One-time cleanup: re-validate every existing signal against its company and
    delete the ones that fail attribution (source not about that company). Local
    review signals (google_reviews) + discovery-extract are inherently self-attributed
    and are left alone."""
    rows = db.execute(
        select(Signal, Company).join(Company, Company.id == Signal.company_id)
        .where(Signal.organization_id == organization_id)
    ).all()
    dropped = kept = 0
    for sig, company in rows:
        if (sig.source or "") in ("google_reviews", "discovery_extract", "seed",
                                  "website_scan"):
            kept += 1
            continue
        if signal_attribution_ok(company, url=sig.url, label=sig.label,
                                 description=sig.description):
            kept += 1
        else:
            db.delete(sig)
            dropped += 1
    db.commit()
    log.info("prune_misattributed_signals", dropped=dropped, kept=kept)
    return {"dropped": dropped, "kept": kept}


def list_signals(db: Session, *, company_id: uuid.UUID, limit: int = 50) -> list[Signal]:
    return db.execute(
        select(Signal).where(Signal.company_id == company_id)
        .order_by(Signal.created_at.desc()).limit(limit)
    ).scalars().all()
