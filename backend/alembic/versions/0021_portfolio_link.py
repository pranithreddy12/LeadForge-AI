"""portfolio_link — optional examples/portfolio link for follow-ups + reply drafts

Revision ID: 0021_portfolio_link
Revises: 0020_outreach_services
Create Date: 2026-07-19
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_portfolio_link"
down_revision: Union[str, None] = "0020_outreach_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("portfolio_link", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "portfolio_link")
