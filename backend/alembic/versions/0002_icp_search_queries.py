"""add icps.search_queries for buyer-intent discovery

Revision ID: 0002_icp_search_queries
Revises: 0001_initial
Create Date: 2026-06-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_icp_search_queries"
down_revision: Union[str, None] = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "icps",
        sa.Column("search_queries", postgresql.ARRAY(sa.String),
                  server_default="{}", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("icps", "search_queries")
