import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.opportunity_engine import analyze_opportunity
from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.company import Company
from app.models.icp import ICP
from app.models.scoring import LeadScore
from app.models.signal import Signal
from app.models.tenant import Organization
from app.schemas.scoring import LeadScoreOut, OpportunityAnalysis, ScoreRequest
from app.services.scoring import best_score_for_company, score_company
from app.workers.scoring import score_batch_task

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/score/{company_id}/{icp_id}", response_model=LeadScoreOut)
def score_one(
    company_id: uuid.UUID,
    icp_id: uuid.UUID,
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
):
    return score_company(db, organization_id=org.id, company_id=company_id, icp_id=icp_id)


@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
def score_batch(payload: ScoreRequest, db: Session = Depends(get_db),
                org: Organization = Depends(current_org)):
    icp = db.get(ICP, payload.icp_id)
    if not icp or icp.project.organization_id != org.id:
        raise NotFound("ICP")
    ids = [str(i) for i in (payload.company_ids or [])]
    task = score_batch_task.delay(str(org.id), str(icp.id), ids)
    return {"task_id": task.id, "status": "queued"}


@router.get("/company/{company_id}", response_model=LeadScoreOut)
def latest_score(company_id: uuid.UUID, db: Session = Depends(get_db),
                 org: Organization = Depends(current_org)):
    row = best_score_for_company(db, company_id)
    if not row or row.organization_id != org.id:
        raise NotFound("LeadScore")
    return row


@router.post("/opportunity/{company_id}/{icp_id}", response_model=OpportunityAnalysis)
def opportunity(company_id: uuid.UUID, icp_id: uuid.UUID,
                db: Session = Depends(get_db),
                org: Organization = Depends(current_org)):
    company = db.get(Company, company_id)
    icp = db.get(ICP, icp_id)
    if not company or not icp or company.organization_id != org.id:
        raise NotFound("Company")
    signals = db.execute(
        select(Signal).where(Signal.company_id == company.id)
    ).scalars().all()
    raw = analyze_opportunity(
        icp={c.key: getattr(icp, c.key) for c in icp.__table__.columns},
        company={c.key: getattr(company, c.key) for c in company.__table__.columns},
        signals=[{c.key: getattr(s, c.key) for c in s.__table__.columns} for s in signals],
    )
    if raw.get("_provider_error") or "probability" not in raw:
        from app.core.errors import AIUnavailable
        raise AIUnavailable()
    raw.pop("_provider_error", None)
    return OpportunityAnalysis(company_id=company.id, **raw)
