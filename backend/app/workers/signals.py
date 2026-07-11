from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from celery import shared_task
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.company import Company
from app.models.icp import ICP
from app.services.signals import detect_for_company
from app.workers._base import task_session

log = get_logger("workers.signals")


@shared_task(name="app.workers.signals.detect_signals_task",
             bind=True, max_retries=2, default_retry_delay=20)
def detect_signals_task(self, organization_id: str, company_id: str):
    with task_session() as db:
        company = db.get(Company, uuid.UUID(company_id))
        if not company or str(company.organization_id) != organization_id:
            return {"error": "company_not_found"}
        keywords = []
        if company.icp_id:
            icp = db.get(ICP, company.icp_id)
            keywords = (icp.keywords if icp else []) or []
        try:
            signals = detect_for_company(db, company, keywords)
        except Exception as exc:
            log.exception("detect_signals_failed")
            raise self.retry(exc=exc)
        return {"signals": len(signals)}


@shared_task(name="app.workers.signals.rescan_local_signals")
def rescan_local_signals(organization_id: str | None = None) -> dict:
    """Fresh-signal re-scan for UNCONTACTED local leads: refresh Places facts, detect
    new signals, resolve stale ones (booking widget appeared), re-score changed leads.
    Weekly beat + on-demand from /today. Sends NOTHING."""
    from app.services.icp import get_active_icp
    from app.services.rescan import rescan_company
    from app.services.scoring import score_company
    from app.services.settings_resolver import pipeline_config, resolve_credential

    with task_session() as db:
        if organization_id:
            org_ids = [uuid.UUID(organization_id)]
        else:
            org_ids = db.execute(select(Company.organization_id).distinct()).scalars().all()
        totals = {"scanned": 0, "changed": 0, "new_signals": 0, "resolved": 0,
                  "rescored": 0}
        for oid in org_ids:
            if pipeline_config(db, oid).get("discovery_mode") != "local":
                continue  # B2B signals refresh on their own path
            key = resolve_credential(db, oid, "google_places_api_key") or None
            icp = get_active_icp(db, oid)
            companies = db.execute(
                select(Company).where(
                    Company.organization_id == oid,
                    Company.pipeline_stage.in_(("new", "qualified")))
            ).scalars().all()
            for c in companies:
                try:
                    r = rescan_company(db, c, key)
                except Exception as e:
                    log.warning("rescan_failed", company=str(c.id), error=str(e)[:120])
                    continue
                totals["scanned"] += 1
                if r["changes"] or r["new"] or r["resolved"]:
                    totals["changed"] += 1
                    totals["new_signals"] += len(r["new"])
                    totals["resolved"] += len(r["resolved"])
                    if icp is not None and (r["new"] or r["resolved"]):
                        try:
                            score_company(db, organization_id=oid, company_id=c.id,
                                          icp_id=icp.id, with_opportunity=False)
                            totals["rescored"] += 1
                        except Exception as e:
                            log.warning("rescan_rescore_failed", company=str(c.id),
                                        error=str(e)[:120])
        log.info("rescan_local_signals_done", **totals)
        return totals


@shared_task(name="app.workers.signals.refresh_active_companies")
def refresh_active_companies():
    """Hourly beat — refresh signals on any company that was created in the last
    72 hours and hasn't been re-checked in the last 6 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=72)
    with task_session() as db:
        ids = db.execute(
            select(Company.id).where(Company.created_at >= cutoff)
        ).scalars().all()
        for cid in ids:
            detect_signals_task.apply_async(
                args=[str(db.get(Company, cid).organization_id), str(cid)],
                queue="default",
            )
    return {"scheduled": len(ids)}
