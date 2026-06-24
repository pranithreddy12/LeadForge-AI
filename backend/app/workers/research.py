from __future__ import annotations

import uuid

from celery import shared_task

from app.core.logging import get_logger
from app.services.research import research_company
from app.workers._base import task_session

log = get_logger("workers.research")


@shared_task(name="app.workers.research.research_company_task",
             bind=True, max_retries=1, default_retry_delay=30)
def research_company_task(self, organization_id: str, company_id: str):
    with task_session() as db:
        try:
            row = research_company(
                db, organization_id=uuid.UUID(organization_id),
                company_id=uuid.UUID(company_id),
            )
        except Exception as exc:
            log.exception("research_failed")
            raise self.retry(exc=exc)
        return {"research_id": str(row.id) if row else None,
                "provider_unavailable": row is None}
