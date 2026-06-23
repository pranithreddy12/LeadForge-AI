"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- organizations / users / memberships ----------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("clerk_org_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("plan", sa.String(32), nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.String(64)),
        sa.Column("settings", postgresql.JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("clerk_user_id", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False, index=True),
        sa.Column("name", sa.String(200)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("last_seen_at", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    # --- projects -------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("business_description", sa.Text, nullable=False),
        sa.Column("target_offering", sa.Text),
        sa.Column("metadata", postgresql.JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- icps -----------------------------------------------------------------
    op.create_table(
        "icps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("industries", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("sub_industries", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("countries", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("regions", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("employee_min", sa.Integer),
        sa.Column("employee_max", sa.Integer),
        sa.Column("revenue_min_usd", sa.BigInteger),
        sa.Column("revenue_max_usd", sa.BigInteger),
        sa.Column("buyer_personas", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("buying_signals", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("keywords", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("excluded_keywords", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("tech_stack_required", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("tech_stack_excluded", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("weights", postgresql.JSONB, server_default="{}"),
        sa.Column("raw_ai_response", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- companies ------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("icp_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("icps.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("domain", sa.String(300)),
        sa.Column("website", sa.String(500)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("description", sa.Text),
        sa.Column("industry", sa.String(200)),
        sa.Column("sub_industries", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("employee_count", sa.BigInteger),
        sa.Column("employee_range", sa.String(40)),
        sa.Column("revenue_usd", sa.BigInteger),
        sa.Column("revenue_range", sa.String(40)),
        sa.Column("country", sa.String(80)),
        sa.Column("region", sa.String(80)),
        sa.Column("city", sa.String(120)),
        sa.Column("founded_year", sa.Integer),
        sa.Column("tech_stack", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("socials", postgresql.JSONB, server_default="{}"),
        sa.Column("enriched", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("pipeline_stage", sa.String(20), nullable=False, server_default="new"),
        sa.Column("source", sa.String(40)),
        sa.Column("last_enriched_at", sa.DateTime(timezone=True)),
        sa.Column("embedding", Vector(1536)),
        sa.Column("embedding_pending", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("raw", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_companies_org_domain", "companies", ["organization_id", "domain"], unique=True)
    op.create_index("ix_companies_org_name_trgm", "companies", ["organization_id", "name"])
    op.create_index("ix_companies_industry", "companies", ["industry"])
    op.create_index("ix_companies_country", "companies", ["country"])
    op.create_index("ix_companies_pipeline_stage", "companies", ["pipeline_stage"])
    op.create_index("ix_companies_embedding_pending", "companies", ["embedding_pending"])

    # --- contacts -------------------------------------------------------------
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("title", sa.String(200)),
        sa.Column("seniority", sa.String(40)),
        sa.Column("department", sa.String(80)),
        sa.Column("email", sa.String(320)),
        sa.Column("email_status", sa.String(20)),
        sa.Column("email_confidence", sa.Integer),
        sa.Column("email_validated_at", sa.DateTime(timezone=True)),
        sa.Column("phone", sa.String(40)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("location", sa.String(200)),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("tags", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("raw", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_contacts_company_email", "contacts", ["company_id", "email"])
    op.create_index("ix_contacts_title", "contacts", ["title"])

    # --- signals --------------------------------------------------------------
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(40), nullable=False, index=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("severity", sa.Float, server_default="0.5"),
        sa.Column("confidence", sa.Float, server_default="0.7"),
        sa.Column("url", sa.String(1000)),
        sa.Column("source", sa.String(40)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("payload", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_signals_company_kind_time", "signals", ["company_id", "kind", "observed_at"])

    # --- lead_scores ----------------------------------------------------------
    op.create_table(
        "lead_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("icp_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("icps.id", ondelete="SET NULL")),
        sa.Column("score", sa.Integer, nullable=False, index=True),
        sa.Column("grade", sa.String(4), nullable=False),
        sa.Column("probability", sa.Float, server_default="0"),
        sa.Column("fit_score", sa.Integer, server_default="0"),
        sa.Column("funding_score", sa.Integer, server_default="0"),
        sa.Column("hiring_score", sa.Integer, server_default="0"),
        sa.Column("growth_score", sa.Integer, server_default="0"),
        sa.Column("tech_match_score", sa.Integer, server_default="0"),
        sa.Column("email_score", sa.Integer, server_default="0"),
        sa.Column("activity_score", sa.Integer, server_default="0"),
        sa.Column("reasoning", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("suggested_offer", sa.Text),
        sa.Column("suggested_contact_title", sa.String(200)),
        sa.Column("pain_points", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("raw", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_lead_scores_company_icp", "lead_scores", ["company_id", "icp_id"])

    # --- campaigns / emails ---------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("objective", sa.Text),
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("settings", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "email_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.id", ondelete="CASCADE")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.Column("step", sa.Integer, server_default="1"),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("channel", sa.String(20), server_default="email"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("replied_at", sa.DateTime(timezone=True)),
        sa.Column("open_count", sa.Integer, server_default="0"),
        sa.Column("click_count", sa.Integer, server_default="0"),
        sa.Column("meta", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- crm ------------------------------------------------------------------
    op.create_table(
        "crm_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("payload", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "crm_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("priority", sa.Integer, server_default="2"),
        sa.Column("is_done", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- workflows ------------------------------------------------------------
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("enabled", sa.Boolean, server_default=sa.true()),
        sa.Column("schedule", sa.String(40), server_default="manual"),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("steps", postgresql.JSONB, server_default="[]"),
        sa.Column("settings", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text),
        sa.Column("step_results", postgresql.JSONB, server_default="[]"),
        sa.Column("items_in", sa.Integer, server_default="0"),
        sa.Column("items_out", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- subscriptions --------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("stripe_customer_id", sa.String(64), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(64)),
        sa.Column("price_id", sa.String(64)),
        sa.Column("plan", sa.String(32), server_default="free"),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean, server_default=sa.false()),
        sa.Column("seats", sa.Integer, server_default="1"),
        sa.Column("raw", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # HNSW index on embedding for ANN search. HNSW supports the full 3072-dim vector
    # (IVFFLAT caps at 2000 dims). Build is incremental — safe to create on empty table.
    op.execute(
        "CREATE INDEX ix_companies_embedding_hnsw ON companies "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    for t in [
        "subscriptions", "workflow_runs", "workflows", "crm_tasks", "crm_activities",
        "email_messages", "campaigns", "lead_scores", "signals", "contacts", "companies",
        "icps", "projects", "organization_members", "users", "organizations",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
