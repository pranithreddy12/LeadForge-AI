from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class Contact(Base, UUIDPk, Timestamps):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_company_email", "company_id", "email", unique=False),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(200))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200), index=True)
    seniority: Mapped[str | None] = mapped_column(String(40))  # cxo | vp | director | manager | ic
    department: Mapped[str | None] = mapped_column(String(80))
    influence_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 0..100
    buying_power: Mapped[str | None] = mapped_column(String(20))
    # decision_maker | influencer | gatekeeper | evaluator | end_user
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    email_status: Mapped[str | None] = mapped_column(String(20))  # valid | risky | invalid | unknown
    email_confidence: Mapped[int | None] = mapped_column(Integer)
    email_validated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    phone: Mapped[str | None] = mapped_column(String(40))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)

    company: Mapped["Company"] = relationship(back_populates="contacts")  # type: ignore[name-defined]  # noqa: F821
