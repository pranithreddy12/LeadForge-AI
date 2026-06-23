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
from sqlalchemy import select

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


def _step_discover(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    icp_id = uuid.UUID(config.get("icp_id") or ctx["icp_id"])
    icp = db.get(ICP, icp_id)
    limit = int(config.get("limit", 25))
    cands = discover_via_search(icp, limit=limit, extra_keywords=config.get("keywords"))
    rows = persist_candidates(db, organization_id=org_id, icp=icp, candidates=cands)
    company_ids = ctx.get("company_ids", []) + [str(r.id) for r in rows]
    return {"company_ids": company_ids, "delta": len(rows)}


def _step_signals(db, org_id: uuid.UUID, ctx: dict, _config: dict) -> dict:
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
        draft_outreach_for_company.delay(str(org_id), cid, channel=channel)
        n += 1
    return {"drafted_queued": n}


def _step_filter(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    """`config` can include min_score, grades, industries, country, pipeline_stage."""
    from app.models.scoring import LeadScore
    company_ids = ctx.get("company_ids") or []
    if not company_ids:
        return {"company_ids": []}
    rows = db.execute(
        select(Company, LeadScore.score, LeadScore.grade)
        .outerjoin(LeadScore, LeadScore.company_id == Company.id)
        .where(Company.id.in_([uuid.UUID(c) for c in company_ids]))
    ).all()
    out = []
    for company, score, grade in rows:
        if (m := config.get("min_score")) is not None and (score or 0) < int(m):
            continue
        if (g := config.get("grades")) and grade not in g:
            continue
        if (ind := config.get("industries")) and company.industry not in ind:
            continue
        if (cy := config.get("country")) and company.country != cy:
            continue
        out.append(str(company.id))
    return {"company_ids": out, "passed": len(out)}


def _step_add_to_crm(db, org_id: uuid.UUID, ctx: dict, config: dict) -> dict:
    stage = config.get("stage", "qualified")
    n = 0
    for cid in ctx.get("company_ids", []):
        c = db.get(Company, uuid.UUID(cid))
        if c:
            c.pipeline_stage = stage
            n += 1
    db.commit()
    return {"moved": n, "to": stage}


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
    "detect_signals": _step_signals,
    "find_contacts": _step_contacts,
    "validate_emails": _step_validate_emails,
    "score_leads": _step_score,
    "generate_outreach": _step_outreach,
    "filter": _step_filter,
    "add_to_crm": _step_add_to_crm,
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
        }
        step_results: list[dict] = []
        had_error = False

        for step in _topological_order(list(wf.steps or [])):
            handler = HANDLERS.get(step.get("type"))
            if handler is None:
                step_results.append({"id": step.get("id"), "skipped": True})
                continue
            try:
                result = handler(db, wf.organization_id, ctx, step.get("config") or {})
                # Merge updates that look like context keys.
                for k in ("company_ids", "contact_ids", "icp_id"):
                    if k in result and result[k] is not None:
                        ctx[k] = result[k]
                step_results.append({"id": step["id"], "type": step["type"], "result": result})
            except Exception as e:
                log.exception("workflow_step_failed", step=step.get("id"))
                step_results.append({"id": step.get("id"), "error": str(e)})
                had_error = True

        run.status = "partial" if had_error else "success"
        run.finished_at = datetime.utcnow()
        run.step_results = step_results
        run.items_out = len(ctx.get("company_ids") or [])
        wf.last_run_at = run.finished_at
        return {"run_id": str(run.id), "status": run.status, "steps": len(step_results)}


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
