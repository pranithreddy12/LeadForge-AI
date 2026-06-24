"""Reply detection — polls the Gmail inbox via IMAP and fires a Telegram alert
when someone we emailed replies.

Matching strategy (robust, no provider webhooks needed):
  - Pull UNSEEN messages from the inbox.
  - For each, take the sender's email address.
  - If it matches the recipient of one of our SENT EmailMessages, it's a reply:
    mark the message replied, advance the company to the 'replied' CRM stage,
    log a CRM activity, and notify Telegram.

Runs on Celery Beat every few minutes. Idempotent: a message already marked
replied is skipped, and we mark processed mail as Seen.
"""
from __future__ import annotations

import email
import imaplib
from email.header import decode_header, make_header

from celery import shared_task
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.contact import Contact
from app.models.crm import CRMActivity
from app.services import telegram
from app.services.email_sender import sent_message_index
from app.workers._base import task_session

log = get_logger("workers.inbox")


def _imap_configured() -> bool:
    return bool(settings.gmail_address and settings.gmail_app_password)


def _from_addr(msg) -> str:
    raw = msg.get("From", "")
    # extract the bare address from "Name <a@b.com>"
    if "<" in raw and ">" in raw:
        return raw.split("<", 1)[1].split(">", 1)[0].strip().lower()
    return raw.strip().lower()


def _body_snippet(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")[:400]
                except Exception:
                    continue
        return ""
    try:
        return (msg.get_payload(decode=True) or b"").decode(errors="ignore")[:400]
    except Exception:
        return ""


@shared_task(name="app.workers.inbox.poll_replies")
def poll_replies(max_messages: int = 30) -> dict:
    if not _imap_configured():
        return {"skipped": "gmail_not_configured"}

    # Build the recipient->sent-message index across all orgs that have sent mail.
    with task_session() as db:
        org_ids = db.execute(
            select(EmailMessage.organization_id)
            .where(EmailMessage.status == "sent").distinct()
        ).scalars().all()
        index: dict[str, EmailMessage] = {}
        for oid in org_ids:
            index.update(sent_message_index(db, oid))

        if not index:
            return {"replies": 0, "note": "no_sent_emails_to_match"}

        replies = 0
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            imap.login(settings.gmail_address, settings.gmail_app_password)
            imap.select("INBOX")
            _typ, data = imap.search(None, "UNSEEN")
            ids = (data[0].split() if data and data[0] else [])[:max_messages]
            for mid in ids:
                _typ, raw = imap.fetch(mid, "(RFC822)")
                if not raw or not raw[0]:
                    continue
                msg = email.message_from_bytes(raw[0][1])
                sender = _from_addr(msg)
                match = index.get(sender)
                if not match:
                    continue  # leave unrelated mail UNSEEN
                replies += _record_reply(db, match, msg)
                imap.store(mid, "+FLAGS", "\\Seen")
            imap.logout()
        except Exception as e:
            log.warning("imap_poll_failed", error=str(e))
            return {"replies": replies, "error": str(e)[:160]}

        return {"replies": replies}


def _record_reply(db, message: EmailMessage, msg) -> int:
    if message.status == "replied":
        return 0
    from sqlalchemy import func
    subject = str(make_header(decode_header(msg.get("Subject", "")))) if msg.get("Subject") else (message.subject or "")
    snippet = _body_snippet(msg).strip()

    message.status = "replied"
    message.replied_at = func.now()

    company = db.get(Company, message.company_id) if message.company_id else None
    contact = db.get(Contact, message.contact_id) if message.contact_id else None
    contact_name = contact.name if contact else (message.meta or {}).get("to", "Someone")
    company_name = company.name if company else "a company"

    if company and company.pipeline_stage in ("new", "qualified", "contacted"):
        company.pipeline_stage = "replied"
    db.add(CRMActivity(
        organization_id=message.organization_id,
        company_id=message.company_id,
        contact_id=message.contact_id,
        kind="email",
        body=f"Reply received: {snippet[:280]}",
        payload={"direction": "inbound", "subject": subject},
    ))
    db.commit()

    telegram.notify_reply(
        contact_name=contact_name, company_name=company_name,
        subject=subject, snippet=snippet,
        company_id=str(message.company_id) if message.company_id else None,
    )
    log.info("reply_recorded", company=company_name, contact=contact_name)
    return 1
