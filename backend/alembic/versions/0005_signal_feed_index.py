"""index for the dashboard signal feed (org, created_at)

Revision ID: 0005_signal_feed_index
Revises: 0004_contact_influence
Create Date: 2026-06-23
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005_signal_feed_index"
down_revision: Union[str, None] = "0004_contact_influence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The dashboard feed orders org signals by created_at DESC then LIMITs;
    # this composite index lets Postgres serve it without a full sort.
    op.create_index(
        "ix_signals_org_created", "signals", ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_signals_org_created", table_name="signals")
