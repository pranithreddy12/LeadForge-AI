"""settings: contact-finding toggles + lead-quality filter config

Revision ID: 0015_pipeline_config
Revises: 0014_outreach_send_mode
Create Date: 2026-06-30
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_pipeline_config"
down_revision: Union[str, None] = "0014_outreach_send_mode"
branch_labels = None
depends_on = None

_T = sa.text("true")
_F = sa.text("false")


def upgrade() -> None:
    op.add_column("settings", sa.Column("contact_find_hunter", sa.Boolean, server_default=_T, nullable=False))
    op.add_column("settings", sa.Column("contact_find_scrape", sa.Boolean, server_default=_T, nullable=False))
    op.add_column("settings", sa.Column("contact_find_linkedin", sa.Boolean, server_default=_T, nullable=False))
    op.add_column("settings", sa.Column("validate_emails", sa.Boolean, server_default=_T, nullable=False))
    op.add_column("settings", sa.Column("filter_min_score", sa.Integer, server_default="65", nullable=False))
    op.add_column("settings", sa.Column("filter_enforce_icp_size", sa.Boolean, server_default=_T, nullable=False))


def downgrade() -> None:
    for col in ("filter_enforce_icp_size", "filter_min_score", "validate_emails",
                "contact_find_linkedin", "contact_find_scrape", "contact_find_hunter"):
        op.drop_column("settings", col)
