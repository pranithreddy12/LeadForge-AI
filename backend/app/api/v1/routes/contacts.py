import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.company import Company
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.tenant import Organization
from app.schemas.common import Page
from app.schemas.contact import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    EmailValidationRequest,
    EmailValidationResult,
)
from app.services.contacts import (
    discover_contacts_for_company,
    validate_and_store,
)
from app.services.email_validation import validate_email

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=Page[ContactOut])
def list_contacts(
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    company_id: uuid.UUID | None = None,
    page: int = 1, page_size: int = 50,
):
    stmt = select(Contact).where(Contact.organization_id == org.id)
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Contact.influence_score.desc(), Contact.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=total,
                has_next=total > page * page_size)


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    from app.services.contact_intelligence import compute_influence
    from app.services.contacts import _department_for, _seniority_for
    company = db.get(Company, payload.company_id)
    if not company or company.organization_id != org.id:
        raise NotFound("Company")
    data = payload.model_dump(exclude_none=True)
    row = Contact(organization_id=org.id, **data)
    # Derive seniority/department from the title when not supplied, so influence
    # reflects the role (a manually-added CFO must score like a CFO).
    if not row.seniority and row.title:
        row.seniority = _seniority_for(row.title)
    if not row.department and row.title:
        row.department = _department_for(row.title)
    personas: list[str] = []
    if company.icp_id:
        icp = db.get(ICP, company.icp_id)
        personas = (icp.buyer_personas or []) if icp else []
    row.influence_score, row.buying_power = compute_influence(
        title=row.title, seniority=row.seniority, department=row.department,
        buyer_personas=personas,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{contact_id}", response_model=ContactOut)
def patch_contact(contact_id: uuid.UUID, payload: ContactUpdate,
                  db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    from app.services.contact_intelligence import compute_influence
    from app.services.contacts import _department_for, _seniority_for
    row = db.get(Contact, contact_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Contact")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    # A title/seniority/department edit changes the role — recompute influence so
    # ranking stays correct (otherwise a promoted contact keeps a stale score).
    if {"title", "seniority", "department"} & data.keys():
        if row.title:
            row.seniority = data.get("seniority") or _seniority_for(row.title)
            row.department = data.get("department") or _department_for(row.title)
        personas: list[str] = []
        company = db.get(Company, row.company_id)
        if company and company.icp_id:
            icp = db.get(ICP, company.icp_id)
            personas = (icp.buyer_personas or []) if icp else []
        row.influence_score, row.buying_power = compute_influence(
            title=row.title, seniority=row.seniority, department=row.department,
            buyer_personas=personas,
        )
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: uuid.UUID, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    row = db.get(Contact, contact_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Contact")
    db.delete(row)
    db.commit()
    return None


@router.post("/discover/{company_id}", response_model=list[ContactOut])
def discover(company_id: uuid.UUID, db: Session = Depends(get_db),
             org: Organization = Depends(current_org)):
    company = db.get(Company, company_id)
    if not company or company.organization_id != org.id:
        raise NotFound("Company")
    return discover_contacts_for_company(db, company)


@router.post("/{contact_id}/validate-email", response_model=ContactOut)
def validate_contact_email(contact_id: uuid.UUID, db: Session = Depends(get_db),
                           org: Organization = Depends(current_org)):
    row = db.get(Contact, contact_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Contact")
    return validate_and_store(db, contact_id)


@router.post("/validate-email", response_model=EmailValidationResult)
def validate_arbitrary(payload: EmailValidationRequest,
                       org: Organization = Depends(current_org)):
    r = validate_email(str(payload.email))
    return EmailValidationResult(email=r.email, status=r.status,
                                 confidence=r.confidence, provider=r.provider)


@router.post("/recompute-influence", status_code=200)
def recompute_influence(db: Session = Depends(get_db),
                        org: Organization = Depends(current_org),
                        company_id: uuid.UUID | None = None):
    """Backfill/refresh influence_score + buying_power for existing contacts
    (deterministic, no AI — safe to run anytime)."""
    from app.core.rate_limit import hit
    from app.services.contact_intelligence import compute_influence
    from app.services.contacts import _department_for, _seniority_for

    hit(f"recompute_influence:{org.id}", limit=6, window_seconds=60)

    stmt = select(Contact).where(Contact.organization_id == org.id)
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    # Bound the work — this is a synchronous full-scan write.
    rows = db.execute(stmt.limit(5000)).scalars().all()

    # Build company_id -> personas in TWO queries (no N+1 inside the loop).
    company_ids = {c.company_id for c in rows}
    co_to_icp = dict(db.execute(
        select(Company.id, Company.icp_id).where(Company.id.in_(company_ids))
    ).all()) if company_ids else {}
    icp_ids = {i for i in co_to_icp.values() if i}
    icp_personas = dict(db.execute(
        select(ICP.id, ICP.buyer_personas).where(ICP.id.in_(icp_ids))
    ).all()) if icp_ids else {}

    n = 0
    for c in rows:
        if not c.seniority and c.title:
            c.seniority = _seniority_for(c.title)
        if not c.department and c.title:
            c.department = _department_for(c.title)
        personas = icp_personas.get(co_to_icp.get(c.company_id)) or []
        c.influence_score, c.buying_power = compute_influence(
            title=c.title, seniority=c.seniority, department=c.department,
            buyer_personas=personas,
        )
        n += 1
    db.commit()
    return {"updated": n}
