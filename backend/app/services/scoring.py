from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.opportunity_engine import analyze_opportunity
from app.ai.scoring_engine import ScoreInput, score_lead
from app.models.company import Company
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.scoring import LeadScore
from app.models.signal import Signal


def _row_as_dict(row) -> dict:
    if row is None:
        return {}
    return {c.key: getattr(row, c.key) for c in row.__table__.columns}


def score_company(db: Session, *, organization_id: uuid.UUID,
                  company_id: uuid.UUID, icp_id: uuid.UUID,
                  with_opportunity: bool = True) -> LeadScore:
    company = db.get(Company, company_id)
    icp = db.get(ICP, icp_id)
    if not company or not icp:
        raise ValueError("company or ICP not found")

    signals = db.execute(
        select(Signal).where(Signal.company_id == company.id)
    ).scalars().all()
    contacts = db.execute(
        select(Contact).where(Contact.company_id == company.id)
    ).scalars().all()

    result = score_lead(ScoreInput(
        icp=_row_as_dict(icp),
        company=_row_as_dict(company),
        signals=[_row_as_dict(s) for s in signals],
        contacts=[_row_as_dict(c) for c in contacts],
    ))

    opp = {}
    if with_opportunity:
        opp = analyze_opportunity(
            icp=_row_as_dict(icp),
            company=_row_as_dict(company),
            signals=[_row_as_dict(s) for s in signals],
            score=result,
        )

    score = LeadScore(
        organization_id=organization_id,
        company_id=company.id,
        icp_id=icp.id,
        score=result["score"],
        grade=result["grade"],
        probability=result["probability"],
        fit_score=result["fit_score"],
        funding_score=result["funding_score"],
        hiring_score=result["hiring_score"],
        growth_score=result["growth_score"],
        tech_match_score=result["tech_match_score"],
        email_score=result["email_score"],
        activity_score=result["activity_score"],
        reasoning=result["reasoning"],
        suggested_offer=opp.get("suggested_offer") if opp else None,
        suggested_contact_title=opp.get("suggested_contact_title") if opp else None,
        pain_points=opp.get("pain_points") or [],
        raw={**result.get("raw", {}), "opportunity": opp},
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def best_score_for_company(db: Session, company_id: uuid.UUID) -> LeadScore | None:
    return db.execute(
        select(LeadScore).where(LeadScore.company_id == company_id)
        .order_by(LeadScore.created_at.desc()).limit(1)
    ).scalar_one_or_none()
