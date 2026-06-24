"""add account_research table (Phase 6)

Revision ID: 0003_account_research
Revises: 0002_icp_search_queries
Create Date: 2026-06-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_account_research"
down_revision: Union[str, None] = "0002_icp_search_queries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_research",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("summary", sa.Text),
        sa.Column("pain_points", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("current_initiatives", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("growth_signals", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("key_facts", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("recommended_pitch", sa.Text),
        sa.Column("suggested_contact_title", sa.String(200)),
        sa.Column("confidence", sa.Integer, server_default="0"),
        sa.Column("sources", postgresql.JSONB, server_default="[]"),
        sa.Column("raw", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_account_research_company_time", "account_research",
                    ["company_id", "created_at"])


def downgrade() -> None:
    op.drop_table("account_research")
