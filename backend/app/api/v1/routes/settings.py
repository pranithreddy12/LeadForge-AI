from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.core.deps import current_org
from app.models.settings import Settings
from app.models.tenant import Organization
from app.schemas.settings import CredentialStatus, SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_or_create(db: Session, org_id) -> Settings:
    s = db.execute(select(Settings).where(Settings.organization_id == org_id)).scalars().first()
    if not s:
        s = Settings(organization_id=org_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _serialize(s: Settings) -> SettingsOut:
    return SettingsOut(
        discovery_mode=s.discovery_mode,
        target_business_types=s.target_business_types or [],
        target_locations=s.target_locations or [],
        search_radius_miles=s.search_radius_miles,
        min_reviews=s.min_reviews,
        max_results_per_run=s.max_results_per_run,
        icp_name=s.icp_name,
        employee_min=s.employee_min,
        employee_max=s.employee_max,
        target_industries=s.target_industries or [],
        target_geography=s.target_geography or [],
        outreach_mode=s.outreach_mode or ["email"],
        outreach_tone=s.outreach_tone,
        max_emails_per_day=s.max_emails_per_day,
        max_emails_per_run=s.max_emails_per_run,
        credentials=CredentialStatus(
            gmail_address=s.gmail_address,
            telegram_chat_id=s.telegram_chat_id,
            gmail_app_password_set=bool(s.gmail_app_password_enc),
            telegram_bot_token_set=bool(s.telegram_bot_token_enc),
            google_places_api_key_set=bool(s.google_places_api_key_enc),
        ),
    )


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    return _serialize(_get_or_create(db, org.id))


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db),
                    org: Organization = Depends(current_org)):
    s = _get_or_create(db, org.id)
    # non-credential config — full update
    for f in ("discovery_mode", "target_business_types", "target_locations",
              "search_radius_miles", "min_reviews", "max_results_per_run", "icp_name",
              "employee_min", "employee_max", "target_industries", "target_geography",
              "outreach_mode", "outreach_tone", "max_emails_per_day", "max_emails_per_run"):
        setattr(s, f, getattr(payload, f))
    # non-secret identifiers
    if payload.gmail_address is not None:
        s.gmail_address = payload.gmail_address or None
    if payload.telegram_chat_id is not None:
        s.telegram_chat_id = payload.telegram_chat_id or None
    # secrets — only rotate when a value is provided; empty string clears it
    if payload.gmail_app_password is not None:
        s.gmail_app_password_enc = encrypt(payload.gmail_app_password) or None
    if payload.telegram_bot_token is not None:
        s.telegram_bot_token_enc = encrypt(payload.telegram_bot_token) or None
    if payload.google_places_api_key is not None:
        s.google_places_api_key_enc = encrypt(payload.google_places_api_key) or None
    db.commit()
    db.refresh(s)

    # B2B: keep the org's single active ICP in sync with Settings (kills proliferation).
    if s.discovery_mode == "b2b":
        from app.services.settings_sync import sync_active_icp_from_settings
        sync_active_icp_from_settings(db, s)
    return _serialize(s)
