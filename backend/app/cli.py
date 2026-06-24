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


def _bar(label: str, value: float, width: int = 24) -> str:
    filled = int(round(value * width))
    return f"{label:22} [{'#' * filled}{'.' * (width - filled)}] {value * 100:5.1f}%"


def evaluate() -> None:
    """Golden-set eval: qualification precision/recall + scoring grade-band accuracy.
    Pass --no-llm for a deterministic gate-only run (skips the AI classifier/scorer)."""
    from app.ai.eval import run_all
    use_llm = "--no-llm" not in sys.argv
    print(f"\nLeadForge golden-set eval  (llm={'on' if use_llm else 'OFF'})")
    res = run_all(use_llm=use_llm)

    q = res["qualification"]
    h, comb = q["heuristic_only"], q["combined"]
    print("\n" + "=" * 70)
    print(f"QUALIFICATION GATE  (n={q['n']}, buyers={h['true_buyers']})")
    print("-" * 70)
    print("  (a) HEURISTIC-ONLY (deterministic floor, no LLM):")
    print("   " + _bar("buyer precision", h["precision"]))
    print("   " + _bar("buyer recall", h["recall"]))
    print("  (b) HEURISTIC + LLM (ceiling):")
    print("   " + _bar("buyer precision", comb["precision"]))
    print("   " + _bar("buyer recall", comb["recall"]))
    lift_pp = q["lift_precision"] * 100
    verdict = ("LLM ESSENTIAL — heuristics alone can't catch in-band vendor/VC/competitor"
               if lift_pp >= 10 else "heuristics carry it; LLM call could be optional")
    print(f"  LLM precision lift: {lift_pp:+.1f} pp   ({verdict})")
    print(f"  [b] accepted-as-buyer: {comb['pred_buyers']}   TP: {comb['tp']}   FP: {comb['fp']}")
    if comb["fp_by_archetype"]:
        print("  FALSE POSITIVES by archetype (non-buyers leaking through as buyer):")
        for arch, n in sorted(comb["fp_by_archetype"].items(), key=lambda x: -x[1]):
            print(f"    - {arch:26} {n}")
    else:
        print("  FALSE POSITIVES by archetype: none")
    print("  REJECT rate by archetype (caught / total):")
    for arch, d in sorted(q["reject_by_archetype"].items()):
        print(f"    - {arch:26} {d['caught']}/{d['total']}")

    print("\n  per-row decisions:")
    print(f"    {'company':26} {'expected':22} {'predicted':16} why")
    for r in q["per_row"]:
        flag = "  " if (r["predicted"] == "buyer") == (r["expected"] == "buyer") else "!!"
        print(f"  {flag}{r['name'][:24]:26} {r['expected']:22} {r['predicted']:16} {r['why']}")

    s = res["scoring"]
    print("\n" + "=" * 70)
    print("SCORING  (deterministic / heuristic-only — repeatable baseline)")
    print("-" * 70)
    print(f"  BUYER SEPARATION  buyers outranking every off-size firm "
          f"(>{s['highest_offsize_score']}): {s['buyer_separation_pass']}/{s['n_buyers']} pass")
    print(f"  OFF-SIZE GUARD    too_large below B AND below lowest buyer "
          f"(={s['lowest_buyer_score']}): {s['offsize_guard_pass']}/{s['n_too_large']} pass")
    print(f"  (informational)   buyer letter-band match: {s['buyer_band_informational'] * 100:.0f}%"
          f"  — backbone is compressed; production LLM lifts ~1 band, see live proof")
    print("\n  per-row scores:")
    print(f"    {'company':26} {'label':12} {'emp':>7} {'score':>5} {'grade':>5} {'band':>6} ok")
    for r in s["per_row"]:
        extra = f"  margin={r['margin']}" if "margin" in r else ""
        print(f"  {'!!' if not r['ok'] else '  '}{r['name'][:24]:26} {r['label']:12} "
              f"{str(r['emp']):>7} {r['score']:>5} {r['grade']:>5} {r['expected_band']:>6} "
              f"{'y' if r['ok'] else 'N'}{extra}")
    print("\n" + "=" * 70)
    print("BASELINE captured. Phases 1B-1D must beat: buyer precision up, FP-by-archetype down.")
    print("=" * 70 + "\n")


def discovery_eval() -> None:
    """Compare topic-keyword queries (BEFORE) vs intent-angle queries (AFTER) on a
    real search+gate run. Reports buyer-share and LLM-classifications-per-buyer."""
    from sqlalchemy import select

    from app.ai.qualification_engine import classify_candidates
    from app.ai.query_engine import generate_intent_queries
    from app.core.database import SessionLocal
    from app.models.icp import ICP
    from app.services.discovery import _collect, _template_queries
    from app.services.search import serper_search, tavily_search

    db = SessionLocal()
    try:
        icp = db.execute(select(ICP).where(ICP.name.ilike("%Automation%"))
                         .order_by(ICP.created_at.desc())).scalars().first()
        if not icp:
            print("no Automation ICP — run seed/ICP gen first")
            return
        seller = ""
        if icp.project is not None:
            seller = icp.project.business_description or ""
            if icp.project.target_offering:
                seller += f"\nOffering: {icp.project.target_offering}"
        icp_dict = {"industries": icp.industries, "buyer_personas": icp.buyer_personas,
                    "buying_signals": icp.buying_signals, "countries": icp.countries,
                    "keywords": icp.keywords, "employee_min": icp.employee_min,
                    "employee_max": icp.employee_max}

        from app.services.serp_filter import process_hit

        topic_q = [("topic", q) for q in _template_queries(icp, [])]
        intent_q = [(i["angle"], i["query"]) for i in
                    generate_intent_queries(business_description=seller, icp=icp_dict, limit=10)]

        def run_pool(labeled_queries, *, drop_junk, extract, cap=12):
            raw: dict = {}
            for _angle, q in labeled_queries:
                for hit in tavily_search(q, max_results=6):
                    c = process_hit(title=hit.get("title"), url=hit.get("url"),
                                    snippet=hit.get("content"), source="tavily",
                                    drop_junk=drop_junk, extract=extract)
                    if c and c.domain and c.domain not in raw:
                        raw[c.domain] = c
                for hit in serper_search(q, max_results=6):
                    c = process_hit(title=hit.get("title"), url=hit.get("link"),
                                    snippet=hit.get("snippet"), source="serper",
                                    drop_junk=drop_junk, extract=extract)
                    if c and c.domain and c.domain not in raw:
                        raw[c.domain] = c
                if len(raw) >= cap:
                    break
            cands = list(raw.values())[:cap]
            judged = classify_candidates(cands, seller_description=seller)
            buyers = [j for j in judged if j["label"] == "buyer"]
            llm_routed = [j for j in judged if j["source"] in ("llm", "provider_error")]
            extracted = sum(1 for c in cands if c.signal)
            return cands, judged, buyers, llm_routed, extracted

        rows = [
            ("(1) BASELINE  topic-keyword, raw collect", topic_q, False, False),
            ("(2) 1C+drop  intent-angle, defensive drop", intent_q, True, False),
            ("(3) 1C+extract  intent-angle, drop + EXTRACT (target)", intent_q, True, True),
        ]
        for name, labeled, drop, extract in rows:
            print("\n" + "=" * 70)
            print(f"{name}")
            print("-" * 70)
            cands, judged, buyers, llm_routed, extracted = run_pool(
                labeled, drop_junk=drop, extract=extract)
            n = len(cands) or 1
            print(f"  candidates: {len(cands)}   pre-signaled(extracted): {extracted}")
            print(f"  buyers: {len(buyers)}  ({len(buyers) / n * 100:.0f}% buyer-share)")
            print(f"  LLM-classifications/buyer: "
                  f"{len(llm_routed) / max(1, len(buyers)):.1f}  ({len(llm_routed)} LLM / {len(buyers)} buyers)")
            mix: dict = {}
            for j in judged:
                mix[j["label"]] = mix.get(j["label"], 0) + 1
            print(f"  label mix: {mix}")
        print("\n" + "=" * 70)
        print("Row (3) is the target: extraction turns funding-news/job-posts into pre-")
        print("signaled buyer candidates -> higher buyer-share, fewer LLM calls per buyer.")
        print("=" * 70 + "\n")
    finally:
        db.close()


def outreach_dryrun() -> None:
    """Exercise the FULL outreach path — suppression, cap check, draft, Message-ID
    stamping — WITHOUT sending. Shows, per company: suppression status (+ why), send-cap
    headroom, and the exact email that would be sent (subject, first line, Message-ID)."""
    from sqlalchemy import select

    from app.ai.outreach_engine import generate_outreach
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models.company import Company
    from app.models.contact import Contact
    from app.models.icp import ICP
    from app.models.signal import Signal
    from app.services.email_sender import (daily_cap_remaining, stamp_message_id,
                                           suppression_reason)

    TEST_RECIPIENT = "pranithredy3207@gmail.com"  # dry-run only; nothing is sent
    db = SessionLocal()
    try:
        icp = db.execute(select(ICP).where(ICP.name.ilike("%Automation%"))
                         .order_by(ICP.created_at.desc())).scalars().first()
        pool = db.execute(select(Company).where(Company.icp_id == icp.id)
                          .order_by(Company.name)).scalars().all()
        org_id = icp.project.organization_id if icp.project else (pool[0].organization_id if pool else None)

        per_run = settings.max_emails_per_run
        daily_remaining = daily_cap_remaining(db, org_id)
        would_send = 0
        print("\n" + "=" * 74)
        print(f"OUTREACH DRY-RUN  (NO SEND)  pool={len(pool)}  "
              f"per-run cap={per_run}  daily cap={settings.max_emails_per_day} "
              f"(remaining today={daily_remaining})")
        print("=" * 74)
        for co in pool:
            contact = db.execute(select(Contact).where(Contact.company_id == co.id)
                                 .order_by(Contact.is_primary.desc())).scalars().first()
            print(f"\n- {co.name}  ({co.domain})  stage={co.pipeline_stage} "
                  f"class={co.classification_status or 'buyer'}")
            reason = suppression_reason(db, co, contact)
            if reason:
                print(f"    SUPPRESSED -> {reason}")
                continue
            headroom = min(per_run - would_send, daily_remaining - would_send)
            if headroom <= 0:
                print(f"    CAP REACHED -> would defer (per-run {would_send}/{per_run}, "
                      f"daily {would_send}/{daily_remaining} used)")
                continue
            # Real draft + real Message-ID stamping (the actual send-path helper).
            signals = db.execute(select(Signal).where(Signal.company_id == co.id).limit(15)).scalars().all()
            raw = generate_outreach(company=_rowdict(co), contact=_rowdict(contact),
                                    icp=_rowdict(icp), signals=[_rowdict(s) for s in signals],
                                    channel="email", tone="concise")
            variants = raw.get("variants") or []
            if not variants:
                print("    NO DRAFT (provider error or empty) -> skipped, nothing persisted")
                continue
            v = variants[0]
            mid = stamp_message_id()
            to_addr = (contact.email if contact and contact.email else TEST_RECIPIENT)
            first_line = (v.get("body") or "").strip().splitlines()[0][:90] if v.get("body") else "(empty)"
            would_send += 1
            print(f"    WOULD SEND  (cap headroom {min(per_run, daily_remaining) - would_send} left)")
            print(f"      to:         {to_addr}")
            print(f"      subject:    {v.get('subject')}")
            print(f"      first line: {first_line}")
            print(f"      Message-ID: {mid}")
        print("\n" + "=" * 74)
        print(f"DRY-RUN COMPLETE — would send {would_send}, NOTHING sent, nothing persisted.")
        print("=" * 74 + "\n")
    finally:
        db.close()


def _rowdict(r):
    return {c.key: getattr(r, c.key) for c in r.__table__.columns} if r else None


COMMANDS = {"seed": seed, "keys": keys, "daily-workflow": daily_workflow,
            "eval": evaluate, "discovery-eval": discovery_eval,
            "outreach-dryrun": outreach_dryrun}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print("usage: python -m app.cli {seed|keys}")
