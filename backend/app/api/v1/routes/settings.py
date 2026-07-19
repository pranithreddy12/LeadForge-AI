from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as cfg
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
        outreach_send_mode=s.outreach_send_mode or "manual",
        booking_link=s.booking_link,
        draft_language=s.draft_language or "en",
        outreach_services=s.outreach_services,
        max_emails_per_day=s.max_emails_per_day,
        max_emails_per_run=s.max_emails_per_run,
        contact_find_hunter=bool(s.contact_find_hunter),
        contact_find_scrape=bool(s.contact_find_scrape),
        contact_find_linkedin=bool(s.contact_find_linkedin),
        validate_emails=bool(s.validate_emails),
        filter_min_score=int(s.filter_min_score if s.filter_min_score is not None else 65),
        filter_enforce_icp_size=bool(s.filter_enforce_icp_size),
        whatsapp_webhook_url=f"{cfg.api_public_url.rstrip('/')}/api/v1/webhooks/whatsapp",
        credentials=CredentialStatus(
            gmail_address=s.gmail_address,
            telegram_chat_id=s.telegram_chat_id,
            gmail_app_password_set=bool(s.gmail_app_password_enc),
            telegram_bot_token_set=bool(s.telegram_bot_token_enc),
            google_places_api_key_set=bool(s.google_places_api_key_enc),
            whatsapp_phone_number_id=s.whatsapp_phone_number_id,
            whatsapp_business_account_id=s.whatsapp_business_account_id,
            whatsapp_access_token_set=bool(s.whatsapp_access_token_enc),
            whatsapp_verify_token_set=bool(s.whatsapp_verify_token_enc),
            hunter_api_key_set=bool(s.hunter_api_key_enc),
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
              "outreach_mode", "outreach_tone", "outreach_send_mode", "booking_link",
              "draft_language", "outreach_services",
              "max_emails_per_day", "max_emails_per_run",
              "contact_find_hunter", "contact_find_scrape", "contact_find_linkedin",
              "validate_emails", "filter_min_score", "filter_enforce_icp_size"):
        setattr(s, f, getattr(payload, f))
    # non-secret identifiers
    if payload.gmail_address is not None:
        s.gmail_address = payload.gmail_address or None
    if payload.telegram_chat_id is not None:
        s.telegram_chat_id = payload.telegram_chat_id or None
    if payload.whatsapp_phone_number_id is not None:
        s.whatsapp_phone_number_id = payload.whatsapp_phone_number_id or None
    if payload.whatsapp_business_account_id is not None:
        s.whatsapp_business_account_id = payload.whatsapp_business_account_id or None
    # secrets — only rotate when a value is provided; empty string clears it
    if payload.gmail_app_password is not None:
        s.gmail_app_password_enc = encrypt(payload.gmail_app_password) or None
    if payload.telegram_bot_token is not None:
        s.telegram_bot_token_enc = encrypt(payload.telegram_bot_token) or None
    if payload.google_places_api_key is not None:
        s.google_places_api_key_enc = encrypt(payload.google_places_api_key) or None
    if payload.whatsapp_access_token is not None:
        s.whatsapp_access_token_enc = encrypt(payload.whatsapp_access_token) or None
    if payload.whatsapp_verify_token is not None:
        s.whatsapp_verify_token_enc = encrypt(payload.whatsapp_verify_token) or None
    if payload.hunter_api_key is not None:
        s.hunter_api_key_enc = encrypt(payload.hunter_api_key) or None
    db.commit()
    db.refresh(s)

    # B2B: keep the org's single active ICP in sync with Settings (kills proliferation).
    if s.discovery_mode == "b2b":
        from app.services.settings_sync import sync_active_icp_from_settings
        sync_active_icp_from_settings(db, s)
    return _serialize(s)


@router.get("/sending-health")
def sending_health_check(db: Session = Depends(get_db),
                         org: Organization = Depends(current_org)):
    """Bounce rate, today's volume vs cap, and account risk — the two numbers that
    actually predict a suspension, measured from real send outcomes."""
    from app.services.sending_health import sending_health
    return sending_health(db, org.id)


@router.get("/deliverability")
def deliverability_check(domain: str | None = None,
                         db: Session = Depends(get_db),
                         org: Organization = Depends(current_org)):
    """SPF/DKIM/DMARC/MX preflight for the SENDING domain (Gmail/Yahoo bulk-sender
    rules, hard-enforced since Nov 2025). Defaults to the configured gmail_address
    domain; pass ?domain= to check a custom sending domain before switching to it."""
    from app.services.presend import domain_auth
    if not domain:
        s = _get_or_create(db, org.id)
        if s.gmail_address and "@" in s.gmail_address:
            domain = s.gmail_address.rsplit("@", 1)[-1]
    result = domain_auth(domain or "")
    if (domain or "").lower().endswith("gmail.com"):
        result["notes"].insert(0, (
            "You send from a personal Gmail address: Google signs SPF/DKIM/DMARC for "
            "gmail.com automatically, so this check passing is about Google's domain, "
            "not yours. Limits still apply (keep volume low, warm up gradually). "
            "For scale, move to a custom domain and re-check it here."))
    return result
