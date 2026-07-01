"""Workflow runner — interprets a Workflow's step graph.

A step is shaped like:

    {"id": "discover_1", "type": "discover_companies",
     "config": {"icp_id": "<uuid>", "limit": 20},
     "next": ["signals_1"]}

Supported types (see app.schemas.workflow.StepType):

  discover_companies     find companies for an ICP (Tavily + Serper)
  detect_signals         per-company signal sweep
  find_contacts          per-company contact discovery
  validate_emails        per-contact validation
  score_leads            score every discovered/imported company
  generate_outreach      draft first-touch email/LinkedIn
  filter                 narrow context.companies by predicate
  add_to_crm             move qualifying companies to a pipeline stage
  webhook                POST run summary to a URL
  wait                   sleep N seconds (test/development)

Context flowing through the run:

    {
        "icp_id": <uuid>,
        "company_ids": [<uuid>, ...],
        "contact_ids": [<uuid>, ...],
        "step_log": [...],
    }
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

import httpx
from celery import shared_task
from sqlalchemy import func, select

from app.ai.opportunity_engine import analyze_opportunity  # noqa: F401  -- used indirectly
from app.core.logging import get_logger
from app.models.company import Company
from app.models.contact import Contact
from app.models.icp import ICP
from app.models.workflow import Workflow, WorkflowRun
from app.services.contacts import discover_contacts_for_company, validate_and_store
from app.services.discovery import discover_via_search, persist_candidates
from app.services.scoring import score_company
from app.services.signals import detect_for_company
from app.workers._base import task_session
from app.workers.outreach import draft_outreach_for_company

log = get_logger("workers.workflows")


# ---- step handlers ----------------------------------------------------------


def _step_discover_local(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """Local-SMB discovery via Google Places, driven by Settings (Step 5). Nothing-
    static: no Places key -> empty result, logged, no crash."""
    from app.services.discovery import discover_local_businesses
    from app.services.icp import get_active_icp
    from app.services.settings_resolver import resolve_credential, settings_row
    s = settings_row(db, org_id)
    icp = get_active_icp(db, org_id)
    if s is None or icp is None:
        return {"company_ids": ctx.get("company_ids", []), "delta": 0,
                "error": "no_settings_or_icp"}
    key = resolve_credential(db, org_id, "google_places_api_key")
    if not key:
        log.info("discover_local_no_places_key")
        return {"company_ids": ctx.get("company_ids", []), "delta": 0, "no_places_key": True}
    seller = ""
    if icp.project is not None:
        seller = icp.project.business_description or ""
    rows, stats = discover_local_businesses(
        db, organization_id=org_id, icp=icp,
        business_types=s.target_business_types or [], locations=s.target_locations or [],
        min_reviews=s.min_reviews, max_results=s.max_results_per_run,
        api_key=key, seller_description=seller)
    buyer_rows = [r for r in rows if r.classification_status in (None, "buyer")]
    company_ids = ctx.get("company_ids", []) + [str(r.id) for r in buyer_rows]
    return {"company_ids": company_ids, "delta": len(buyer_rows), "places_stats": stats}


def _step_discover(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    # Mode-aware (Step 4): Settings.discovery_mode == "local" -> Google Places instead
    # of web search. Same DAG, the handler reads Settings.
    from app.services.settings_resolver import settings_row
    s = settings_row(db, org_id)
    if s is not None and s.discovery_mode == "local":
        return _step_discover_local(db, org_id, ctx, config)
    # B2B discovery uses the org's SINGLE active ICP (synced from Settings) — no more
    # name-matched / hardcoded icp_id. Config/ctx icp_id is only a fallback.
    from app.services.icp import get_active_icp
    icp = get_active_icp(db, org_id)
    if icp is None:
        icp_id = config.get("icp_id") or ctx.get("icp_id")
        icp = db.get(ICP, uuid.UUID(str(icp_id))) if icp_id else None
    if icp is None:
        return {"company_ids": ctx.get("company_ids", []), "delta": 0,
                "error": "no_active_icp"}
    limit = int(config.get("limit", 25))
    cands = discover_via_search(icp, limit=limit, extra_keywords=config.get("keywords"))
    rows = persist_candidates(db, organization_id=org_id, icp=icp, candidates=cands)
    # Held-unknown rows are persisted (retry-able, suppressible) but kept OUT of the
    # scoring/outreach pipeline until confirmed as buyers.
    buyer_rows = [r for r in rows if r.classification_status is None]
    held = len(rows) - len(buyer_rows)
    company_ids = ctx.get("company_ids", []) + [str(r.id) for r in buyer_rows]
    return {"company_ids": company_ids, "delta": len(buyer_rows), "held_unknown": held}


def _step_discover_places(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """Local-SMB discovery via Google Places (compliant). config: icp_id, limit,
    optional queries[]. Held-unknown filtering not needed (Places results are real
    verified businesses, not noisy SERP candidates)."""
    from app.services.discovery import discover_via_places
    icp_id = uuid.UUID(config.get("icp_id") or ctx["icp_id"])
    icp = db.get(ICP, icp_id)
    cands = discover_via_places(icp, limit=int(config.get("limit", 20)),
                                queries=config.get("queries"))
    rows = persist_candidates(db, organization_id=org_id, icp=icp, candidates=cands)
    company_ids = ctx.get("company_ids", []) + [str(r.id) for r in rows]
    return {"company_ids": company_ids, "delta": len(rows), "source": "places"}


def _step_enrich(db, org_id: uuid.UUID, ctx: dict, _config: dict) -> dict:
    """Fill firmographics (employee_count, revenue, funding, HQ) before scoring,
    so size/fit filtering has real data to work with."""
    from app.services.enrichment import enrich_company
    n = 0
    for cid in ctx.get("company_ids", []):
        c = db.get(Company, uuid.UUID(cid))
        if c:
            try:
                enrich_company(db, c)
                n += 1
            except Exception as e:
                log.warning("enrich_failed", error=str(e), company_id=cid)
    return {"enriched": n}


def _step_detect_local_signals(db, org_id: uuid.UUID, ctx: dict, _config: dict) -> dict:
    """Review/website-based signals for local businesses (Step 6)."""
    from app.services.local_signals import detect_local_signals
    n = 0
    for cid in ctx.get("company_ids", []):
        c = db.get(Company, uuid.UUID(cid))
        if c:
            n += len(detect_local_signals(db, c))
    return {"signals_created": n, "kind": "local"}


def _step_signals(db, org_id: uuid.UUID, ctx: dict, _config: dict) -> dict:
    # Mode-aware: local businesses get review/website signals, not web/funding signals.
    from app.services.settings_resolver import settings_row
    s = settings_row(db, org_id)
    if s is not None and s.discovery_mode == "local":
        return _step_detect_local_signals(db, org_id, ctx, _config)
    n = 0
    for cid in ctx.get("company_ids", []):
        c = db.get(Company, uuid.UUID(cid))
        if c:
            icp = db.get(ICP, c.icp_id) if c.icp_id else None
            sigs = detect_for_company(db, c, (icp.keywords or []) if icp else [])
            n += len(sigs)
    return {"signals_created": n}


def _step_contacts(db, org_id: uuid.UUID, ctx: dict, _config: dict) -> dict:
    new_ids: list[str] = []
    for cid in ctx.get("company_ids", []):
        c = db.get(Company, uuid.UUID(cid))
        if c:
            for k in discover_contacts_for_company(db, c):
                new_ids.append(str(k.id))
    ctx_contacts = ctx.get("contact_ids", []) + new_ids
    return {"contact_ids": ctx_contacts, "delta": len(new_ids)}


def _step_validate_emails(db, org_id: uuid.UUID, ctx: dict, _config: dict) -> dict:
    # Settings-gated: skip validation entirely when turned off.
    from app.services.settings_resolver import pipeline_config
    if not pipeline_config(db, org_id)["validate_emails"]:
        return {"validated": 0, "skipped": "disabled_in_settings"}
    n = 0
    ids = ctx.get("contact_ids") or []
    if not ids:
        ids = [
            str(i) for i in db.execute(
                select(Contact.id).where(
                    Contact.organization_id == org_id,
                    Contact.email.is_not(None),
                    Contact.email_status.is_(None),
                )
            ).scalars().all()
        ]
    for cid in ids:
        if validate_and_store(db, uuid.UUID(cid)):
            n += 1
    return {"validated": n}


def _step_score(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    icp_id = uuid.UUID(config.get("icp_id") or ctx["icp_id"])
    company_ids = ctx.get("company_ids") or []
    scored = 0
    grades: dict[str, int] = {}
    for cid in company_ids:
        try:
            s = score_company(db, organization_id=org_id, company_id=uuid.UUID(cid),
                              icp_id=icp_id, with_opportunity=False)
            grades[s.grade] = grades.get(s.grade, 0) + 1
            scored += 1
        except Exception as e:
            log.warning("score_failed", error=str(e), company_id=cid)
    return {"scored": scored, "by_grade": grades}


def _step_outreach(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    channel = config.get("channel", "email")
    n = 0
    for cid in ctx.get("company_ids", []):
        # Run synchronously (not .delay) so drafts exist in the DB before a
        # following send_emails step runs in the same workflow.
        draft_outreach_for_company(str(org_id), cid, channel=channel)
        n += 1
    return {"drafted": n}


def _step_send_emails(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """Send the draft emails for this workflow's companies via Gmail, within caps.
    Honors Settings.outreach_send_mode: in 'manual' mode this is a NO-OP — drafts are
    left for human review + send on /today (nothing auto-sends)."""
    from app.core.config import settings
    from app.models.campaign import EmailMessage
    from app.services.email_sender import daily_cap_remaining, send_email_message
    from app.services.settings_resolver import outreach_send_mode
    if outreach_send_mode(db, org_id) == "manual":
        log.info("send_emails_skipped_manual_mode", org=str(org_id))
        return {"sent": 0, "mode": "manual", "note": "drafts left for /today review"}
    company_ids = [uuid.UUID(c) for c in ctx.get("company_ids", [])]
    if not company_ids:
        return {"sent": 0}
    drafts = db.execute(
        select(EmailMessage).where(
            EmailMessage.organization_id == org_id,
            EmailMessage.company_id.in_(company_ids),
            EmailMessage.status == "draft",
            EmailMessage.channel == "email",
        )
    ).scalars().all()

    # Caps enforced BEFORE any send attempt — from Settings (else .env).
    from app.services.settings_resolver import resolve_caps
    res_run, res_day = resolve_caps(db, org_id)
    per_run = int(config.get("max_per_run") or res_run)
    budget = min(per_run, daily_cap_remaining(db, org_id))
    sent = capped = 0
    sent_ids: list[str] = []   # companies with a CONFIRMED send — the only ones add_to_crm may advance
    for m in drafts:
        if sent >= budget:
            capped += 1
            continue
        if send_email_message(db, m).get("sent"):
            sent += 1
            if m.company_id:
                sent_ids.append(str(m.company_id))
                _annotate_lead(ctx, m.company_id, outreach_channel="email",
                               outreach_status="sent")
    return {"sent": sent, "sent_company_ids": sent_ids, "drafts": len(drafts),
            "skipped_by_cap": capped, "per_run_cap": per_run,
            "daily_cap": settings.max_emails_per_day}


def _annotate_lead(ctx: dict, company_id, **fields) -> None:
    """Record per-lead facts a step knows (filter pass, outreach channel/status,
    suppression reason) into ctx['lead_meta'] for the end-of-run run_leads assembly."""
    meta = ctx.setdefault("lead_meta", {})
    meta.setdefault(str(company_id), {}).update({k: v for k, v in fields.items()
                                                 if v is not None})


def build_run_leads(db, org_id: uuid.UUID, ctx: dict) -> list[dict]:
    """Assemble per-lead detail for the run from the DB + the step annotations in
    ctx['lead_meta']. One object per company the run touched — powers the Runs
    dashboard funnel + lead audit."""
    from app.ai.outreach_engine import _extract_city
    from app.models.scoring import LeadScore
    from app.models.signal import Signal
    from app.services.email_sender import suppression_reason

    all_ids = ctx.get("_all_company_ids") or list(ctx.get("company_ids") or [])
    final_passed = {str(c) for c in (ctx.get("company_ids") or [])}
    lead_meta = ctx.get("lead_meta") or {}
    out: list[dict] = []
    seen: set[str] = set()
    for cid in all_ids:
        cid = str(cid)
        if cid in seen:
            continue
        seen.add(cid)
        company = db.get(Company, uuid.UUID(cid))
        if company is None:
            continue
        meta = lead_meta.get(cid, {})
        sc = db.execute(
            select(LeadScore.score, LeadScore.grade)
            .where(LeadScore.company_id == company.id)
            .order_by(LeadScore.created_at.desc()).limit(1)
        ).first()
        score = int(sc[0]) if sc and sc[0] is not None else None
        grade = sc[1] if sc else None
        sig_kinds = list(db.execute(
            select(Signal.kind).where(Signal.company_id == company.id).distinct()
        ).scalars().all())
        # filter_passed: a step recorded it, else infer from the final working set.
        filter_passed = meta.get("filter_passed")
        if filter_passed is None:
            filter_passed = cid in final_passed
        outreach_status = meta.get("outreach_status")
        if company.pipeline_stage == "replied":
            outreach_status = "replied"
        supp = meta.get("suppression_reason")
        if supp is None and meta.get("outreach_channel") is None:
            supp = suppression_reason(db, company)
        out.append({
            "company_id": cid,
            "company_name": company.name,
            "city": _extract_city({"name": company.name,
                                   "description": company.description,
                                   "raw": company.raw}),
            "score": score,
            "grade": grade,
            "signals": sig_kinds,
            "qualification_label": company.classification_label,
            "filter_passed": bool(filter_passed),
            "outreach_channel": meta.get("outreach_channel"),
            "outreach_status": outreach_status,
            "suppression_reason": supp,
        })
    return out


def _company_signal_dicts(db, company_id: uuid.UUID) -> list[dict]:
    """Real Signal rows for a company as plain dicts (kind/label/severity) for the
    problem-aware message generators — never invented."""
    from app.models.signal import Signal
    rows = db.execute(
        select(Signal).where(Signal.company_id == company_id).limit(15)
    ).scalars().all()
    return [{"kind": s.kind, "label": s.label, "severity": s.severity,
             "description": s.description} for s in rows]


def _step_send_whatsapp(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """WhatsApp-first outreach for the filtered pool. Sequential logic:
      1. suppression (3 base conditions + whatsapp_active) -> skip;
      2. no sendable phone -> email_fallback_ids (immediate email);
      3. generate a problem-aware message from REAL signals;
      4. send via the Meta Cloud API;
      5. on success: WhatsAppMessage row (written by the sender) + stage
         'whatsapp_contacted', record in whatsapp_sent_ids;
      6. on failure: email_fallback_ids.
    Nothing-static: a provider error persists nothing and routes to email fallback."""
    from app.core.config import settings
    from app.ai.outreach_engine import generate_whatsapp_message
    from app.services.email_sender import suppression_reason
    from app.services.settings_resolver import outreach_send_mode, settings_row
    from app.services.whatsapp_sender import (is_configured, normalize_phone,
                                              send_whatsapp)

    if outreach_send_mode(db, org_id) == "manual":
        log.info("send_whatsapp_skipped_manual_mode", org=str(org_id))
        return {"sent": 0, "mode": "manual",
                "note": "manual mode - review/send WhatsApp yourself on /today"}
    company_ids = ctx.get("company_ids", [])
    s = settings_row(db, org_id)
    tone = (s.outreach_tone if s else None) or "professional"
    sender_name = settings.gmail_from_name or "LeadForge"
    configured = is_configured(db, org_id)

    whatsapp_sent_ids: list[str] = []
    email_fallback_ids: list[str] = []
    sent = skipped = no_phone = failed = 0

    for cid in company_ids:
        company = db.get(Company, uuid.UUID(cid))
        if not company:
            continue
        # (1) suppression — includes whatsapp_active so we never double-message.
        reason = suppression_reason(db, company)
        if reason:
            skipped += 1
            _annotate_lead(ctx, cid, outreach_status="suppressed", suppression_reason=reason)
            log.info("whatsapp_suppressed", company=str(company.id), reason=reason)
            continue
        # (2) phone gate.
        phone_raw = (company.raw or {}).get("places", {}).get("phone")
        normalized = normalize_phone(phone_raw)
        if not normalized:
            no_phone += 1
            email_fallback_ids.append(cid)
            _annotate_lead(ctx, cid, outreach_channel="email", outreach_status="no_phone")
            continue
        if not configured:
            # No WhatsApp creds at all -> route to email fallback (no demo send).
            email_fallback_ids.append(cid)
            _annotate_lead(ctx, cid, outreach_channel="email",
                           outreach_status="whatsapp_unconfigured")
            continue
        # (3) problem-aware message from real signals.
        signals = _company_signal_dicts(db, company.id)
        gen = generate_whatsapp_message(
            {"name": company.name, "description": company.description, "raw": company.raw},
            signals, {"tone": tone, "sender_name": sender_name})
        # (4) send.
        res = send_whatsapp(db, organization_id=org_id, to_phone=normalized,
                            body=gen["message"], company_id=company.id)
        if res.get("sent"):
            company.pipeline_stage = "whatsapp_contacted"
            db.commit()
            whatsapp_sent_ids.append(cid)
            sent += 1
            _annotate_lead(ctx, cid, outreach_channel="whatsapp", outreach_status="sent")
        else:
            # (6) provider error / invalid -> email fallback.
            failed += 1
            email_fallback_ids.append(cid)
            _annotate_lead(ctx, cid, outreach_channel="email",
                           outreach_status="whatsapp_failed")

    return {"company_ids": company_ids, "whatsapp_sent_ids": whatsapp_sent_ids,
            "email_fallback_ids": email_fallback_ids, "sent": sent,
            "suppressed": skipped, "no_phone": no_phone, "failed": failed,
            "configured": configured}


def _draft_scheduled_email(db, org_id: uuid.UUID, company: Company,
                           scheduled_at) -> bool:
    """Draft ONE real email for `company` and persist it status='scheduled' with the
    given send time. Bypasses the whatsapp_active guard (this IS the sequence's
    fallback), but still honors the other suppression conditions. Returns True if a
    scheduled row was created. Nothing-static: if the LLM yields no draft, persist
    nothing."""
    from app.models.campaign import EmailMessage
    from app.services.email_sender import suppression_reason
    from app.services.settings_resolver import settings_row
    from app.ai.outreach_engine import generate_outreach

    # Honor real suppressions (already emailed / contacted-or-beyond / held), but NOT
    # whatsapp_active — the fallback is the deliberate next step of the sequence.
    reason = suppression_reason(db, company, check_whatsapp=False)
    if reason:
        log.info("schedule_email_suppressed", company=str(company.id), reason=reason)
        return False

    contact = db.execute(
        select(Contact).where(Contact.company_id == company.id,
                              Contact.email.is_not(None))
        .order_by(Contact.influence_score.desc().nullslast()).limit(1)
    ).scalar_one_or_none() or db.execute(
        select(Contact).where(Contact.company_id == company.id)
        .order_by(Contact.is_primary.desc(), Contact.created_at.desc()).limit(1)
    ).scalar_one_or_none()

    icp = db.get(ICP, company.icp_id) if company.icp_id else None
    signals = _company_signal_dicts(db, company.id)
    s = settings_row(db, org_id)
    is_local = bool(s and s.discovery_mode == "local")
    eff_tone = (s.outreach_tone if s else None) or "concise"

    def _row(r):
        return {c.key: getattr(r, c.key) for c in r.__table__.columns} if r else None

    raw = generate_outreach(company=_row(company), contact=_row(contact), icp=_row(icp),
                            signals=signals, channel="email", tone=eff_tone, local=is_local)
    variants = (raw or {}).get("variants") or []
    if not variants:
        log.info("schedule_email_no_draft", company=str(company.id))
        return False
    v = variants[0]
    msg = EmailMessage(
        organization_id=org_id, company_id=company.id,
        contact_id=contact.id if contact else None,
        subject=v.get("subject") or f"About {company.name}",
        body=v.get("body") or "", channel="email", status="scheduled",
        scheduled_at=scheduled_at,
        meta={"to": contact.email} if (contact and contact.email) else {},
    )
    db.add(msg)
    db.commit()
    return True


def _step_schedule_email_followup(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """Schedule the email leg of the sequence:
      - email_fallback_ids (no phone / send failed) -> email scheduled NOW;
      - whatsapp_sent_ids -> email scheduled 48h LATER (cancelled later if they reply).
    """
    from datetime import timedelta
    now = datetime.utcnow()
    delay_hours = int(config.get("followup_hours", 48))
    immediate = 0
    deferred = 0
    for cid in ctx.get("email_fallback_ids", []):
        c = db.get(Company, uuid.UUID(cid))
        if c and _draft_scheduled_email(db, org_id, c, now):
            immediate += 1
            _annotate_lead(ctx, cid, outreach_channel="email", outreach_status="scheduled")
    for cid in ctx.get("whatsapp_sent_ids", []):
        c = db.get(Company, uuid.UUID(cid))
        if c and _draft_scheduled_email(db, org_id, c, now + timedelta(hours=delay_hours)):
            deferred += 1
            # WhatsApp already sent for these; record the 48h email is queued behind it.
            _annotate_lead(ctx, cid, outreach_channel="whatsapp",
                           outreach_status="sent+email_48h")
    return {"scheduled_immediate": immediate, "scheduled_48h": deferred,
            "followup_hours": delay_hours}


def _step_notify_telegram(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """Send a Telegram summary of this workflow run."""
    from app.models.campaign import EmailMessage
    from app.models.company import Company
    from app.models.scoring import LeadScore
    from app.services import telegram

    company_ids = [uuid.UUID(c) for c in ctx.get("company_ids", [])]
    found = len(company_ids)
    scored = hot = sent = drafted = 0
    top: list[str] = []
    if company_ids:
        rows = db.execute(
            select(Company.name, LeadScore.grade, LeadScore.score)
            .join(LeadScore, LeadScore.company_id == Company.id)
            .where(Company.id.in_(company_ids))
            .order_by(LeadScore.score.desc())
        ).all()
        scored = len(rows)
        hot = sum(1 for _, g, _ in rows if g in ("A+", "A", "B"))
        top = [f"{n} — {g} ({s})" for n, g, s in rows[:5]]
        drafted = db.execute(
            select(func.count(EmailMessage.id)).where(
                EmailMessage.organization_id == org_id,
                EmailMessage.company_id.in_(company_ids),
            )
        ).scalar_one() or 0
        sent = db.execute(
            select(func.count(EmailMessage.id)).where(
                EmailMessage.organization_id == org_id,
                EmailMessage.company_id.in_(company_ids),
                EmailMessage.status == "sent",
            )
        ).scalar_one() or 0
    ok = telegram.notify_daily_summary(found=found, scored=scored, hot=hot,
                                       drafted=drafted, sent=sent, top=top)
    return {"telegram_sent": ok, "found": found, "hot": hot}


def _step_filter(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """Filter the working set of companies.

    config keys: min_score, grades, industries, country, employee_min,
    employee_max, and `enforce_icp_size` (bool) which pulls the size band from
    the run's ICP. Size enforcement hard-drops grossly off-size accounts (e.g. a
    27k-employee giant or a 9-person shop for a 50–1000 ICP) regardless of score
    — being out-of-band is a disqualifier, not just a low score.
    """
    from app.models.scoring import LeadScore
    from app.services.settings_resolver import pipeline_config
    company_ids = ctx.get("company_ids") or []
    if not company_ids:
        return {"company_ids": []}

    # Settings provide the defaults; an explicit step config still overrides them.
    pcfg = pipeline_config(db, org_id)
    min_score = config.get("min_score")
    if min_score is None:
        min_score = pcfg["filter_min_score"]
    enforce_size = config.get("enforce_icp_size")
    if enforce_size is None:
        enforce_size = pcfg["filter_enforce_icp_size"]

    # Resolve size bounds (explicit config wins; else the ICP band if requested).
    emp_min = config.get("employee_min")
    emp_max = config.get("employee_max")
    if enforce_size:
        icp_id = config.get("icp_id") or ctx.get("icp_id")
        icp = db.get(ICP, uuid.UUID(str(icp_id))) if icp_id else None
        if icp:
            emp_min = emp_min if emp_min is not None else icp.employee_min
            emp_max = emp_max if emp_max is not None else icp.employee_max

    # Latest score per company (most recent row wins) — avoids the duplicate-row
    # fan-out an unordered outerjoin produced when a company was re-scored.
    latest: dict[uuid.UUID, tuple[int | None, str | None]] = {}
    score_rows = db.execute(
        select(LeadScore.company_id, LeadScore.score, LeadScore.grade)
        .where(LeadScore.company_id.in_([uuid.UUID(c) for c in company_ids]))
        .order_by(LeadScore.company_id, LeadScore.created_at.desc())
    ).all()
    for cid, score, grade in score_rows:
        latest.setdefault(cid, (score, grade))

    from app.services.leadpool import is_buyer
    out: list[str] = []
    for cid in company_ids:
        company = db.get(Company, uuid.UUID(cid))
        if not company:
            continue
        if not is_buyer(company):   # P1 #9: non-buyer-classified never proceed to outreach
            continue
        score, grade = latest.get(company.id, (None, None))
        if min_score is not None and (score or 0) < int(min_score):
            continue
        if (g := config.get("grades")) and grade not in g:
            continue
        if (ind := config.get("industries")) and company.industry not in ind:
            continue
        if (cy := config.get("country")) and company.country != cy:
            continue
        # Size band — only enforced when the company's size is known (enriched).
        emp = company.employee_count or 0
        if emp > 0:
            if emp_min is not None and emp < int(emp_min):
                continue
            if emp_max is not None and emp > int(emp_max):
                continue
        out.append(str(company.id))
    # Per-lead annotation: which input companies passed the filter (for run_leads).
    passed_set = set(out)
    for cid in company_ids:
        _annotate_lead(ctx, cid, filter_passed=str(cid) in passed_set)
    return {"company_ids": out, "passed": len(out)}


_CONTACTED_STAGES = {"contacted", "replied", "meeting", "proposal", "won", "lost"}


def _step_add_to_crm(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """Advance pipeline stage. A 'contacted'-or-beyond stage means we actually reached
    the company, so it must ONLY apply to companies with a CONFIRMED send — otherwise a
    0-send run silently marks leads contacted and permanently suppresses them (P0 bug).
    Safe-by-default: if this is a contacted+ stage AND a send step ran (ctx carries
    sent_company_ids), advance only those. `only_sent: true` forces it explicitly.
    Pre-send stages (e.g. 'qualified') still advance the whole filtered set."""
    stage = config.get("stage", "qualified")
    gate_on_send = config.get("only_sent") or (
        stage in _CONTACTED_STAGES and "sent_company_ids" in ctx)
    ids = ctx.get("sent_company_ids", []) if gate_on_send else ctx.get("company_ids", [])
    n = 0
    for cid in ids:
        c = db.get(Company, uuid.UUID(cid))
        if c:
            c.pipeline_stage = stage
            n += 1
    db.commit()
    return {"moved": n, "to": stage, "gated_on_send": gate_on_send,
            "candidates": len(ctx.get("company_ids", []))}


def _step_webhook(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    url = config.get("url")
    if not url:
        return {"error": "no_url"}
    try:
        httpx.post(url, json=ctx, timeout=10).raise_for_status()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def _step_wait(_db, _org_id, _ctx, config) -> dict:
    seconds = int(config.get("seconds", 1))
    time.sleep(max(0, min(60, seconds)))
    return {"slept": seconds}


HANDLERS = {
    "discover_companies": _step_discover,
    "discover_local": _step_discover_local,
    "discover_places": _step_discover_places,
    "enrich": _step_enrich,
    "detect_signals": _step_signals,
    "detect_local_signals": _step_detect_local_signals,
    "find_contacts": _step_contacts,
    "validate_emails": _step_validate_emails,
    "score_leads": _step_score,
    "generate_outreach": _step_outreach,
    "filter": _step_filter,
    "add_to_crm": _step_add_to_crm,
    "send_emails": _step_send_emails,
    "send_whatsapp": _step_send_whatsapp,
    "schedule_email_followup": _step_schedule_email_followup,
    "notify_telegram": _step_notify_telegram,
    "webhook": _step_webhook,
    "wait": _step_wait,
}


# ---- runner -----------------------------------------------------------------


def _topological_order(steps: list[dict]) -> list[dict]:
    """Return steps in topological order. Steps form a DAG via `next:[...]`."""
    by_id = {s["id"]: s for s in steps}
    indeg = {s["id"]: 0 for s in steps}
    for s in steps:
        for nx in s.get("next") or []:
            if nx in indeg:
                indeg[nx] += 1
    queue = [sid for sid, d in indeg.items() if d == 0]
    out: list[dict] = []
    while queue:
        sid = queue.pop(0)
        out.append(by_id[sid])
        for nx in by_id[sid].get("next") or []:
            indeg[nx] -= 1
            if indeg[nx] == 0:
                queue.append(nx)
    if len(out) != len(steps):
        # Cycle — fall back to original order.
        return list(steps)
    return out


@shared_task(name="app.workers.workflows.run_workflow_task",
             bind=True, max_retries=1)
def run_workflow_task(self, workflow_id: str) -> dict:
    with task_session() as db:
        wf = db.get(Workflow, uuid.UUID(workflow_id))
        if not wf:
            return {"error": "workflow_not_found"}

        run = WorkflowRun(
            organization_id=wf.organization_id,
            workflow_id=wf.id,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()

        ctx: dict[str, Any] = {
            "icp_id": (wf.settings or {}).get("icp_id"),
            "company_ids": (wf.settings or {}).get("seed_company_ids") or [],
            "contact_ids": [],
            "lead_meta": {},
        }
        step_results: list[dict] = []
        # Ordered union of every company id the run saw — seed with any pre-supplied
        # company_ids so a seeded run counts them as "discovered" too.
        seen_company_ids: list[str] = [str(c) for c in (ctx.get("company_ids") or [])]
        had_error = False

        for step in _topological_order(list(wf.steps or [])):
            handler = HANDLERS.get(step.get("type"))
            if handler is None:
                step_results.append({"id": step.get("id"), "skipped": True})
                continue
            try:
                result = handler(db, wf.organization_id, ctx, step.get("config") or {})
                # Merge updates that look like context keys.
                for k in ("company_ids", "contact_ids", "icp_id", "sent_company_ids",
                          "whatsapp_sent_ids", "email_fallback_ids"):
                    if k in result and result[k] is not None:
                        ctx[k] = result[k]
                # Accumulate every company id this step surfaced (for run_leads), so the
                # discovered set survives the filter narrowing company_ids.
                for k in ("company_ids", "whatsapp_sent_ids", "email_fallback_ids",
                          "sent_company_ids"):
                    for cid in (result.get(k) or []):
                        if str(cid) not in seen_company_ids:
                            seen_company_ids.append(str(cid))
                step_results.append({"id": step["id"], "type": step["type"], "result": result})
            except Exception as e:
                log.exception("workflow_step_failed", step=step.get("id"))
                step_results.append({"id": step.get("id"), "error": str(e)})
                had_error = True

        run.status = "partial" if had_error else "success"
        run.finished_at = datetime.utcnow()
        run.step_results = step_results
        ctx["_all_company_ids"] = seen_company_ids
        try:
            run.run_leads = build_run_leads(db, wf.organization_id, ctx)
        except Exception:
            log.exception("build_run_leads_failed", run_id=str(run.id))
            run.run_leads = []
        run.items_in = len(seen_company_ids)
        run.items_out = len(ctx.get("company_ids") or [])
        wf.last_run_at = run.finished_at
        return {"run_id": str(run.id), "status": run.status, "steps": len(step_results),
                "leads": len(run.run_leads)}


@shared_task(name="app.workers.workflows.run_due_workflows")
def run_due_workflows():
    """Beat-driven dispatcher: schedule any enabled workflow whose `schedule` is due."""
    with task_session() as db:
        candidates = db.execute(
            select(Workflow).where(Workflow.enabled.is_(True), Workflow.schedule != "manual")
        ).scalars().all()
        kicked = 0
        for wf in candidates:
            # Simple schedule semantics: "daily" / "hourly" - more granular cron lives in
            # Celery's beat config.
            should_run = (
                wf.schedule == "hourly"
                or (wf.schedule == "daily" and (
                    wf.last_run_at is None
                    or (datetime.utcnow() - wf.last_run_at).total_seconds() > 23 * 3600
                ))
            )
            if should_run:
                run_workflow_task.delay(str(wf.id))
                kicked += 1
        return {"kicked": kicked}
