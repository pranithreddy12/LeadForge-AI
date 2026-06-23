import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.company import Company
from app.models.contact import Contact
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
        stmt.order_by(Contact.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=total,
                has_next=total > page * page_size)


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    company = db.get(Company, payload.company_id)
    if not company or company.organization_id != org.id:
        raise NotFound("Company")
    row = Contact(organization_id=org.id, **payload.model_dump(exclude_none=True))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{contact_id}", response_model=ContactOut)
def patch_contact(contact_id: uuid.UUID, payload: ContactUpdate,
                  db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    row = db.get(Contact, contact_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Contact")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
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
