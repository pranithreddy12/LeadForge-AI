"""do_not_contact — opt-out / suppression registry (UAE PDPL + unsubscribe duty)

Revision ID: 0018_do_not_contact
Revises: 0017_draft_language
Create Date: 2026-07-06
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_do_not_contact"
down_revision: Union[str, None] = "0017_draft_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "do_not_contact",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False, server_default="email"),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "value", name="uq_dnc_org_value"),
    )
    op.create_index("ix_do_not_contact_organization_id", "do_not_contact", ["organization_id"])
    op.create_index("ix_do_not_contact_value", "do_not_contact", ["value"])


def downgrade() -> None:
    op.drop_index("ix_do_not_contact_value", table_name="do_not_contact")
    op.drop_index("ix_do_not_contact_organization_id", table_name="do_not_contact")
    op.drop_table("do_not_contact")
