"""Sent — every outreach message you've sent, newest first, for the /sent page.

Sourced from the manual outreach log (the one row-per-send record across email,
WhatsApp and Instagram), enriched with the email subject where there is one. The
frontend groups these by date.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.models.campaign import EmailMessage
from app.models.manual_outreach import ManualOutreachLog
from app.models.tenant import Organization

router = APIRouter(prefix="/sent", tags=["sent"])


@router.get("")
def list_sent(db: Session = Depends(get_db), org: Organization = Depends(current_org),
              limit: int = 500):
    """All 'sent' outreach actions, newest first. One row per send (email/WhatsApp/
    Instagram), with the email subject attached when the channel is email."""
    rows = db.execute(
        select(ManualOutreachLog).where(
            ManualOutreachLog.organization_id == org.id,
            ManualOutreachLog.action == "sent",
        ).order_by(ManualOutreachLog.created_at.desc()).limit(limit)
    ).scalars().all()

    # Attach the email subject for email sends (one lookup of the latest sent email
    # per company keeps this cheap without an N+1 per row).
    email_cids = [r.company_id for r in rows if r.company_id and r.channel == "email"]
    subj: dict[uuid.UUID, str] = {}
    if email_cids:
        for cid, s in db.execute(
            select(EmailMessage.company_id, EmailMessage.subject)
            .where(EmailMessage.company_id.in_(email_cids),
                   EmailMessage.status.in_(("sent", "replied")))
            .order_by(EmailMessage.created_at.desc())
        ):
            subj.setdefault(cid, s)

    items = [{
        "id": str(r.id),
        "company_id": str(r.company_id) if r.company_id else None,
        "company_name": r.company_name,
        "channel": r.channel,               # email | whatsapp | instagram
        "replied": r.replied,
        "subject": subj.get(r.company_id) if r.channel == "email" else None,
        "at": r.created_at,
    } for r in rows]
    return {"count": len(items),
            "replied": sum(1 for i in items if i["replied"]),
            "items": items}
