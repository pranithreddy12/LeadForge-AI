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
        # Suppression guardrail — never draft for an already-contacted or held company.
        from app.services.email_sender import suppression_reason
        reason = suppression_reason(db, company)
        if reason:
            log.info("outreach_suppressed", company=str(company.id), reason=reason)
            return {"created": 0, "suppressed": reason}
        # Prefer a contact that actually HAS an email (else the send bounces) — pick
        # the highest-influence emailable one; fall back to any contact for the draft.
        contact = db.execute(
            select(Contact).where(Contact.company_id == company.id,
                                  Contact.email.is_not(None))
            .order_by(Contact.influence_score.desc().nullslast()).limit(1)
        ).scalar_one_or_none() or db.execute(
            select(Contact).where(Contact.company_id == company.id)
            .order_by(Contact.is_primary.desc(), Contact.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        icp = db.get(ICP, company.icp_id) if company.icp_id else None
        signals = db.execute(
            select(Signal).where(Signal.company_id == company.id).limit(15)
        ).scalars().all()

        # Mode + tone from Settings: local businesses get the Places-grounded path.
        from app.services.settings_resolver import settings_row
        s = settings_row(db, company.organization_id)
        is_local = bool(s and s.discovery_mode == "local")
        eff_tone = (s.outreach_tone if s else None) or tone
        raw = generate_outreach(
            company=_row(company),
            contact=_row(contact),
            icp=_row(icp),
            signals=[_row(s_) for s_ in signals],
            channel=channel, tone=eff_tone, local=is_local,
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
