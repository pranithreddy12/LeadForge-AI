"""WhatsApp outreach: settings credentials + whatsapp_messages table

Revision ID: 0010_whatsapp_messages
Revises: 0009_class_label
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_whatsapp_messages"
down_revision: Union[str, None] = "0009_class_label"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- WhatsApp credentials on settings (1A) ----
    op.add_column("settings", sa.Column("whatsapp_phone_number_id", sa.String(60), nullable=True))
    op.add_column("settings", sa.Column("whatsapp_business_account_id", sa.String(60), nullable=True))
    op.add_column("settings", sa.Column("whatsapp_access_token_enc", sa.Text, nullable=True))
    op.add_column("settings", sa.Column("whatsapp_verify_token_enc", sa.Text, nullable=True))

    # ---- whatsapp_messages table (1C) ----
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_phone", sa.String(24), nullable=False),
        sa.Column("message_body", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), server_default="sent", nullable=False),
        sa.Column("meta_message_id", sa.String(120), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_whatsapp_messages_organization_id", "whatsapp_messages", ["organization_id"])
    op.create_index("ix_whatsapp_messages_company_id", "whatsapp_messages", ["company_id"])
    op.create_index("ix_whatsapp_messages_contact_phone", "whatsapp_messages", ["contact_phone"])
    op.create_index("ix_whatsapp_messages_status", "whatsapp_messages", ["status"])
    op.create_index("ix_whatsapp_messages_meta_message_id", "whatsapp_messages", ["meta_message_id"])


def downgrade() -> None:
    op.drop_table("whatsapp_messages")
    op.drop_column("settings", "whatsapp_verify_token_enc")
    op.drop_column("settings", "whatsapp_access_token_enc")
    op.drop_column("settings", "whatsapp_business_account_id")
    op.drop_column("settings", "whatsapp_phone_number_id")
