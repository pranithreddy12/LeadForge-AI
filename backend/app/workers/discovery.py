from __future__ import annotations

import uuid

from celery import shared_task

from app.core.celery_app import celery
from app.core.logging import get_logger
from app.models.icp import ICP
from app.services.discovery import discover_via_search, persist_candidates
from app.workers._base import task_session

log = get_logger("workers.discovery")


@shared_task(name="app.workers.discovery.discover_companies_task",
             bind=True, max_retries=2, default_retry_delay=15)
def discover_companies_task(self, organization_id: str, icp_id: str,
                            limit: int = 25, extra_keywords: list[str] | None = None):
    with task_session() as db:
        icp = db.get(ICP, uuid.UUID(icp_id))
        if not icp:
            return {"error": "icp_not_found"}
        try:
            candidates = discover_via_search(icp, limit=limit, extra_keywords=extra_keywords or [])
            rows = persist_candidates(db, organization_id=uuid.UUID(organization_id),
                                      icp=icp, candidates=candidates)
        except Exception as exc:
            log.exception("discover_failed")
            raise self.retry(exc=exc)
        # Fan out signal detection per company.
        for c in rows:
            detect_signals_task = celery.signature(
                "app.workers.signals.detect_signals_task",
                args=[organization_id, str(c.id)],
            )
            detect_signals_task.apply_async(queue="default")
        return {"created": len(rows)}
