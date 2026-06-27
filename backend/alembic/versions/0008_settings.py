"""settings table (one per org) — source of truth for discovery/outreach/creds

Revision ID: 0008_settings
Revises: 0007_icp_active
Create Date: 2026-06-26
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_settings"
down_revision: Union[str, None] = "0007_icp_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("discovery_mode", sa.String(10), server_default="b2b", nullable=False),
        sa.Column("target_business_types", postgresql.JSONB, server_default="[]"),
        sa.Column("target_locations", postgresql.JSONB, server_default="[]"),
        sa.Column("search_radius_miles", sa.Integer, server_default="25"),
        sa.Column("min_reviews", sa.Integer, server_default="10"),
        sa.Column("max_results_per_run", sa.Integer, server_default="20"),
        sa.Column("icp_name", sa.String(200)),
        sa.Column("employee_min", sa.Integer),
        sa.Column("employee_max", sa.Integer),
        sa.Column("target_industries", postgresql.JSONB, server_default="[]"),
        sa.Column("target_geography", postgresql.JSONB, server_default="[]"),
        sa.Column("outreach_mode", postgresql.JSONB, server_default='["email"]'),
        sa.Column("outreach_tone", sa.String(20), server_default="professional"),
        sa.Column("max_emails_per_day", sa.Integer, server_default="50"),
        sa.Column("max_emails_per_run", sa.Integer, server_default="25"),
        sa.Column("gmail_address", sa.String(200)),
        sa.Column("gmail_app_password_enc", sa.Text),
        sa.Column("telegram_bot_token_enc", sa.Text),
        sa.Column("telegram_chat_id", sa.String(60)),
        sa.Column("google_places_api_key_enc", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_settings_organization_id", "settings", ["organization_id"])
    # Seed one row per existing org (defaults). Live .env values get migrated in by the
    # app-level seed (cli) so they can be encrypted with the runtime APP_SECRET_KEY.
    op.execute("""
        INSERT INTO settings (id, organization_id, discovery_mode)
        SELECT gen_random_uuid(), id, 'b2b' FROM organizations
    """)


def downgrade() -> None:
    op.drop_index("ix_settings_organization_id", table_name="settings")
    op.drop_table("settings")
