"""Process inbound WhatsApp (Meta Cloud API) webhook payloads.

Two payload shapes arrive on the same endpoint:
  - `messages`: an actual inbound reply from a prospect -> mark our WhatsAppMessage
    replied, advance the company to CRM stage 'replied', log a CRMActivity, cancel the
    scheduled email fallback, and fire a Telegram alert.
  - `statuses`: delivery/read receipts -> update WhatsAppMessage.status only.

Idempotency: a re-delivered reply (already 'replied') is a no-op. The caller always
returns HTTP 200 to Meta regardless of processing errors (Meta retries on non-200).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt
from app.core.logging import get_logger
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.crm import CRMActivity
from app.models.scoring import LeadScore
from app.models.settings import Settings
from app.models.signal import Signal
from app.models.whatsapp import WhatsAppMessage
from app.services.whatsapp_sender import normalize_phone

log = get_logger(__name__)

_OPEN_WA_STATUSES = ("sent", "delivered", "read")


def valid_verify_token(db: Session, token: str | None) -> bool:
    """Meta webhook verification: token must match the global .env verify token OR any
    org's stored (encrypted) verify token."""
    if not token:
        return False
    if settings.whatsapp_verify_token and token == settings.whatsapp_verify_token:
        return True
    rows = db.execute(
        select(Settings.whatsapp_verify_token_enc).where(
            Settings.whatsapp_verify_token_enc.is_not(None)
        )
    ).scalars().all()
    return any(decrypt(enc) == token for enc in rows if enc)


def _city_of(company: Company) -> str | None:
    # Local SMBs carry a real Places address; parse "..., City, ST 12345" -> "City, ST".
    addr = ((company.raw or {}).get("places") or {}).get("address")
    if addr:
        parts = [p.strip() for p in str(addr).split(",") if p.strip()]
        if len(parts) >= 2:
            tail = parts[-1].split()
            region = tail[0] if tail else ""
            return f"{parts[-2]}, {region}".strip(", ") if region else parts[-2]
        if parts:
            return parts[0]
    # B2B: use the real city column if enriched — never the marketing description.
    if company.city:
        return f"{company.city}, {company.region}" if company.region else company.city
    return None


def _driving_signal(db: Session, company_id) -> str | None:
    s = db.execute(
        select(Signal.label, Signal.kind).where(Signal.company_id == company_id)
        .order_by(Signal.severity.desc().nullslast()).limit(1)
    ).first()
    return (s[0] or s[1]) if s else None


def _latest_score(db: Session, company_id):
    return db.execute(
        select(LeadScore.score, LeadScore.grade).where(LeadScore.company_id == company_id)
        .order_by(LeadScore.created_at.desc()).limit(1)
    ).first()


def _handle_message(db: Session, from_phone: str, text: str) -> bool:
    """Match an inbound message to an open WhatsAppMessage and process the reply once.
    Returns True if a reply was newly recorded."""
    normalized = normalize_phone(from_phone)
    if not normalized:
        log.info("whatsapp_inbound_unnormalizable", raw=str(from_phone)[:40])
        return False
    wam = db.execute(
        select(WhatsAppMessage).where(
            WhatsAppMessage.contact_phone == normalized,
            WhatsAppMessage.status.in_(_OPEN_WA_STATUSES + ("replied",)),
        ).order_by(WhatsAppMessage.sent_at.desc().nullslast()).limit(1)
    ).scalar_one_or_none()
    if wam is None:
        log.info("whatsapp_inbound_no_match", phone=normalized)
        return False
    if wam.status == "replied":
        log.info("whatsapp_inbound_idempotent", phone=normalized)  # already processed
        return False

    wam.status = "replied"
    wam.replied_at = func.now()

    company = db.get(Company, wam.company_id) if wam.company_id else None
    city = grade = signal = phone = email = suggested = None
    score = None
    company_name = normalized
    if company is not None:
        company.pipeline_stage = "replied"
        company_name = company.name or normalized
        city = _city_of(company)
        signal = _driving_signal(db, company.id)
        sc = _latest_score(db, company.id)
        if sc:
            score, grade = int(sc[0]) if sc[0] is not None else None, sc[1]
        phone = ((company.raw or {}).get("places") or {}).get("phone")
        # Mistral suggested next reply (None on provider error) — stored so /replies
        # and the Telegram alert both show it.
        suggested = _suggested_response(company, text, signal)
        # CRM activity log (reply text + suggested response live in the payload).
        db.add(CRMActivity(
            organization_id=wam.organization_id, company_id=company.id,
            kind="whatsapp", body=f"WhatsApp reply: {text[:500]}",
            occurred_at=func.now(),
            payload={"channel": "whatsapp", "reply": text[:1000],
                     "suggested_response": suggested, "wamid": wam.meta_message_id},
        ))
        # Cancel any scheduled email fallback for this company.
        cancelled = db.execute(
            select(EmailMessage).where(
                EmailMessage.company_id == company.id,
                EmailMessage.status == "scheduled",
            )
        ).scalars().all()
        for m in cancelled:
            m.status = "cancelled"
            m.meta = {**(m.meta or {}), "cancelled_reason": "whatsapp_replied"}

    db.commit()

    # Fire Telegram (best-effort; never blocks).
    try:
        from app.services import telegram
        telegram.notify_whatsapp_reply(
            company_name=company_name, city=city, grade=grade, score=score,
            signal=signal, reply_text=text, suggested_response=suggested,
            phone=phone, email=email,
            company_id=str(company.id) if company else None)
    except Exception as e:
        log.warning("whatsapp_reply_telegram_failed", error=str(e)[:200])
    log.info("whatsapp_reply_recorded", phone=normalized, company=company_name)
    return True


def _suggested_response(company: Company, reply_text: str, signal: str | None) -> str | None:
    """Mistral-generated suggested next reply (Section 4A). None on provider error —
    the notification still sends with all other fields."""
    from app.ai.outreach_engine import generate_suggested_reply
    res = generate_suggested_reply(
        company={"name": company.name}, their_message=reply_text,
        signal=signal, channel="whatsapp")
    return res.get("suggested_response") if not res.get("_provider_error") else None


def _handle_status(db: Session, wamid: str, status: str) -> bool:
    """delivered / read receipts -> update the WhatsAppMessage status (never downgrade
    a 'replied')."""
    if status not in ("delivered", "read"):
        return False
    wam = db.execute(
        select(WhatsAppMessage).where(WhatsAppMessage.meta_message_id == wamid).limit(1)
    ).scalar_one_or_none()
    if wam is None or wam.status in ("replied",):
        return False
    # don't move read -> delivered backwards
    if wam.status == "read" and status == "delivered":
        return False
    wam.status = status
    db.commit()
    return True


def process_inbound(db: Session, payload: dict) -> dict:
    """Walk a Meta webhook payload. Never raises (caller must return 200)."""
    replies = statuses = 0
    try:
        for entry in (payload.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = change.get("value") or {}
                for msg in (value.get("messages") or []):
                    if msg.get("type") == "text":
                        body = (msg.get("text") or {}).get("body") or ""
                    else:
                        body = f"[{msg.get('type', 'non-text')} message]"
                    if _handle_message(db, msg.get("from"), body):
                        replies += 1
                for st in (value.get("statuses") or []):
                    if _handle_status(db, st.get("id"), st.get("status")):
                        statuses += 1
    except Exception as e:
        db.rollback()
        log.warning("whatsapp_inbound_error", error=str(e)[:300])
    return {"replies": replies, "statuses": statuses}
