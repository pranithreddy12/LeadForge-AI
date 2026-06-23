from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class Campaign(Base, UUIDPk, Timestamps):
    __tablename__ = "campaigns"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email | linkedin
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    messages: Mapped[list["EmailMessage"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class EmailMessage(Base, UUIDPk, Timestamps):
    __tablename__ = "email_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )

    step: Mapped[int] = mapped_column(default=1)  # 1=initial, 2=fu1, 3=fu2, ...
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="email")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | scheduled | sent | replied | bounced
    scheduled_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    open_count: Mapped[int] = mapped_column(default=0)
    click_count: Mapped[int] = mapped_column(default=0)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    campaign: Mapped[Campaign | None] = relationship(back_populates="messages")
