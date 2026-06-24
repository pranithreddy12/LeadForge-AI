"""add contact influence_score + buying_power (Phase 7)

Revision ID: 0004_contact_influence
Revises: 0003_account_research
Create Date: 2026-06-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_contact_influence"
down_revision: Union[str, None] = "0003_account_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("influence_score", sa.Integer,
                  server_default="0", nullable=False))
    op.add_column("contacts", sa.Column("buying_power", sa.String(20)))
    op.create_index("ix_contacts_influence", "contacts",
                    ["company_id", "influence_score"])


def downgrade() -> None:
    op.drop_index("ix_contacts_influence", table_name="contacts")
    op.drop_column("contacts", "buying_power")
    op.drop_column("contacts", "influence_score")
