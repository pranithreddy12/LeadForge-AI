"""place_cache — cache Google Place Details to cut the per-day quota

Revision ID: 0019_place_cache
Revises: 0018_do_not_contact
Create Date: 2026-07-08
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_place_cache"
down_revision: Union[str, None] = "0018_do_not_contact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "place_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("place_id", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="reviews"),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("place_id", "kind", name="uq_place_cache_pid_kind"),
    )
    op.create_index("ix_place_cache_place_id", "place_cache", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_place_cache_place_id", table_name="place_cache")
    op.drop_table("place_cache")
