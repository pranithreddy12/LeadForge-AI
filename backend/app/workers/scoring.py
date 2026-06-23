from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.company import Company
from app.services.scoring import score_company
from app.workers._base import task_session

log = get_logger("workers.scoring")


@shared_task(name="app.workers.scoring.score_batch_task",
             bind=True, max_retries=2, default_retry_delay=15)
def score_batch_task(self, organization_id: str, icp_id: str,
                     company_ids: list[str] | None = None):
    org_uuid = uuid.UUID(organization_id)
    icp_uuid = uuid.UUID(icp_id)
    out: dict[str, str] = {}
    with task_session() as db:
        if not company_ids:
            company_ids = [
                str(i) for i in db.execute(
                    select(Company.id).where(Company.organization_id == org_uuid)
                ).scalars().all()
            ]
        for cid in company_ids:
            try:
                score = score_company(
                    db, organization_id=org_uuid, company_id=uuid.UUID(cid),
                    icp_id=icp_uuid,
                )
                out[cid] = score.grade
            except Exception as e:
                log.warning("score_failed", company_id=cid, error=str(e))
                out[cid] = "error"
    return out
