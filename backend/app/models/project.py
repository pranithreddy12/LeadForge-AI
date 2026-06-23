from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class Project(Base, UUIDPk, Timestamps):
    """A 'workspace' inside an organization — e.g. one agency offering."""

    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200))
    business_description: Mapped[str] = mapped_column(Text)
    target_offering: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    organization: Mapped["Organization"] = relationship(back_populates="projects")  # type: ignore[name-defined]  # noqa: F821
    icps: Mapped[list["ICP"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
