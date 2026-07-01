"""Outbound WhatsApp via the Meta Cloud (Graph) API.

POST https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages
     Authorization: Bearer {ACCESS_TOKEN}

NOTHING-STATIC: on a real provider error (Meta API error / 429) we log the full
response, return {"_provider_error": True}, and persist NOTHING — never a canned
fallback message. A WhatsAppMessage row is written ONLY on a confirmed send.

Credentials resolve from the org's Settings first, then the global .env (logged),
mirroring the Gmail pattern (see settings_resolver).
"""
from __future__ import annotations

import re
import uuid as uuidlib

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.whatsapp import WhatsAppMessage
from app.services.settings_resolver import resolve_credential

log = get_logger(__name__)

_GRAPH_VERSION = "v18.0"


def normalize_phone(raw: str | None) -> str | None:
    """Convert a raw phone string to E.164 (+12145551234), or None if it can't be
    sent safely. Rules:
      - strip to digits; a leading '+' marks an already-international number
      - a 10-digit US number with no country code -> prepend +1
      - an 11-digit number starting with 1 -> +1XXXXXXXXXX
      - too short, non-numeric, or missing country code -> None (skip, do not send)
    """
    if not raw:
        return None
    s = str(raw).strip()
    had_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None  # non-numeric
    if had_plus:
        # already carries a country code; sanity-floor the length
        return f"+{digits}" if len(digits) >= 8 else None
    if len(digits) == 10:
        return f"+1{digits}"          # US/Canada without country code
    if len(digits) == 11 and digits.startswith("1"):
        return f"+1{digits[1:]}"      # US/Canada with leading 1
    # A full international number supplied WITHOUT a '+' — this is exactly how Meta sends
    # the inbound `from` / wa_id (e.g. "919014150785" for +91 90141 50785). Treat any
    # 11-15 digit run as already carrying its country code.
    if 11 <= len(digits) <= 15:
        return f"+{digits}"
    # 7-9 digits = too short / missing country code -> skip.
    return None


def is_configured(db: Session, organization_id: uuidlib.UUID) -> bool:
    pid = resolve_credential(db, organization_id, "whatsapp_phone_number_id")
    tok = resolve_credential(db, organization_id, "whatsapp_access_token")
    return bool(pid and tok)


def send_whatsapp(db: Session, *, organization_id: uuidlib.UUID, to_phone: str,
                  body: str, company_id: uuidlib.UUID | None = None) -> dict:
    """Send one WhatsApp text via the Meta Cloud API.

    Returns one of:
      {"sent": True, "wamid": ..., "to": "+1...", "row_id": ...}   on success (row written)
      {"sent": False, "reason": "..."}                              on a guard skip
      {"_provider_error": True, "reason": "..."}                    on Meta API error / 429

    On any provider error NOTHING is persisted.
    """
    phone_number_id = resolve_credential(db, organization_id, "whatsapp_phone_number_id")
    access_token = resolve_credential(db, organization_id, "whatsapp_access_token")
    if not (phone_number_id and access_token):
        return {"sent": False, "reason": "whatsapp_not_configured"}

    normalized = normalize_phone(to_phone)
    if not normalized:
        log.info("whatsapp_phone_skipped", reason="unnormalizable", raw=str(to_phone)[:40])
        return {"sent": False, "reason": "invalid_phone"}

    # Log the normalized number before every send attempt (audit trail).
    log.info("whatsapp_send_attempt", to=normalized, phone_number_id=phone_number_id)

    url = f"https://graph.facebook.com/{_GRAPH_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized.lstrip("+"),
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {access_token}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=20.0,
        )
    except Exception as e:
        log.warning("whatsapp_send_failed", to=normalized, error=str(e)[:300])
        return {"_provider_error": True, "reason": str(e)[:160]}

    if r.status_code == 429:
        # Rate limited — do NOT retry in this run; persist nothing.
        log.warning("whatsapp_rate_limited", to=normalized, body=r.text[:500])
        return {"_provider_error": True, "reason": "rate_limited_429"}

    if r.status_code >= 400:
        # Meta API error — log the full error response, persist nothing.
        log.warning("whatsapp_api_error", to=normalized, status=r.status_code,
                    body=r.text[:800])
        return {"_provider_error": True, "reason": f"meta_api_error_{r.status_code}"}

    try:
        data = r.json()
        wamid = (data.get("messages") or [{}])[0].get("id")
    except Exception:
        wamid = None

    row = WhatsAppMessage(
        organization_id=organization_id,
        company_id=company_id,
        contact_phone=normalized,
        message_body=body,
        status="sent",
        meta_message_id=wamid,
        sent_at=func.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("whatsapp_sent", to=normalized, wamid=wamid, row_id=str(row.id))
    return {"sent": True, "wamid": wamid, "to": normalized, "row_id": str(row.id)}
