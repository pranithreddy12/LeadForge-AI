from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.scoring import LeadScore
from app.models.signal import Signal


def _latest_score_subquery(organization_id: uuid.UUID):
    """Subquery: the most recent LeadScore per company for this org."""
    return (
        select(
            LeadScore.company_id,
            func.max(LeadScore.created_at).label("max_created"),
        )
        .where(LeadScore.organization_id == organization_id)
        .group_by(LeadScore.company_id)
        .subquery()
    )


def list_opportunities(db: Session, *, organization_id: uuid.UUID,
                       min_score: int = 0, limit: int = 50, offset: int = 0) -> list[dict]:
    """Companies joined with their latest score + opportunity reasoning,
    ranked by score descending. This is the intelligence view."""
    latest = _latest_score_subquery(organization_id)

    rows = db.execute(
        select(Company, LeadScore)
        .join(latest, latest.c.company_id == Company.id)
        .join(
            LeadScore,
            (LeadScore.company_id == latest.c.company_id)
            & (LeadScore.created_at == latest.c.max_created),
        )
        .where(Company.organization_id == organization_id)
        .where(LeadScore.score >= min_score)
        .order_by(LeadScore.score.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    out: list[dict] = []
    for company, score in rows:
        # signal rollup
        sig_rows = db.execute(
            select(Signal.kind, func.count(Signal.id))
            .where(Signal.company_id == company.id)
            .group_by(Signal.kind)
            .order_by(func.count(Signal.id).desc())
        ).all()
        signal_count = sum(n for _, n in sig_rows)
        top_kinds = [k for k, _ in sig_rows[:4]]

        opp = (score.raw or {}).get("opportunity") or {}
        out.append({
            "company_id": company.id,
            "company_name": company.name,
            "domain": company.domain,
            "industry": company.industry,
            "pipeline_stage": company.pipeline_stage,
            "score": score.score,
            "grade": score.grade,
            "probability": score.probability,
            "why_now": opp.get("why_now") or score.reasoning or [],
            "pain_points": opp.get("pain_points") or score.pain_points or [],
            "suggested_contact_title": score.suggested_contact_title
                or opp.get("suggested_contact_title"),
            "suggested_offer": score.suggested_offer or opp.get("suggested_offer"),
            "signal_count": signal_count,
            "top_signal_kinds": top_kinds,
            "scored_at": score.created_at,
        })
    return out


def opportunity_stats(db: Session, *, organization_id: uuid.UUID) -> dict:
    latest = _latest_score_subquery(organization_id)
    rows = db.execute(
        select(LeadScore.grade, LeadScore.score)
        .join(latest, (LeadScore.company_id == latest.c.company_id)
              & (LeadScore.created_at == latest.c.max_created))
        .where(LeadScore.organization_id == organization_id)
    ).all()
    if not rows:
        return {"total_scored": 0, "hot": 0, "warm": 0, "cold": 0, "avg_score": 0.0}
    hot = sum(1 for g, _ in rows if g in ("A+", "A"))
    warm = sum(1 for g, _ in rows if g in ("B", "C"))
    cold = sum(1 for g, _ in rows if g in ("D", "F"))
    avg = round(sum(s for _, s in rows) / len(rows), 1)
    return {"total_scored": len(rows), "hot": hot, "warm": warm, "cold": cold, "avg_score": avg}
