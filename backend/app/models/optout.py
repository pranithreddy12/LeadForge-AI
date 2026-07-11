from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class DoNotContact(Base, UUIDPk, Timestamps):
    """A do-not-contact / opt-out entry (UAE PDPL + Google/Yahoo unsubscribe duty).
    One normalized identifier (email, phone digits, or bare domain) that must be
    EXCLUDED from all future drafting/sending for the org. Populated automatically
    when a reply says stop/unsubscribe, or manually from /today or /replies."""

    __tablename__ = "do_not_contact"
    __table_args__ = (
        UniqueConstraint("organization_id", "value", name="uq_dnc_org_value"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    # normalized identifier: email (lowercased), phone (digits only), or domain
    value: Mapped[str] = mapped_column(String(255), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="email")   # email | phone | domain
    reason: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | reply | import
