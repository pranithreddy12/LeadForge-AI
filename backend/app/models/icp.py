from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class ICP(Base, UUIDPk, Timestamps):
    """Ideal Customer Profile generated for a project."""

    __tablename__ = "icps"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    industries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    sub_industries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    countries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    regions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    employee_min: Mapped[int | None] = mapped_column(default=None)
    employee_max: Mapped[int | None] = mapped_column(default=None)
    revenue_min_usd: Mapped[int | None] = mapped_column(default=None)
    revenue_max_usd: Mapped[int | None] = mapped_column(default=None)
    buyer_personas: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    buying_signals: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    excluded_keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    tech_stack_required: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    tech_stack_excluded: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    weights: Mapped[dict] = mapped_column(JSONB, default=dict)
    raw_ai_response: Mapped[dict] = mapped_column(JSONB, default=dict)

    project: Mapped["Project"] = relationship(back_populates="icps")  # type: ignore[name-defined]  # noqa: F821
