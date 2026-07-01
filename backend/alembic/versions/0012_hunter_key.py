"""settings.hunter_api_key_enc — encrypted Hunter.io key

Revision ID: 0012_hunter_key
Revises: 0011_run_leads
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_hunter_key"
down_revision: Union[str, None] = "0011_run_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("hunter_api_key_enc", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "hunter_api_key_enc")
