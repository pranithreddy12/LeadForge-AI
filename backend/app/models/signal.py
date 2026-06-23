from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class Signal(Base, UUIDPk, Timestamps):
    """A buying signal observed for a company."""

    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_company_kind_time", "company_id", "kind", "observed_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    # taxonomy
    kind: Mapped[str] = mapped_column(String(40), index=True)
    # one of: hiring, funding, growth, product_launch, tech_install, leadership_change,
    #        partnership, news, traffic_growth, office_expansion
    label: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    confidence: Mapped[float] = mapped_column(Float, default=0.7)  # 0..1
    url: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str | None] = mapped_column(String(40))
    observed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    company: Mapped["Company"] = relationship(back_populates="signals")  # type: ignore[name-defined]  # noqa: F821
