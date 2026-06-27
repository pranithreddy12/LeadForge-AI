"""icp.organization_id + single active ICP per org

Revision ID: 0007_icp_active
Revises: 0006_classification_status
Create Date: 2026-06-26
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_icp_active"
down_revision: Union[str, None] = "0006_classification_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Denormalize org onto icps so a partial-unique index can enforce one active per org.
    op.add_column("icps", sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True),
                                    sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True))
    op.execute("""
        UPDATE icps SET organization_id = p.organization_id
        FROM projects p WHERE p.id = icps.project_id
    """)
    op.create_index("ix_icps_organization_id", "icps", ["organization_id"])

    # Proliferation fix: every ICP currently defaults is_active=true. Reset all to false;
    # the app's activate_icp() then designates exactly one. Partial-unique index makes a
    # second active ICP for the same org impossible at the DB level.
    op.execute("UPDATE icps SET is_active = false")
    op.create_index("uq_icp_one_active_per_org", "icps", ["organization_id"],
                    unique=True, postgresql_where=sa.text("is_active"))


def downgrade() -> None:
    op.drop_index("uq_icp_one_active_per_org", table_name="icps")
    op.drop_index("ix_icps_organization_id", table_name="icps")
    op.drop_column("icps", "organization_id")
