"""Manual-send sprint (Today's Leads) — review drafted leads, copy + send yourself,
mark sent / skip, and track the 7-day funnel. Drafts accumulate when
Settings.outreach_send_mode == 'manual' (the workflow drafts but never sends)."""
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.contact import Contact
from app.models.manual_outreach import ManualOutreachLog
from app.models.scoring import LeadScore
from app.models.signal import Signal
from app.models.tenant import Organization
from app.models.workflow import Workflow
from app.services.settings_resolver import outreach_send_mode

router = APIRouter(prefix="/today", tags=["today"])


class SkipBody(BaseModel):
    reason: str = "other"   # bad_fit | no_contact | looks_wrong | other


class LogUpdate(BaseModel):
    replied: bool | None = None
    notes: str | None = None


def _top_signal(db: Session, company_id) -> str | None:
    r = db.execute(
        select(Signal.label, Signal.kind).where(Signal.company_id == company_id)
        .order_by(Signal.severity.desc().nullslast()).limit(1)
    ).first()
    return (r[0] or r[1]) if r else None


def _latest_score(db: Session, company_id):
    return db.execute(
        select(LeadScore.score, LeadScore.grade).where(LeadScore.company_id == company_id)
        .order_by(LeadScore.created_at.desc()).limit(1)
    ).first()


def _recipient(db: Session, m: EmailMessage) -> str | None:
    if m.contact_id:
        c = db.get(Contact, m.contact_id)
        if c and c.email:
            return c.email
    return (m.meta or {}).get("to")


@router.get("")
def todays_leads(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """All drafted leads awaiting manual review/send (status='draft'), best score first."""
    drafts = db.execute(
        select(EmailMessage).where(
            EmailMessage.organization_id == org.id,
            EmailMessage.status == "draft",
            EmailMessage.channel == "email",
        )
    ).scalars().all()

    leads = []
    for m in drafts:
        co = db.get(Company, m.company_id) if m.company_id else None
        if co is None:
            continue
        sc = _latest_score(db, co.id)
        score, grade = (int(sc[0]) if sc and sc[0] is not None else None,
                        sc[1] if sc else None)
        leads.append({
            "draft_id": str(m.id),
            "company_id": str(co.id),
            "company_name": co.name,
            "domain": co.domain,
            "score": score,
            "grade": grade,
            "signal": _top_signal(db, co.id),
            "subject": m.subject,
            "body": m.body,
            "to": _recipient(db, m),
            "phone": ((co.raw or {}).get("places") or {}).get("phone"),
        })
    leads.sort(key=lambda x: (x["score"] is not None, x["score"] or 0), reverse=True)
    return {"mode": outreach_send_mode(db, org.id), "count": len(leads), "leads": leads}


@router.post("/run", status_code=202)
def run_discovery(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Trigger the org's enabled discovery workflow(s) now (the morning 'Run Today's
    Discovery' button). In manual mode they draft but never send."""
    from app.workers.workflows import run_workflow_task
    wfs = db.execute(
        select(Workflow).where(Workflow.organization_id == org.id,
                               Workflow.enabled.is_(True))
    ).scalars().all()
    kicked = []
    for wf in wfs:
        task = run_workflow_task.delay(str(wf.id))
        kicked.append({"workflow": wf.name, "task_id": task.id})
    return {"triggered": kicked, "count": len(kicked)}


def _draft_for_company(db: Session, org_id, company_id: uuid.UUID) -> EmailMessage | None:
    return db.execute(
        select(EmailMessage).where(
            EmailMessage.organization_id == org_id,
            EmailMessage.company_id == company_id,
            EmailMessage.status == "draft",
        ).order_by(EmailMessage.created_at.desc()).limit(1)
    ).scalar_one_or_none()


@router.post("/{company_id}/sent")
def mark_sent(company_id: uuid.UUID, db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    """I sent this one myself — log it, take it off the review queue, advance CRM."""
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    m = _draft_for_company(db, org.id, company_id)
    to_addr = _recipient(db, m) if m else None
    if m is not None:
        # Leave the queue + enable reply-matching if a reply lands in the connected inbox.
        m.status = "sent"
        m.sent_at = func.now()
        m.meta = {**(m.meta or {}), "manual_sent": True,
                  **({"to": to_addr} if to_addr else {})}
    if co.pipeline_stage in ("new", "qualified"):
        co.pipeline_stage = "contacted"
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=co.id, company_name=co.name,
        channel="email", action="sent", sent_by_me=True))
    db.commit()
    return {"ok": True, "company": co.name, "logged": "sent"}


@router.post("/{company_id}/skip")
def skip_lead(company_id: uuid.UUID, body: SkipBody, db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    """Skip this draft (with a reason) — take it off the queue, record why."""
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    m = _draft_for_company(db, org.id, company_id)
    if m is not None:
        m.status = "skipped"
        m.meta = {**(m.meta or {}), "skip_reason": body.reason}
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=co.id, company_name=co.name,
        channel="email", action="skipped", skip_reason=body.reason))
    db.commit()
    return {"ok": True, "company": co.name, "logged": "skipped", "reason": body.reason}


# ---- /log lives under the same router file but its own prefix ----
log_router = APIRouter(prefix="/log", tags=["today"])


@log_router.get("")
def manual_log(db: Session = Depends(get_db), org: Organization = Depends(current_org),
               days: int = 7):
    rows = db.execute(
        select(ManualOutreachLog).where(
            ManualOutreachLog.organization_id == org.id,
            ManualOutreachLog.created_at >= datetime.utcnow() - timedelta(days=days),
        ).order_by(ManualOutreachLog.created_at.desc())
    ).scalars().all()
    items = [{
        "id": str(r.id), "company_name": r.company_name, "channel": r.channel,
        "action": r.action, "skip_reason": r.skip_reason, "sent_by_me": r.sent_by_me,
        "replied": r.replied, "notes": r.notes, "at": r.created_at,
    } for r in rows]
    sent = sum(1 for r in rows if r.action == "sent")
    skipped = sum(1 for r in rows if r.action == "skipped")
    replied = sum(1 for r in rows if r.replied)
    return {"summary": {"reviewed": len(rows), "sent": sent, "skipped": skipped,
                        "replied": replied, "days": days}, "items": items}


@log_router.patch("/{log_id}")
def update_log(log_id: uuid.UUID, body: LogUpdate, db: Session = Depends(get_db),
               org: Organization = Depends(current_org)):
    r = db.get(ManualOutreachLog, log_id)
    if not r or r.organization_id != org.id:
        raise NotFound("LogEntry")
    if body.replied is not None:
        r.replied = body.replied
    if body.notes is not None:
        r.notes = body.notes
    db.commit()
    return {"ok": True, "replied": r.replied, "notes": r.notes}
