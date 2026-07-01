"""Replies dashboard (Section 4B) — every replied lead with the original outreach,
their reply, an AI-suggested next response, and CRM stage controls."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org, current_user
from app.core.errors import NotFound
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.crm import CRMActivity
from app.models.tenant import Organization, User
from app.models.whatsapp import WhatsAppMessage
from app.schemas.crm import StageMove
from app.services.crm import move_stage
from app.services.whatsapp_inbound import _city_of, _latest_score

router = APIRouter(prefix="/replies", tags=["replies"])

# The reply funnel: a lead enters at 'replied' and moves through these stages.
REPLY_STAGES = ("replied", "in_conversation", "closed_won", "closed_lost")


def _latest_reply_activity(db: Session, company_id: uuid.UUID) -> CRMActivity | None:
    return db.execute(
        select(CRMActivity).where(
            CRMActivity.company_id == company_id,
            CRMActivity.kind.in_(("email", "whatsapp")),
        ).order_by(CRMActivity.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _original_message(db: Session, company_id: uuid.UUID, channel: str) -> str | None:
    if channel == "whatsapp":
        row = db.execute(
            select(WhatsAppMessage.message_body)
            .where(WhatsAppMessage.company_id == company_id)
            .order_by(WhatsAppMessage.sent_at.desc().nullslast()).limit(1)
        ).first()
        return row[0] if row else None
    row = db.execute(
        select(EmailMessage.body)
        .where(EmailMessage.company_id == company_id,
               EmailMessage.status.in_(("sent", "replied")))
        .order_by(EmailMessage.sent_at.desc().nullslast()).limit(1)
    ).first()
    return row[0] if row else None


@router.get("")
def list_replies(db: Session = Depends(get_db),
                 org: Organization = Depends(current_org)):
    """All replied leads (pipeline_stage in the reply funnel), newest reply first."""
    companies = db.execute(
        select(Company).where(
            Company.organization_id == org.id,
            Company.pipeline_stage.in_(REPLY_STAGES),
        )
    ).scalars().all()

    out = []
    for c in companies:
        act = _latest_reply_activity(db, c.id)
        payload = (act.payload or {}) if act else {}
        channel = payload.get("channel") or (act.kind if act else None) or "email"
        sc = _latest_score(db, c.id)
        score, grade = (int(sc[0]) if sc and sc[0] is not None else None,
                        sc[1] if sc else None)
        reply_text = payload.get("reply") or (act.body if act else None)
        out.append({
            "company_id": str(c.id),
            "company_name": c.name,
            "city": _city_of(c),
            "score": score,
            "grade": grade,
            "stage": c.pipeline_stage,
            "channel": channel,
            "original_message": _original_message(db, c.id, channel),
            "reply_text": reply_text,
            "reply_at": (act.created_at if act else None),
            "suggested_response": payload.get("suggested_response"),
        })
    # Newest reply first (None reply_at sinks to the bottom).
    out.sort(key=lambda r: (r["reply_at"] is not None, r["reply_at"]), reverse=True)
    return {"replies": out}


@router.post("/{company_id}/stage")
def set_reply_stage(company_id: uuid.UUID, payload: StageMove,
                    db: Session = Depends(get_db),
                    org: Organization = Depends(current_org),
                    user: User = Depends(current_user)):
    """Advance a replied lead through the reply funnel
    (replied -> in_conversation -> closed_won / closed_lost)."""
    if payload.stage not in REPLY_STAGES:
        from fastapi import HTTPException
        raise HTTPException(status_code=400,
                            detail=f"stage must be one of {REPLY_STAGES}")
    c = db.get(Company, company_id)
    if not c or c.organization_id != org.id:
        raise NotFound("Company")
    move_stage(db, c, payload.stage, user_id=user.id)
    return {"ok": True, "stage": payload.stage}
