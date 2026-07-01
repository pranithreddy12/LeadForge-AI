from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class WhatsAppMessage(Base, UUIDPk, Timestamps):
    """One outbound WhatsApp (Meta Cloud API) message per row. Mirrors EmailMessage,
    but phone-centric: the contact is an E.164 number (Places phone), and the provider's
    wamid is stored so inbound status/reply webhooks can be matched back."""

    __tablename__ = "whatsapp_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    contact_phone: Mapped[str] = mapped_column(String(24), index=True)  # E.164 normalized
    message_body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="sent", index=True)
    # sent | delivered | read | replied | failed
    meta_message_id: Mapped[str | None] = mapped_column(String(120), index=True)  # wamid.* from Meta
    sent_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
