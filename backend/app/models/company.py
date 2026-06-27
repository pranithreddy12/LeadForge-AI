from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class Company(Base, UUIDPk, Timestamps):
    """A discovered account — deduped by `domain` per organization."""

    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_org_domain", "organization_id", "domain", unique=True),
        Index("ix_companies_org_name_trgm", "organization_id", "name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("icps.id", ondelete="SET NULL"), index=True, nullable=True
    )

    name: Mapped[str] = mapped_column(String(300), index=True)
    domain: Mapped[str | None] = mapped_column(String(300), index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(200), index=True)
    sub_industries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    employee_count: Mapped[int | None] = mapped_column(BigInteger)
    employee_range: Mapped[str | None] = mapped_column(String(40))
    revenue_usd: Mapped[int | None] = mapped_column(BigInteger)
    revenue_range: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(80), index=True)
    region: Mapped[str | None] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(120))
    founded_year: Mapped[int | None] = mapped_column()
    tech_stack: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    socials: Mapped[dict] = mapped_column(JSONB, default=dict)
    enriched: Mapped[bool] = mapped_column(Boolean, default=False)
    pipeline_stage: Mapped[str] = mapped_column(
        String(20), default="new", server_default="new", index=True
    )  # new | qualified | contacted | replied | meeting | proposal | won | lost
    source: Mapped[str | None] = mapped_column(String(40))   # tavily | serper | manual | csv | playwright
    # Pipeline STATE: null = active buyer/legacy, "held_unknown" = provider error (retry),
    # "rejected" = a definitive non-buyer the retry confirmed (permanently excluded).
    classification_status: Mapped[str | None] = mapped_column(String(30))
    # Gate VERDICT ("what it is"): buyer | vendor | competitor | investor_vc |
    # job_board_or_directory | listicle_or_content | too_large | unknown. Scoring caps any
    # non-buyer at F/<=40 so a vendor can never be the top lead (BUG 5).
    classification_label: Mapped[str | None] = mapped_column(String(30))
    last_enriched_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    embedding = mapped_column(Vector(settings.openai_embedding_dim), nullable=True)
    embedding_pending: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)

    contacts: Mapped[list["Contact"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )
    signals: Mapped[list["Signal"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )
    scores: Mapped[list["LeadScore"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )
