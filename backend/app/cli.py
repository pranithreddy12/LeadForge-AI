"""Tiny CLI:
    python -m app.cli seed    populate demo data
    python -m app.cli keys    show which external API keys are LIVE vs demo
"""
from __future__ import annotations

import sys

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models.company import Company
from app.models.icp import ICP
from app.models.project import Project
from app.models.tenant import Organization, OrganizationMember, User

configure_logging()
log = get_logger("cli")


# Per-provider key validators — each returns True iff the key looks real
# (not empty, not a placeholder ending in xxx/placeholder, and roughly the
# right shape). Used by `keys` command and the demo-mode gates.
KEY_CHECKS: dict[str, tuple[str, callable]] = {
    "openai":      ("openai_api_key",       lambda k: k.startswith("sk-")  and len(k) > 30),
    "gemini":      ("gemini_api_key",       lambda k: len(k) > 20),
    "mistral":     ("mistral_api_key",      lambda k: len(k) > 20),
    "tavily":      ("tavily_api_key",       lambda k: k.startswith("tvly-") and len(k) > 20),
    "serper":      ("serper_api_key",       lambda k: len(k) >= 32 and all(c.isalnum() for c in k)),
    "hunter":      ("hunter_api_key",       lambda k: len(k) >= 32 and all(c.isalnum() for c in k)),
    "neverbounce": ("neverbounce_api_key",  lambda k: len(k) >= 24),
    "clerk":       ("clerk_secret_key",     lambda k: k.startswith("sk_")  and len(k) > 30),
    "stripe":      ("stripe_secret_key",    lambda k: k.startswith("sk_")  and len(k) > 30),
    "gmail":       ("gmail_app_password",   lambda k: len(k) >= 12),
    "telegram":    ("telegram_bot_token",   lambda k: ":" in k and len(k) > 20),
}


def keys() -> None:
    """Report LIVE vs demo for every external API key."""
    print(f"{'provider':12}  {'status':6}  {'env_var':24}  detail")
    print("-" * 70)
    for name, (attr, ok) in KEY_CHECKS.items():
        raw = (getattr(settings, attr, "") or "").strip()
        is_placeholder = (
            not raw
            or raw.endswith("xxx")
            or raw.endswith("placeholder")
            or raw == "change-me"
        )
        live = (not is_placeholder) and ok(raw)
        status = "LIVE" if live else "demo"
        detail = f"len={len(raw)}" if raw else "unset"
        if raw and not live and not is_placeholder:
            detail += " (looks malformed)"
        print(f"  {name:10}  {status:6}  {attr.upper():24}  {detail}")


def seed():
    db = SessionLocal()
    try:
        org = Organization(clerk_org_id="org_demo", name="Demo Co", slug="demo", plan="growth")
        user = User(clerk_user_id="user_demo", email="founder@demo.co", name="Demo Founder")
        db.add(org)
        db.add(user)
        db.flush()
        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="owner"))

        project = Project(
            organization_id=org.id, created_by_id=user.id,
            name="QA Automation Agency",
            business_description="We are a QA automation agency selling test-automation engagements.",
        )
        db.add(project)
        db.flush()

        icp = ICP(
            project_id=project.id, name="SaaS scale-ups",
            summary="Series A/B SaaS in NA hiring QA roles.",
            industries=["SaaS", "Fintech", "Healthcare"],
            countries=["USA", "UK", "Canada"],
            employee_min=20, employee_max=500,
            buyer_personas=["CTO", "VP Engineering", "QA Manager"],
            buying_signals=["Hiring QA Engineers", "Recent Funding", "Mobile App Launch"],
            keywords=["QA engineer", "test automation", "SDET"],
            weights={"hiring": 1.6, "funding": 1.3, "growth": 1.1, "tech_match": 1.0},
        )
        db.add(icp)
        db.flush()

        for name, dom in [
            ("Acme Cloud", "acmecloud.com"),
            ("Northwind Health", "northwindhealth.com"),
            ("Globex Fintech", "globexfin.com"),
        ]:
            db.add(Company(
                organization_id=org.id, project_id=project.id, icp_id=icp.id,
                name=name, domain=dom, website=f"https://{dom}",
                industry="SaaS", employee_count=120, country="USA",
                pipeline_stage="new", source="seed",
            ))

        db.commit()
        log.info("seed_done", org=org.slug)
    finally:
        db.close()


def daily_workflow(icp_name_contains: str = "Automation") -> None:
    """Create (or refresh) a daily lead-gen workflow for the demo org, wired to
    the first ICP whose name contains `icp_name_contains`."""
    from app.models.icp import ICP
    from app.models.project import Project
    from app.models.workflow import Workflow

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "demo").first()
        if not org:
            print("no demo org — run `seed` first")
            return
        icp = (
            db.query(ICP).join(Project, Project.id == ICP.project_id)
            .filter(Project.organization_id == org.id, ICP.name.ilike(f"%{icp_name_contains}%"))
            .order_by(ICP.created_at.desc()).first()
        )
        if not icp:
            print(f"no ICP matching {icp_name_contains!r}")
            return

        steps = [
            {"id": "discover", "type": "discover_companies",
             "config": {"icp_id": str(icp.id), "limit": 10}, "next": ["enrich"]},
            {"id": "enrich", "type": "enrich", "config": {}, "next": ["signals"]},
            {"id": "signals", "type": "detect_signals", "config": {}, "next": ["score"]},
            {"id": "score", "type": "score_leads",
             "config": {"icp_id": str(icp.id)}, "next": ["filter"]},
            {"id": "filter", "type": "filter",
             "config": {"min_score": 65, "enforce_icp_size": True,
                        "icp_id": str(icp.id)}, "next": ["draft"]},
            {"id": "draft", "type": "generate_outreach",
             "config": {"channel": "email"}, "next": ["send"]},
            {"id": "send", "type": "send_emails", "config": {}, "next": ["crm"]},
            {"id": "crm", "type": "add_to_crm",
             "config": {"stage": "contacted"}, "next": ["notify"]},
            {"id": "notify", "type": "notify_telegram", "config": {}, "next": []},
        ]
        existing = db.query(Workflow).filter(
            Workflow.organization_id == org.id,
            Workflow.name == "Daily lead engine",
        ).first()
        if existing:
            existing.steps = steps
            existing.schedule = "daily"
            existing.enabled = True
            existing.settings = {"icp_id": str(icp.id)}
            wf = existing
        else:
            wf = Workflow(
                organization_id=org.id, project_id=icp.project_id,
                name="Daily lead engine",
                description="Find 10 leads, enrich, score, draft + send outreach, Telegram summary.",
                schedule="daily", enabled=True, steps=steps,
                settings={"icp_id": str(icp.id)},
            )
            db.add(wf)
        db.commit()
        log.info("daily_workflow_ready", workflow=str(wf.id), icp=icp.name)
        print(f"daily workflow ready (id={wf.id}) wired to ICP: {icp.name}")
    finally:
        db.close()


COMMANDS = {"seed": seed, "keys": keys, "daily-workflow": daily_workflow}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print("usage: python -m app.cli {seed|keys}")
