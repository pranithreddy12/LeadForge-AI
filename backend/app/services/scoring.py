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


def latest_score_ids_select(organization_id: uuid.UUID):
    """A SELECT of exactly ONE (latest) LeadScore id per company for an org.

    Uses Postgres DISTINCT ON with a deterministic tie-break (created_at DESC,
    id DESC) so a company with two scores sharing the same created_at yields
    exactly one row — avoiding the double-count a max(created_at) self-join has.
    """
    return (
        select(LeadScore.id)
        .distinct(LeadScore.company_id)
        .where(LeadScore.organization_id == organization_id)
        .order_by(LeadScore.company_id, LeadScore.created_at.desc(), LeadScore.id.desc())
    )


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

    # LOCAL-mode businesses are graded on the AI-receptionist fit (no online booking,
    # reachable, demand, complaint signals), NOT the B2B employee/funding model.
    from app.services.settings_resolver import settings_row
    _s = settings_row(db, organization_id)
    if _s is not None and _s.discovery_mode == "local":
        from app.services.local_scoring import score_local_fit
        # Score AGAINST the ICP: its target vertical (industries + keywords) and
        # geography (countries + Settings target_locations).
        icp_terms = list(icp.industries or []) + list(icp.keywords or [])
        icp_geos = list(icp.countries or []) + list(_s.target_locations or [])
        lf = score_local_fit(
            company_name=company.name, industry=company.industry,
            places=(company.raw or {}).get("places") or {},
            signal_kinds=[s.kind for s in signals],
            icp_terms=icp_terms, icp_geos=icp_geos,
            min_reviews=_s.min_reviews or 10)
        score = LeadScore(
            organization_id=organization_id, company_id=company.id, icp_id=icp.id,
            score=lf["score"], grade=lf["grade"], probability=lf["probability"],
            fit_score=lf["fit_score"], funding_score=0, hiring_score=0, growth_score=0,
            tech_match_score=0, email_score=0, activity_score=lf["pain_score"],
            reasoning=lf["reasoning"], pain_points=[], raw={"local_fit": True})
        db.add(score)
        db.commit()
        db.refresh(score)
        return score

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
