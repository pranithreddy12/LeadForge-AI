from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.contact import Contact
from app.services.contacts import validate_and_store
from app.workers._base import task_session

log = get_logger("workers.validation")


@shared_task(name="app.workers.validation.validate_contacts_for_company")
def validate_contacts_for_company(organization_id: str, company_id: str):
    org_uuid = uuid.UUID(organization_id)
    with task_session() as db:
        ids = db.execute(
            select(Contact.id).where(
                Contact.organization_id == org_uuid,
                Contact.company_id == uuid.UUID(company_id),
                Contact.email.is_not(None),
                Contact.email_status.is_(None),
            )
        ).scalars().all()
        for cid in ids:
            try:
                validate_and_store(db, cid)
            except Exception:
                log.exception("validate_failed", contact_id=str(cid))
    return {"validated": len(ids)}
