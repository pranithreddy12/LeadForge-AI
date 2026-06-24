"""Outbound email via Gmail SMTP + reply tracking helpers.

Send uses smtp.gmail.com with a Google App Password (NOT your login password —
create one at https://myaccount.google.com/apppasswords with 2FA enabled).

Each sent message gets a unique Message-ID we persist on EmailMessage.meta so the
IMAP reply poller can match an inbound reply back to the original email/contact.
"""
from __future__ import annotations

import smtplib
import ssl
import uuid as uuidlib
from email.message import EmailMessage as MIMEMessage
from email.utils import formataddr, make_msgid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.contact import Contact

log = get_logger(__name__)

# CRM stages that mean "already in contact or beyond" — never (re)draft/send.
_CONTACTED_OR_BEYOND = {"contacted", "replied", "meeting", "proposal", "won", "lost"}
# EmailMessage statuses that mean "we already attempted to reach this company".
_ALREADY_SENT_STATUSES = ("sent", "replied", "bounced")


def is_configured() -> bool:
    return bool(settings.gmail_address and settings.gmail_app_password)


def stamp_message_id() -> str:
    """The single source of truth for outgoing Message-IDs. Used by the real send path
    AND the dry-run, so the dry-run exercises the actual stamping, not a mock."""
    return make_msgid(domain=(settings.gmail_address.split("@")[-1] if settings.gmail_address
                              else "") or "leadforge.ai")


def suppression_reason(db: Session, company: Company,
                       contact: Contact | None = None) -> str | None:
    """Return a concrete reason string if outreach to this company must be SUPPRESSED
    (not drafted, not sent), else None.

    Checks ALL THREE conditions INDEPENDENTLY and reports every one that matches (no
    short-circuit) so the dry-run shows exactly why a company was skipped:
      (a) a sent/replied/bounced EmailMessage already exists for the company;
      (b) the CRM pipeline_stage is contacted/replied/or beyond — even with NO
          EmailMessage row (covers manual stage advances / out-of-band sends);
      (c) classification_status == 'held_unknown' — the gate has not confirmed buyer.
    """
    reasons: list[str] = []

    # (c) held / unconfirmed by the qualification gate.
    if company.classification_status == "held_unknown":
        reasons.append("held_unknown: qualification gate has not confirmed this is a buyer")

    # (a) an already-attempted EmailMessage exists.
    q = select(func.count(EmailMessage.id)).where(
        EmailMessage.company_id == company.id,
        EmailMessage.status.in_(_ALREADY_SENT_STATUSES),
    )
    if contact is not None:
        # company-level dedup by default; tighten to the contact if one is given.
        q = q.where((EmailMessage.contact_id == contact.id)
                    | (EmailMessage.contact_id.is_(None)))
    n_sent = db.execute(q).scalar_one()
    if n_sent:
        reasons.append(f"already_emailed: {n_sent} sent/replied/bounced EmailMessage row(s) exist")

    # (b) CRM stage at/after 'contacted', regardless of EmailMessage rows.
    if company.pipeline_stage in _CONTACTED_OR_BEYOND:
        reasons.append(f"crm_stage: pipeline_stage='{company.pipeline_stage}' is contacted-or-beyond")

    return "; ".join(reasons) if reasons else None


def _send_raw(*, to_addr: str, subject: str, body: str, message_id: str) -> None:
    msg = MIMEMessage()
    msg["From"] = formataddr((settings.gmail_from_name, settings.gmail_address))
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.starttls(context=ctx)
        server.login(settings.gmail_address, settings.gmail_app_password)
        server.send_message(msg)


def sent_today_count(db: Session, organization_id) -> int:
    """Emails actually sent (status=sent) for this org since UTC midnight — used to
    enforce the global daily cap."""
    return db.execute(
        select(func.count(EmailMessage.id)).where(
            EmailMessage.organization_id == organization_id,
            EmailMessage.status == "sent",
            EmailMessage.sent_at >= func.date_trunc("day", func.now()),
        )
    ).scalar_one()


def daily_cap_remaining(db: Session, organization_id) -> int:
    return max(0, settings.max_emails_per_day - sent_today_count(db, organization_id))


def send_email_message(db: Session, message: EmailMessage) -> dict:
    """Send one drafted EmailMessage via Gmail. Marks it sent + stores Message-ID.

    Returns a status dict; never raises (failures are recorded on the row)."""
    if not is_configured():
        return {"sent": False, "reason": "gmail_not_configured"}
    if message.channel != "email":
        return {"sent": False, "reason": "not_email_channel"}
    if message.status == "sent":
        return {"sent": False, "reason": "already_sent"}

    # Suppression guardrail at the SEND boundary too (a draft may have been created
    # before the company advanced). Belt-and-suspenders with the draft-time check.
    company = db.get(Company, message.company_id) if message.company_id else None
    if company is not None:
        reason = suppression_reason(db, company)
        if reason:
            return {"sent": False, "reason": f"suppressed: {reason}"}

    # Resolve recipient — prefer the linked contact's validated email.
    to_addr = None
    if message.contact_id:
        contact = db.get(Contact, message.contact_id)
        if contact and contact.email:
            to_addr = contact.email
    to_addr = to_addr or (message.meta or {}).get("to")
    if not to_addr:
        message.status = "bounced"
        message.meta = {**(message.meta or {}), "error": "no_recipient_email"}
        db.commit()
        return {"sent": False, "reason": "no_recipient_email"}

    message_id = stamp_message_id()
    try:
        _send_raw(to_addr=to_addr, subject=message.subject, body=message.body,
                  message_id=message_id)
    except Exception as e:
        log.warning("gmail_send_failed", error=str(e))
        message.status = "bounced"
        message.meta = {**(message.meta or {}), "error": str(e)[:300]}
        db.commit()
        return {"sent": False, "reason": str(e)[:120]}

    from sqlalchemy import func
    message.status = "sent"
    message.sent_at = func.now()
    message.meta = {**(message.meta or {}), "message_id": message_id, "to": to_addr}
    db.commit()
    log.info("email_sent", to=to_addr, message_id=message_id)
    return {"sent": True, "to": to_addr, "message_id": message_id}


def sent_message_index(db: Session, organization_id: uuidlib.UUID) -> dict[str, EmailMessage]:
    """Map of {recipient_email_lower: EmailMessage} for sent, not-yet-replied
    emails — used by the reply poller to match inbound mail to an outreach."""
    from sqlalchemy import select
    rows = db.execute(
        select(EmailMessage).where(
            EmailMessage.organization_id == organization_id,
            EmailMessage.status == "sent",
        )
    ).scalars().all()
    out: dict[str, EmailMessage] = {}
    for m in rows:
        to = (m.meta or {}).get("to")
        if to:
            out[to.lower()] = m
    return out
