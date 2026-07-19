"""outreach_services — the seller's other services for the soft 'and more' line

Revision ID: 0020_outreach_services
Revises: 0019_place_cache
Create Date: 2026-07-19
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_outreach_services"
down_revision: Union[str, None] = "0019_place_cache"
branch_labels = None
depends_on = None

_DEFAULT = "AI receptionist, WhatsApp booking automation, review management, missed-call text-back"


def upgrade() -> None:
    op.add_column("settings", sa.Column("outreach_services", sa.String(500),
                                        nullable=True, server_default=_DEFAULT))


def downgrade() -> None:
    op.drop_column("settings", "outreach_services")
