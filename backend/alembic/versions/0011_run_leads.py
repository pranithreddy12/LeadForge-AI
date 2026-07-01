"""workflow_runs.run_leads — per-lead detail for the Runs dashboard

Revision ID: 0011_run_leads
Revises: 0010_whatsapp_messages
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_run_leads"
down_revision: Union[str, None] = "0010_whatsapp_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("run_leads", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "run_leads")
