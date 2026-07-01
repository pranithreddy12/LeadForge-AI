"""settings.outreach_send_mode — manual (draft only) vs automated (workflow sends)

Revision ID: 0014_outreach_send_mode
Revises: 0013_manual_outreach_log
Create Date: 2026-06-30
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_outreach_send_mode"
down_revision: Union[str, None] = "0013_manual_outreach_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column(
        "outreach_send_mode", sa.String(12), server_default="manual", nullable=False))


def downgrade() -> None:
    op.drop_column("settings", "outreach_send_mode")
