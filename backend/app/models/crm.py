from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class PipelineStage(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    contacted = "contacted"
    replied = "replied"
    meeting = "meeting"
    proposal = "proposal"
    won = "won"
    lost = "lost"


# Pipeline state lives on the Company via a denormalized column for fast filtering.
# Activities/tasks are first-class rows.


class CRMActivity(Base, UUIDPk, Timestamps):
    __tablename__ = "crm_activities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    kind: Mapped[str] = mapped_column(String(40))  # note | email | call | meeting | stage_change | task
    body: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class CRMTask(Base, UUIDPk, Timestamps):
    __tablename__ = "crm_tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1 high .. 3 low
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


# Pipeline column on Company is added via Alembic op (avoids circular imports):
# companies.pipeline_stage  ENUM(PipelineStage) DEFAULT 'new'
# We expose it dynamically via SQL where needed.
