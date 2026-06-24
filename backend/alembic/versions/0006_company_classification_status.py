"""company.classification_status (held_unknown suppression for outreach)

Revision ID: 0006_company_classification_status
Revises: 0005_signal_feed_index
Create Date: 2026-06-24
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_classification_status"  # keep <=32 chars (alembic_version col)
down_revision: Union[str, None] = "0005_signal_feed_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable. null = classified buyer / legacy row; "held_unknown" = the gate could
    # not confirm buyer -> outreach must suppress until re-classified.
    op.add_column(
        "companies",
        sa.Column("classification_status", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "classification_status")
