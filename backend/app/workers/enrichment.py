from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.company import Company
from app.services.enrichment import enrich_batch, enrich_company
from app.workers._base import task_session

log = get_logger("workers.enrichment")


@shared_task(name="app.workers.enrichment.enrich_company_task",
             bind=True, max_retries=1, default_retry_delay=30)
def enrich_company_task(self, organization_id: str, company_id: str):
    with task_session() as db:
        company = db.get(Company, uuid.UUID(company_id))
        if not company or str(company.organization_id) != organization_id:
            return {"error": "company_not_found"}
        try:
            return enrich_company(db, company)
        except Exception as exc:
            log.exception("enrich_company_failed")
            raise self.retry(exc=exc)


@shared_task(name="app.workers.enrichment.enrich_batch_task")
def enrich_batch_task(organization_id: str, company_ids: list[str] | None = None,
                      limit: int = 25):
    with task_session() as db:
        ids = [uuid.UUID(c) for c in company_ids] if company_ids else None
        return enrich_batch(db, organization_id=uuid.UUID(organization_id),
                            company_ids=ids, limit=limit)


@shared_task(name="app.workers.enrichment.enrich_pending")
def enrich_pending(limit: int = 50):
    """Beat-driven backfill: enrich any company not yet enriched."""
    with task_session() as db:
        orgs = db.execute(
            select(Company.organization_id).where(Company.enriched.is_(False)).distinct()
        ).scalars().all()
        total = 0
        for org_id in orgs:
            res = enrich_batch(db, organization_id=org_id, limit=limit)
            total += res["companies"]
        return {"enriched": total}
