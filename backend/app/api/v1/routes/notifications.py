"""Notifications — actionable nudges for the user, focused on follow-ups.

Two kinds, both derived from real state (nothing invented):
  - followup_ready: a follow-up draft (step >= 2) is written and waiting to send.
  - followup_due:   a lead was contacted >= 3 days ago, hasn't replied, and has no
                    follow-up drafted yet -> time to write one.
Surfaced in the top-bar bell so the user never lets a warm lead go cold.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.manual_outreach import ManualOutreachLog
from app.models.tenant import Organization

router = APIRouter(prefix="/notifications", tags=["notifications"])

_FOLLOWUP_DUE_DAYS = 3   # a lead sent this long ago with no reply + no draft = nudge


@router.get("")
def list_notifications(db: Session = Depends(get_db),
                       org: Organization = Depends(current_org)):
    """Follow-up nudges, newest-contacted first. `count` is the badge number."""
    logs = db.execute(
        select(ManualOutreachLog).where(
            ManualOutreachLog.organization_id == org.id,
            ManualOutreachLog.action == "sent",
        ).order_by(ManualOutreachLog.created_at.desc())
    ).scalars().all()

    now = datetime.utcnow()
    seen: set = set()
    items: list[dict] = []
    for lg in logs:
        if not lg.company_id or lg.company_id in seen:
            continue
        seen.add(lg.company_id)
        co = db.get(Company, lg.company_id)
        if co is None or co.pipeline_stage == "replied" or lg.replied:
            continue
        age = (now - lg.created_at.replace(tzinfo=None)).days if lg.created_at else 0

        ready = db.execute(
            select(EmailMessage).where(
                EmailMessage.company_id == co.id,
                EmailMessage.step >= 2,
                EmailMessage.status == "draft",
            ).order_by(EmailMessage.step)
        ).scalars().all()

        if ready:
            for m in ready:
                items.append({
                    "id": f"fu-{m.id}",
                    "type": "followup_ready",
                    "company_id": str(co.id),
                    "company_name": co.name,
                    "title": f"Follow-up #{max(1, m.step - 1)} ready for {co.name}",
                    "detail": m.subject or "Draft ready to send",
                    "days_ago": age,
                    "href": "/followups",
                })
        elif age >= _FOLLOWUP_DUE_DAYS:
            items.append({
                "id": f"due-{co.id}",
                "type": "followup_due",
                "company_id": str(co.id),
                "company_name": co.name,
                "title": f"Time to follow up with {co.name}",
                "detail": f"Contacted {age} days ago, no reply yet — send a nudge.",
                "days_ago": age,
                "href": "/followups",
            })

    # Ready-to-send first, then due; oldest-contacted first within each (most overdue up top).
    items.sort(key=lambda x: (x["type"] != "followup_ready", -x["days_ago"]))
    return {"count": len(items),
            "ready": sum(1 for i in items if i["type"] == "followup_ready"),
            "due": sum(1 for i in items if i["type"] == "followup_due"),
            "items": items}
