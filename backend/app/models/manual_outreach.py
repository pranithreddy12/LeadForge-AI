from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class ManualOutreachLog(Base, UUIDPk, Timestamps):
    """One row per lead the user manually acted on during the manual-send sprint.
    'Mark as sent' on /today writes a row here; /log shows the rolling history."""

    __tablename__ = "manual_outreach_log"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    company_name: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email | whatsapp
    action: Mapped[str] = mapped_column(String(20), default="sent")    # sent | skipped
    skip_reason: Mapped[str | None] = mapped_column(String(40))        # bad_fit | no_contact | looks_wrong | other
    sent_by_me: Mapped[bool] = mapped_column(Boolean, default=False)
    replied: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
