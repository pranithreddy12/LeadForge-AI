from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class Workflow(Base, UUIDPk, Timestamps):
    """User-defined automation pipeline (Clay/Zapier-style)."""

    __tablename__ = "workflows"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # cron-like trigger ("daily" | "hourly" | "manual" | crontab string)
    schedule: Mapped[str] = mapped_column(String(40), default="manual")
    next_run_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    # DAG of steps:  [{id, type, config, next:[...]}]
    steps: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowRun(Base, UUIDPk, Timestamps):
    __tablename__ = "workflow_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending | running | success | partial | failed | canceled
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    step_results: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    items_in: Mapped[int] = mapped_column(Integer, default=0)
    items_out: Mapped[int] = mapped_column(Integer, default=0)

    workflow: Mapped[Workflow] = relationship(back_populates="runs")
