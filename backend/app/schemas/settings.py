from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CredentialStatus(BaseModel):
    """Whether a credential is set — NEVER its value."""
    gmail_address: str | None = None          # not secret -> shown
    telegram_chat_id: str | None = None       # not secret -> shown
    gmail_app_password_set: bool = False
    telegram_bot_token_set: bool = False
    google_places_api_key_set: bool = False
    # WhatsApp (Meta Cloud API)
    whatsapp_phone_number_id: str | None = None       # not secret -> shown
    whatsapp_business_account_id: str | None = None   # not secret -> shown
    whatsapp_access_token_set: bool = False
    whatsapp_verify_token_set: bool = False
    # Contact enrichment
    hunter_api_key_set: bool = False


class SettingsOut(BaseModel):
    discovery_mode: str
    # local
    target_business_types: list[str] = []
    target_locations: list[str] = []
    search_radius_miles: int = 25
    min_reviews: int = 10
    max_results_per_run: int = 20
    # b2b
    icp_name: str | None = None
    employee_min: int | None = None
    employee_max: int | None = None
    target_industries: list[str] = []
    target_geography: list[str] = []
    # outreach
    outreach_mode: list[str] = ["email"]
    outreach_tone: str = "professional"
    outreach_send_mode: str = "manual"   # manual (draft only) | automated (workflow sends)
    booking_link: str | None = None
    draft_language: str = "en"           # en | en+ar (adds an Arabic DM variant)
    outreach_services: str | None = None  # other services for the soft "and more" line
    max_emails_per_day: int = 50
    max_emails_per_run: int = 25
    # contact finding
    contact_find_hunter: bool = True
    contact_find_scrape: bool = True
    contact_find_linkedin: bool = True
    validate_emails: bool = True
    # lead-quality filter
    filter_min_score: int = 65
    filter_enforce_icp_size: bool = True
    # read-only webhook URL to paste into the Meta console (WhatsApp)
    whatsapp_webhook_url: str = ""
    # credentials — masked
    credentials: CredentialStatus


class SettingsUpdate(BaseModel):
    """Full update. Credential fields are OPTIONAL plaintext: provide a value to set/
    rotate it; omit (or null) to leave the stored secret unchanged (so the UI never
    wipes a credential just because the field was rendered blank)."""
    discovery_mode: Literal["b2b", "local"]
    target_business_types: list[str] = []
    target_locations: list[str] = []
    search_radius_miles: int = Field(25, ge=1, le=500)
    min_reviews: int = Field(10, ge=0)
    max_results_per_run: int = Field(20, ge=1, le=60)
    icp_name: str | None = None
    employee_min: int | None = Field(None, ge=0)
    employee_max: int | None = Field(None, ge=0)
    target_industries: list[str] = []
    target_geography: list[str] = []
    outreach_mode: list[str] = ["email"]
    outreach_tone: Literal["professional", "friendly", "direct"] = "professional"
    outreach_send_mode: Literal["manual", "automated"] = "manual"
    booking_link: str | None = None
    draft_language: Literal["en", "en+ar"] = "en"
    outreach_services: str | None = Field(None, max_length=500)
    max_emails_per_day: int = Field(50, ge=0, le=2000)
    max_emails_per_run: int = Field(25, ge=0, le=500)
    contact_find_hunter: bool = True
    contact_find_scrape: bool = True
    contact_find_linkedin: bool = True
    validate_emails: bool = True
    filter_min_score: int = Field(65, ge=0, le=100)
    filter_enforce_icp_size: bool = True
    # credentials (optional plaintext)
    gmail_address: str | None = None
    gmail_app_password: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_places_api_key: str | None = None
    # WhatsApp (Meta Cloud API) — ids are not secret, token/verify are
    whatsapp_phone_number_id: str | None = None
    whatsapp_business_account_id: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_verify_token: str | None = None
    hunter_api_key: str | None = None

    @model_validator(mode="after")
    def _required_per_mode(self):
        if self.discovery_mode == "local":
            if not self.target_business_types:
                raise ValueError("local mode requires at least one target_business_type")
            if not self.target_locations:
                raise ValueError("local mode requires at least one target_location")
        else:  # b2b
            if not (self.icp_name and self.icp_name.strip()):
                raise ValueError("b2b mode requires an icp_name")
            if not self.target_industries:
                raise ValueError("b2b mode requires at least one target_industry")
        return self
