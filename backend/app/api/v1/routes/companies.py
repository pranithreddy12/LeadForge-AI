import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.company import Company
from app.models.icp import ICP
from app.models.tenant import Organization
from app.schemas.common import Page
from app.schemas.company import CompanyCreate, CompanyDiscoveryRequest, CompanyOut, CompanyUpdate
from app.services.discovery import discover_via_search, persist_candidates
from app.services.enrichment import enrich_company
from app.workers.discovery import discover_companies_task
from app.workers.enrichment import enrich_batch_task

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=Page[CompanyOut])
def list_companies(
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    q: str | None = Query(default=None),
    industry: str | None = None,
    country: str | None = None,
    pipeline_stage: str | None = None,
    icp_id: uuid.UUID | None = None,
    sort: str = "-created_at",
    page: int = 1, page_size: int = 25,
):
    stmt = select(Company).where(Company.organization_id == org.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Company.name.ilike(like), Company.domain.ilike(like)))
    if industry:
        stmt = stmt.where(Company.industry == industry)
    if country:
        stmt = stmt.where(Company.country == country)
    if pipeline_stage:
        stmt = stmt.where(Company.pipeline_stage == pipeline_stage)
    if icp_id:
        stmt = stmt.where(Company.icp_id == icp_id)

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    column = sort.lstrip("-")
    col = getattr(Company, column, Company.created_at)
    stmt = stmt.order_by(desc(col) if sort.startswith("-") else col)
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()

    return Page(items=rows, page=page, page_size=page_size, total=total,
                has_next=total > page * page_size)


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    row = Company(organization_id=org.id, source="manual",
                  **payload.model_dump(exclude_none=True))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: uuid.UUID, db: Session = Depends(get_db),
                org: Organization = Depends(current_org)):
    c = db.get(Company, company_id)
    if not c or c.organization_id != org.id:
        raise NotFound("Company")
    return c


@router.patch("/{company_id}", response_model=CompanyOut)
def patch_company(company_id: uuid.UUID, payload: CompanyUpdate,
                  db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    c = db.get(Company, company_id)
    if not c or c.organization_id != org.id:
        raise NotFound("Company")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: uuid.UUID, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    c = db.get(Company, company_id)
    if not c or c.organization_id != org.id:
        raise NotFound("Company")
    db.delete(c)
    db.commit()
    return None


@router.post("/discover", status_code=status.HTTP_202_ACCEPTED)
def discover(
    payload: CompanyDiscoveryRequest,
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    sync: bool = False,
):
    icp = db.get(ICP, payload.icp_id)
    if not icp or icp.project.organization_id != org.id:
        raise NotFound("ICP")

    if sync:
        candidates = discover_via_search(icp, limit=payload.limit,
                                         extra_keywords=payload.extra_keywords)
        rows = persist_candidates(db, organization_id=org.id, icp=icp,
                                  candidates=candidates)
        return {"created": len(rows), "ids": [str(r.id) for r in rows]}

    task = discover_companies_task.delay(
        str(org.id), str(icp.id), payload.limit, payload.extra_keywords or [],
    )
    return {"task_id": task.id, "status": "queued"}


@router.post("/{company_id}/enrich", response_model=CompanyOut)
def enrich_one(company_id: uuid.UUID, db: Session = Depends(get_db),
               org: Organization = Depends(current_org), sync: bool = True):
    """Enrich a single company. Sync by default so the UI gets fresh fields back."""
    c = db.get(Company, company_id)
    if not c or c.organization_id != org.id:
        raise NotFound("Company")
    if sync:
        enrich_company(db, c)
        db.refresh(c)
        return c
    enrich_batch_task.delay(str(org.id), [str(company_id)])
    return c


@router.post("/enrich-batch", status_code=status.HTTP_202_ACCEPTED)
def enrich_many(db: Session = Depends(get_db), org: Organization = Depends(current_org),
                limit: int = 25):
    task = enrich_batch_task.delay(str(org.id), None, limit)
    return {"task_id": task.id, "status": "queued"}
