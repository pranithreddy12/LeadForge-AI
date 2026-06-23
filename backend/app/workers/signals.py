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
