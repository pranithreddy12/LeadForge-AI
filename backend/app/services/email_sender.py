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

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.campaign import EmailMessage
from app.models.contact import Contact

log = get_logger(__name__)


def is_configured() -> bool:
    return bool(settings.gmail_address and settings.gmail_app_password)


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


def send_email_message(db: Session, message: EmailMessage) -> dict:
    """Send one drafted EmailMessage via Gmail. Marks it sent + stores Message-ID.

    Returns a status dict; never raises (failures are recorded on the row)."""
    if not is_configured():
        return {"sent": False, "reason": "gmail_not_configured"}
    if message.channel != "email":
        return {"sent": False, "reason": "not_email_channel"}
    if message.status == "sent":
        return {"sent": False, "reason": "already_sent"}

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

    message_id = make_msgid(domain=settings.gmail_address.split("@")[-1] or "leadforge.ai")
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
