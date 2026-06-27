"""company.classification_label (gate verdict) + backfill from classification_status

Revision ID: 0009_class_label
Revises: 0008_settings
Create Date: 2026-06-26
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_class_label"
down_revision: Union[str, None] = "0008_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("classification_label", sa.String(30), nullable=True))
    # Backfill: classification_status historically held the verdict for reclassified rows
    # (vendor/too_large/investor_vc). Copy those over; buyers/null/held_unknown become a
    # 'buyer'/null label as appropriate.
    op.execute("""
        UPDATE companies SET classification_label =
            CASE
              WHEN classification_status IS NULL OR classification_status = 'buyer' THEN 'buyer'
              WHEN classification_status = 'held_unknown' THEN 'unknown'
              ELSE classification_status
            END
    """)
    # Normalize status: a stored reject verdict becomes the 'rejected' pipeline state.
    op.execute("""
        UPDATE companies SET classification_status = 'rejected'
        WHERE classification_status NOT IN ('held_unknown', 'buyer') AND classification_status IS NOT NULL
    """)
    op.execute("UPDATE companies SET classification_status = NULL WHERE classification_status = 'buyer'")


def downgrade() -> None:
    op.drop_column("companies", "classification_label")
