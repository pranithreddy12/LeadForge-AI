"""manual_outreach_log — manual-send sprint tracking

Revision ID: 0013_manual_outreach_log
Revises: 0012_hunter_key
Create Date: 2026-06-30
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_manual_outreach_log"
down_revision: Union[str, None] = "0012_hunter_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_outreach_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("channel", sa.String(20), server_default="email", nullable=False),
        sa.Column("action", sa.String(20), server_default="sent", nullable=False),
        sa.Column("skip_reason", sa.String(40), nullable=True),
        sa.Column("sent_by_me", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("replied", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_manual_outreach_log_organization_id", "manual_outreach_log", ["organization_id"])
    op.create_index("ix_manual_outreach_log_company_id", "manual_outreach_log", ["company_id"])


def downgrade() -> None:
    op.drop_table("manual_outreach_log")
