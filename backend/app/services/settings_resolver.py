"""Resolve config/credentials: Settings row first, then global .env (logged).

D2: the .env fallback is essential (don't break what works) but must be EXPLICIT —
when a service uses a global .env credential instead of one set in Settings, we log it
so production never wonders which credential is actually in use.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as cfg
from app.core.crypto import decrypt
from app.core.logging import get_logger
from app.models.settings import Settings

log = get_logger(__name__)

# logical name -> (Settings column, encrypted?, .env attr on cfg)
_CRED_MAP = {
    "gmail_address":         ("gmail_address",             False, "gmail_address"),
    "gmail_app_password":    ("gmail_app_password_enc",    True,  "gmail_app_password"),
    "telegram_bot_token":    ("telegram_bot_token_enc",    True,  "telegram_bot_token"),
    "telegram_chat_id":      ("telegram_chat_id",          False, "telegram_chat_id"),
    "google_places_api_key": ("google_places_api_key_enc", True,  "google_maps_api_key"),
    "whatsapp_phone_number_id":     ("whatsapp_phone_number_id",     False, "whatsapp_phone_number_id"),
    "whatsapp_business_account_id": ("whatsapp_business_account_id", False, "whatsapp_business_account_id"),
    "whatsapp_access_token":        ("whatsapp_access_token_enc",    True,  "whatsapp_access_token"),
    "whatsapp_verify_token":        ("whatsapp_verify_token_enc",    True,  "whatsapp_verify_token"),
    "hunter_api_key":               ("hunter_api_key_enc",           True,  "hunter_api_key"),
}


def settings_row(db: Session, organization_id: uuid.UUID) -> Settings | None:
    return db.execute(
        select(Settings).where(Settings.organization_id == organization_id)
    ).scalars().first()


def resolve_credential(db: Session, organization_id: uuid.UUID, name: str) -> str:
    """Return the credential, preferring the org's Settings; fall back to .env (logged)."""
    col, enc, env_attr = _CRED_MAP[name]
    s = settings_row(db, organization_id)
    if s is not None:
        raw = getattr(s, col, None)
        val = (decrypt(raw) if enc else raw) or ""
        if val.strip():
            return val.strip()
    env_val = (getattr(cfg, env_attr, "") or "").strip()
    if env_val:
        log.info("using_global_env_credential", credential=name,
                 hint="set it in Settings to override the global .env value")
    return env_val


def outreach_send_mode(db: Session, organization_id: uuid.UUID) -> str:
    """'manual' (draft only, send yourself on /today) or 'automated' (workflow sends).
    Safe default: 'manual' — nothing auto-sends unless explicitly switched on."""
    s = settings_row(db, organization_id)
    return (s.outreach_send_mode if s and s.outreach_send_mode else "manual")


def pipeline_config(db: Session, organization_id: uuid.UUID) -> dict:
    """All the Settings-driven pipeline toggles in one dict (safe defaults if no row).
    Keeps the workflow steps config-driven instead of hardcoded."""
    s = settings_row(db, organization_id)
    if s is None:
        return {"contact_find_hunter": True, "contact_find_scrape": True,
                "contact_find_linkedin": True, "validate_emails": True,
                "filter_min_score": 65, "filter_enforce_icp_size": True,
                "discovery_mode": "b2b"}
    return {
        "contact_find_hunter": bool(s.contact_find_hunter),
        "contact_find_scrape": bool(s.contact_find_scrape),
        "contact_find_linkedin": bool(s.contact_find_linkedin),
        "validate_emails": bool(s.validate_emails),
        "filter_min_score": int(s.filter_min_score if s.filter_min_score is not None else 65),
        "filter_enforce_icp_size": bool(s.filter_enforce_icp_size),
        "discovery_mode": s.discovery_mode or "b2b",
    }


def resolve_caps(db: Session, organization_id: uuid.UUID) -> tuple[int, int]:
    """(max_emails_per_run, max_emails_per_day) — Settings first, else .env."""
    s = settings_row(db, organization_id)
    if s is not None:
        return s.max_emails_per_run, s.max_emails_per_day
    return cfg.max_emails_per_run, cfg.max_emails_per_day
