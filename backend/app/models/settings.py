from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class Settings(Base, UUIDPk, Timestamps):
    """One settings row per org — the single source of truth for discovery, outreach,
    send limits, and credentials. Replaces the hardcoded ICP / multi-ICP lookup and
    moves caps out of .env. Credential SECRETS are stored encrypted (see core.crypto);
    non-secret identifiers (gmail_address, telegram_chat_id) are plaintext."""

    __tablename__ = "settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        unique=True, index=True,
    )

    discovery_mode: Mapped[str] = mapped_column(String(10), default="b2b")  # b2b | local

    # ---- Local-business config ----
    target_business_types: Mapped[list] = mapped_column(JSONB, default=list)
    target_locations: Mapped[list] = mapped_column(JSONB, default=list)
    search_radius_miles: Mapped[int] = mapped_column(Integer, default=25)
    min_reviews: Mapped[int] = mapped_column(Integer, default=10)
    max_results_per_run: Mapped[int] = mapped_column(Integer, default=20)

    # ---- B2B config (the single source of truth for the synced active ICP) ----
    icp_name: Mapped[str | None] = mapped_column(String(200))
    employee_min: Mapped[int | None] = mapped_column(Integer)
    employee_max: Mapped[int | None] = mapped_column(Integer)
    target_industries: Mapped[list] = mapped_column(JSONB, default=list)
    target_geography: Mapped[list] = mapped_column(JSONB, default=list)

    # ---- Outreach config ----
    outreach_mode: Mapped[list] = mapped_column(JSONB, default=lambda: ["email"])
    outreach_tone: Mapped[str] = mapped_column(String(20), default="professional")

    # ---- Send limits (moved out of .env) ----
    max_emails_per_day: Mapped[int] = mapped_column(Integer, default=50)
    max_emails_per_run: Mapped[int] = mapped_column(Integer, default=25)

    # ---- Credentials ----
    gmail_address: Mapped[str | None] = mapped_column(String(200))            # not secret
    gmail_app_password_enc: Mapped[str | None] = mapped_column(Text)          # encrypted
    telegram_bot_token_enc: Mapped[str | None] = mapped_column(Text)          # encrypted
    telegram_chat_id: Mapped[str | None] = mapped_column(String(60))         # not secret
    google_places_api_key_enc: Mapped[str | None] = mapped_column(Text)      # encrypted
