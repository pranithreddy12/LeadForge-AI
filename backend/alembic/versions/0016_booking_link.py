"""settings.booking_link — optional scheduling link for draft CTAs

Revision ID: 0016_booking_link
Revises: 0015_pipeline_config
Create Date: 2026-07-01
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_booking_link"
down_revision: Union[str, None] = "0015_pipeline_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("booking_link", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "booking_link")
