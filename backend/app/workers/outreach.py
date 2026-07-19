from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import delete, func, select

from app.ai.outreach_engine import generate_outreach
from app.core.logging import get_logger
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.signal import Signal
from app.models.whatsapp import WhatsAppMessage
from app.workers._base import task_session

log = get_logger("workers.outreach")


def _row(r):
    return {c.key: getattr(r, c.key) for c in r.__table__.columns} if r else None


@shared_task(name="app.workers.outreach.draft_outreach_for_company")
def draft_outreach_for_company(organization_id: str, company_id: str,
                               campaign_id: str | None = None,
                               channel: str = "email", tone: str = "concise",
                               force: bool = False) -> dict:
    with task_session() as db:
        company = db.get(Company, uuid.UUID(company_id))
        if not company or str(company.organization_id) != organization_id:
            return {"error": "company_not_found"}
        # Suppression guardrail — never AUTO-draft for an already-contacted or held
        # company. `force=True` is an explicit human action on the lead page ("Generate
        # draft" to see/reuse the content), so it bypasses the guard on purpose.
        from app.services.email_sender import suppression_reason
        reason = suppression_reason(db, company)
        if reason and not force:
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
        # Named decision-maker (Dr./owner scraped from About/Team) drives the greeting.
        dm = db.execute(
            select(Contact).where(Contact.company_id == company.id,
                                  Contact.name.ilike("Dr.%"))
            .order_by(Contact.is_primary.desc(), Contact.created_at).limit(1)
        ).scalar_one_or_none()
        greeting_name = dm.name if dm else None
        signals = db.execute(
            select(Signal).where(Signal.company_id == company.id).limit(15)
        ).scalars().all()

        # Mode + tone from Settings: local businesses get the Places-grounded path.
        from app.services.settings_resolver import settings_row
        s = settings_row(db, company.organization_id)
        is_local = bool(s and s.discovery_mode == "local")
        eff_tone = (s.outreach_tone if s else None) or tone
        market_fact = None
        if is_local:
            from app.services.dossier import cohort_booking_stat
            market_fact = cohort_booking_stat(db, company)
        raw = generate_outreach(
            company=_row(company),
            contact=_row(contact),
            icp=_row(icp),
            signals=[_row(s_) for s_ in signals],
            channel=channel, tone=eff_tone, local=is_local,
            booking_link=(s.booking_link if s else None),
            greeting_name=greeting_name,
            market_fact=market_fact,
            language=(getattr(s, "draft_language", None) or "en") if s else "en",
            services=(getattr(s, "outreach_services", None) if s else None),
        )
        variants = raw.get("variants") or []
        if not variants:
            return {"created": 0}
        v = variants[0]
        # One primary draft per company: replace any existing UNSENT primary draft on this
        # channel instead of stacking a second one (re-drafting must not duplicate the lead
        # on /today). Sent messages are history and are never touched.
        db.execute(
            delete(EmailMessage).where(
                EmailMessage.company_id == company.id,
                EmailMessage.channel == channel,
                EmailMessage.status == "draft",
                EmailMessage.step < 2,
            )
        )
        msg = EmailMessage(
            organization_id=uuid.UUID(organization_id),
            campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
            company_id=company.id,
            contact_id=contact.id if contact else None,
            subject=v.get("subject") or f"About {company.name}",
            body=v.get("body") or "",
            channel=channel,
            status="draft",
            meta={**({"dm": raw["dm"]} if raw.get("dm") else {}),
                  **({"dm_ar": raw["dm_ar"]} if raw.get("dm_ar") else {}),
                  **({"auto_reply_comeback": raw["auto_reply_comeback"]}
                     if raw.get("auto_reply_comeback") else {})},
        )
        db.add(msg)
        return {"created": 1, "subject": msg.subject}


def _followup_recipient(db, company):
    return db.execute(
        select(Contact).where(Contact.company_id == company.id, Contact.email.is_not(None))
        .order_by(Contact.influence_score.desc().nullslast()).limit(1)
    ).scalar_one_or_none()


def draft_followups_for_org(db, organization_id) -> dict:
    """Draft the day-3 (step 2) and day-6 (step 3) follow-ups for leads that were marked
    sent that long ago and haven't replied. Different angle + booking link. Manual send.
    Idempotent: never drafts a step that already exists for the company."""
    from datetime import datetime, timedelta
    from app.ai.outreach_engine import generate_outreach
    from app.models.manual_outreach import ManualOutreachLog
    from app.services.settings_resolver import settings_row

    now = datetime.utcnow()
    logs = db.execute(
        select(ManualOutreachLog).where(
            ManualOutreachLog.organization_id == organization_id,
            ManualOutreachLog.action == "sent",
            ManualOutreachLog.replied.is_(False),
        )
    ).scalars().all()
    s = settings_row(db, organization_id)
    made = 0
    seen_company: set = set()
    for lg in logs:
        if not lg.company_id or lg.company_id in seen_company:
            continue
        seen_company.add(lg.company_id)
        company = db.get(Company, lg.company_id)
        if not company or company.pipeline_stage == "replied":
            continue
        age_days = (now - lg.created_at.replace(tzinfo=None)).days if lg.created_at else 0
        for step, min_age, angle in (
            (2, 3, "a short, friendly bump from a DIFFERENT angle than the first email "
                   "(e.g. a quick specific benefit or a one-line case result)"),
            (3, 6, "a final brief nudge, low-pressure, easy to say yes or no"),
        ):
            if age_days < min_age:
                continue
            exists = db.execute(
                select(EmailMessage.id).where(EmailMessage.company_id == company.id,
                                              EmailMessage.step == step).limit(1)
            ).first()
            if exists:
                continue
            contact = _followup_recipient(db, company)
            dm = db.execute(
                select(Contact).where(Contact.company_id == company.id,
                                      Contact.name.ilike("Dr.%")).limit(1)
            ).scalar_one_or_none()
            icp = db.get(ICP, company.icp_id) if company.icp_id else None
            signals = db.execute(
                select(Signal).where(Signal.company_id == company.id).limit(10)
            ).scalars().all()
            is_local = bool(s and s.discovery_mode == "local")
            raw = generate_outreach(
                company=_row(company), contact=_row(contact), icp=_row(icp),
                signals=[_row(x) for x in signals], channel="email",
                tone=(s.outreach_tone if s else "concise"), local=is_local,
                follow_up=step - 1, booking_link=(s.booking_link if s else None),
                greeting_name=(dm.name if dm else None),
            )
            variants = (raw or {}).get("variants") or []
            if not variants:
                continue
            v = variants[0]
            db.add(EmailMessage(
                organization_id=organization_id, company_id=company.id,
                contact_id=contact.id if contact else None, step=step,
                subject=v.get("subject") or f"Following up - {company.name}",
                body=v.get("body") or "", channel="email", status="draft",
                meta={"followup_day": min_age, **({"to": contact.email} if (contact and contact.email) else {})},
            ))
            made += 1
    db.commit()
    log.info("draft_followups", org=str(organization_id), drafted=made)
    return {"drafted": made}


@shared_task(name="app.workers.outreach.draft_followups")
def draft_followups() -> dict:
    """Daily: draft due follow-ups for every org (manual send — they surface on
    /pipeline)."""
    from sqlalchemy import distinct
    from app.models.manual_outreach import ManualOutreachLog
    with task_session() as db:
        org_ids = db.execute(select(distinct(ManualOutreachLog.organization_id))).scalars().all()
        total = 0
        for oid in org_ids:
            total += draft_followups_for_org(db, oid).get("drafted", 0)
        return {"drafted": total, "orgs": len(org_ids)}


@shared_task(name="app.workers.outreach.rescore_and_redraft")
def rescore_and_redraft(organization_id: str) -> dict:
    """After the ICP (or Settings) changes: re-score EVERY lead against the now-active
    ICP and re-draft its outreach. Leads already sent/contacted are left alone (the
    draft suppression guard skips them)."""
    from sqlalchemy import delete, select
    from app.models.scoring import LeadScore
    from app.services.icp import get_active_icp
    from app.services.scoring import score_company
    with task_session() as db:
        oid = uuid.UUID(organization_id)
        icp = get_active_icp(db, oid)
        if icp is None:
            return {"error": "no_active_icp"}
        companies = db.execute(
            select(Company).where(Company.organization_id == oid)).scalars().all()
        # 1. Re-score everything with the active ICP (old scores cleared first).
        db.execute(delete(LeadScore).where(LeadScore.organization_id == oid))
        db.commit()
        rescored = 0
        for c in companies:
            try:
                score_company(db, organization_id=oid, company_id=c.id,
                              icp_id=icp.id, with_opportunity=False)
                rescored += 1
            except Exception as e:
                log.warning("rescore_failed", company=str(c.id), error=str(e)[:120])
        # 2. Drop draft-status emails and re-draft (suppression skips sent/contacted).
        db.execute(delete(EmailMessage).where(
            EmailMessage.organization_id == oid, EmailMessage.status == "draft"))
        db.commit()
        redrafted = 0
        for c in companies:
            r = draft_outreach_for_company(str(oid), str(c.id), channel="email")
            redrafted += r.get("created", 0)
        log.info("rescore_and_redraft", icp=icp.name, rescored=rescored, redrafted=redrafted)
        return {"icp": icp.name, "rescored": rescored, "redrafted": redrafted}


@shared_task(name="app.workers.outreach.send_scheduled_emails")
def send_scheduled_emails() -> dict:
    """Hourly: send EmailMessages whose scheduled_at has passed. For a WhatsApp-first
    sequence, if the same company has already REPLIED on WhatsApp, cancel the scheduled
    email instead of sending (set status='cancelled'). Otherwise send via the existing
    Gmail sender, bypassing only the whatsapp_active guard (this IS the deliberate
    fallback, not a parallel send)."""
    from app.services.email_sender import send_email_message
    from app.services.settings_resolver import outreach_send_mode

    with task_session() as db:
        due = db.execute(
            select(EmailMessage).where(
                EmailMessage.status == "scheduled",
                EmailMessage.channel == "email",
                EmailMessage.scheduled_at.is_not(None),
                EmailMessage.scheduled_at <= func.now(),
            )
        ).scalars().all()
        sent = cancelled = skipped_manual = 0
        for m in due:
            # Manual mode never auto-sends — leave the scheduled draft for /today.
            if outreach_send_mode(db, m.organization_id) == "manual":
                skipped_manual += 1
                continue
            if m.company_id is not None:
                replied = db.execute(
                    select(func.count(WhatsAppMessage.id)).where(
                        WhatsAppMessage.company_id == m.company_id,
                        WhatsAppMessage.status == "replied",
                    )
                ).scalar_one()
                if replied:
                    m.status = "cancelled"
                    m.meta = {**(m.meta or {}), "cancelled_reason": "whatsapp_replied"}
                    cancelled += 1
                    continue
            if send_email_message(db, m, skip_whatsapp_guard=True).get("sent"):
                sent += 1
        db.commit()
        log.info("send_scheduled_emails", due=len(due), sent=sent, cancelled=cancelled,
                 skipped_manual=skipped_manual)
        return {"due": len(due), "sent": sent, "cancelled": cancelled,
                "skipped_manual": skipped_manual}
