"""settings.draft_language — 'en' (default) or 'en+ar' to also produce an Arabic DM

Revision ID: 0017_draft_language
Revises: 0016_booking_link
Create Date: 2026-07-06
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_draft_language"
down_revision: Union[str, None] = "0016_booking_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("draft_language", sa.String(10),
                                        nullable=False, server_default="en"))


def downgrade() -> None:
    op.drop_column("settings", "draft_language")
