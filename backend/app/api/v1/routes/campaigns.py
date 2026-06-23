import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.outreach_engine import generate_outreach
from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.campaign import Campaign, EmailMessage
from app.models.company import Company
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.signal import Signal
from app.models.tenant import Organization
from app.schemas.campaign import (
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    EmailMessageOut,
    OutreachGenerateRequest,
    OutreachResponse,
    OutreachVariant,
)
from app.schemas.common import Page

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=Page[CampaignOut])
def list_campaigns(db: Session = Depends(get_db),
                   org: Organization = Depends(current_org),
                   page: int = 1, page_size: int = 25):
    rows = db.execute(
        select(Campaign).where(Campaign.organization_id == org.id)
        .order_by(Campaign.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    total = db.execute(
        select(Campaign.id).where(Campaign.organization_id == org.id)
    ).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=len(total),
                has_next=len(total) > page * page_size)


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db),
                    org: Organization = Depends(current_org)):
    row = Campaign(organization_id=org.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{campaign_id}", response_model=CampaignOut)
def patch_campaign(campaign_id: uuid.UUID, payload: CampaignUpdate,
                   db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    row = db.get(Campaign, campaign_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Campaign")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.post("/outreach", response_model=OutreachResponse)
def generate(payload: OutreachGenerateRequest,
             db: Session = Depends(get_db),
             org: Organization = Depends(current_org)):
    company = db.get(Company, payload.company_id)
    if not company or company.organization_id != org.id:
        raise NotFound("Company")
    contact = db.get(Contact, payload.contact_id) if payload.contact_id else None
    icp = db.get(ICP, company.icp_id) if company.icp_id else None
    signals = db.execute(
        select(Signal).where(Signal.company_id == company.id).limit(15)
    ).scalars().all()

    def _row(r):
        return {c.key: getattr(r, c.key) for c in r.__table__.columns} if r else None

    raw = generate_outreach(
        company=_row(company),
        contact=_row(contact),
        icp=_row(icp),
        signals=[_row(s) for s in signals],
        channel=payload.channel,
        tone=payload.tone,
        follow_up=payload.follow_up,
    )
    variants = [OutreachVariant(**v) for v in raw.get("variants", [])]
    return OutreachResponse(company_id=company.id,
                            contact_id=contact.id if contact else None,
                            variants=variants)


@router.get("/{campaign_id}/messages", response_model=list[EmailMessageOut])
def list_messages(campaign_id: uuid.UUID, db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    cam = db.get(Campaign, campaign_id)
    if not cam or cam.organization_id != org.id:
        raise NotFound("Campaign")
    return db.execute(
        select(EmailMessage).where(EmailMessage.campaign_id == campaign_id)
        .order_by(EmailMessage.created_at.desc())
    ).scalars().all()
