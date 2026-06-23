from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.scoring import LeadScore
from app.models.tenant import Organization


def kpi_block(db: Session, organization_id: uuid.UUID) -> dict:
    """Compute the 5 main KPIs + their week-over-week delta."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    def count_companies(start: datetime, end: datetime) -> int:
        return db.execute(
            select(func.count(Company.id)).where(
                Company.organization_id == organization_id,
                Company.created_at >= start,
                Company.created_at < end,
            )
        ).scalar_one() or 0

    leads_this = count_companies(week_ago, now)
    leads_prev = count_companies(two_weeks_ago, week_ago) or 1

    qualified = db.execute(
        select(func.count(Company.id)).where(
            Company.organization_id == organization_id,
            Company.pipeline_stage.in_(["qualified", "contacted", "replied",
                                        "meeting", "proposal", "won"]),
        )
    ).scalar_one() or 0

    avg = db.execute(
        select(func.coalesce(func.avg(LeadScore.score), 0))
        .where(LeadScore.organization_id == organization_id)
    ).scalar_one() or 0

    won = db.execute(
        select(func.count(Company.id)).where(
            Company.organization_id == organization_id,
            Company.pipeline_stage == "won",
        )
    ).scalar_one() or 0
    total = db.execute(
        select(func.count(Company.id))
        .where(Company.organization_id == organization_id)
    ).scalar_one() or 1
    conv = round(100.0 * won / total, 1)

    # Pipeline value is derived from the real per-account revenue we discovered,
    # using a configurable win-rate × deal-size-as-%-of-revenue, NOT a flat
    # per-deal constant. Falls back to the org's configured ACV only when no
    # revenue data exists for the in-flight accounts.
    in_flight_revenue = db.execute(
        select(func.coalesce(func.sum(Company.revenue_usd), 0)).where(
            Company.organization_id == organization_id,
            Company.pipeline_stage.in_(["qualified", "contacted", "replied",
                                        "meeting", "proposal", "won"]),
        )
    ).scalar_one() or 0
    org = db.get(Organization, organization_id)
    deal_pct = float((org.settings or {}).get("deal_size_pct_of_revenue", 0.02)) if org else 0.02
    default_acv = int((org.settings or {}).get("default_acv_usd", 12_000)) if org else 12_000
    pipeline_value = int(in_flight_revenue * deal_pct) if in_flight_revenue else int(won) * default_acv

    return {
        "leads_found": {
            "label": "Leads found (7d)",
            "value": int(leads_this),
            "delta_pct": round(100.0 * (leads_this - leads_prev) / max(1, leads_prev), 1),
        },
        "qualified_leads": {
            "label": "Qualified leads",
            "value": int(qualified),
            "delta_pct": None,
        },
        "avg_score": {
            "label": "Avg lead score",
            "value": round(float(avg), 1),
            "delta_pct": None,
        },
        "conversion_rate": {
            "label": "Conversion rate",
            "value": conv,
            "delta_pct": None,
        },
        "revenue": {
            "label": "Pipeline (est)",
            "value": pipeline_value,
            "delta_pct": None,
        },
    }


def industry_breakdown(db: Session, organization_id: uuid.UUID, *, limit: int = 8):
    rows = db.execute(
        select(Company.industry, func.count(Company.id))
        .where(Company.organization_id == organization_id)
        .group_by(Company.industry).order_by(func.count(Company.id).desc())
        .limit(limit)
    ).all()
    return [{"industry": i or "Unknown", "count": int(c)} for i, c in rows]


def source_breakdown(db: Session, organization_id: uuid.UUID):
    rows = db.execute(
        select(Company.source, func.count(Company.id))
        .where(Company.organization_id == organization_id)
        .group_by(Company.source)
    ).all()
    return [{"source": s or "manual", "count": int(c)} for s, c in rows]


def score_trend(db: Session, organization_id: uuid.UUID, *, days: int = 30):
    sql = (
        select(
            func.date_trunc("day", LeadScore.created_at).label("d"),
            func.avg(LeadScore.score).label("avg"),
            func.count(LeadScore.id).label("n"),
        )
        .where(LeadScore.organization_id == organization_id)
        .where(LeadScore.created_at >= datetime.utcnow() - timedelta(days=days))
        .group_by("d")
        .order_by("d")
    )
    return [
        {"date": d.strftime("%Y-%m-%d"), "avg_score": float(a or 0), "count": int(n)}
        for d, a, n in db.execute(sql).all()
    ]
