from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.ai.outreach_engine import generate_outreach
from app.core.logging import get_logger
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.signal import Signal
from app.workers._base import task_session

log = get_logger("workers.outreach")


def _row(r):
    return {c.key: getattr(r, c.key) for c in r.__table__.columns} if r else None


@shared_task(name="app.workers.outreach.draft_outreach_for_company")
def draft_outreach_for_company(organization_id: str, company_id: str,
                               campaign_id: str | None = None,
                               channel: str = "email", tone: str = "concise") -> dict:
    with task_session() as db:
        company = db.get(Company, uuid.UUID(company_id))
        if not company or str(company.organization_id) != organization_id:
            return {"error": "company_not_found"}
        contact = db.execute(
            select(Contact).where(Contact.company_id == company.id, Contact.is_primary.is_(True))
        ).scalar_one_or_none() or db.execute(
            select(Contact).where(Contact.company_id == company.id)
            .order_by(Contact.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        icp = db.get(ICP, company.icp_id) if company.icp_id else None
        signals = db.execute(
            select(Signal).where(Signal.company_id == company.id).limit(15)
        ).scalars().all()

        raw = generate_outreach(
            company=_row(company),
            contact=_row(contact),
            icp=_row(icp),
            signals=[_row(s) for s in signals],
            channel=channel, tone=tone,
        )
        variants = raw.get("variants") or []
        if not variants:
            return {"created": 0}
        v = variants[0]
        msg = EmailMessage(
            organization_id=uuid.UUID(organization_id),
            campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
            company_id=company.id,
            contact_id=contact.id if contact else None,
            subject=v.get("subject") or f"About {company.name}",
            body=v.get("body") or "",
            channel=channel,
            status="draft",
        )
        db.add(msg)
        return {"created": 1, "subject": msg.subject}
