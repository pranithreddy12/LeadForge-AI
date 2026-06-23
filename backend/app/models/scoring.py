from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class LeadScore(Base, UUIDPk, Timestamps):
    __tablename__ = "lead_scores"
    __table_args__ = (
        Index("ix_lead_scores_company_icp", "company_id", "icp_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("icps.id", ondelete="SET NULL"), index=True, nullable=True
    )

    score: Mapped[int] = mapped_column(Integer, index=True)  # 0..100
    grade: Mapped[str] = mapped_column(String(4))  # A+ A B C D F
    probability: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1

    # component scores
    fit_score: Mapped[int] = mapped_column(Integer, default=0)
    funding_score: Mapped[int] = mapped_column(Integer, default=0)
    hiring_score: Mapped[int] = mapped_column(Integer, default=0)
    growth_score: Mapped[int] = mapped_column(Integer, default=0)
    tech_match_score: Mapped[int] = mapped_column(Integer, default=0)
    email_score: Mapped[int] = mapped_column(Integer, default=0)
    activity_score: Mapped[int] = mapped_column(Integer, default=0)

    reasoning: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    suggested_offer: Mapped[str | None] = mapped_column(Text)
    suggested_contact_title: Mapped[str | None] = mapped_column(String(200))
    pain_points: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)

    company: Mapped["Company"] = relationship(back_populates="scores")  # type: ignore[name-defined]  # noqa: F821
