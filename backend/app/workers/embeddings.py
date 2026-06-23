from __future__ import annotations

from celery import shared_task
from sqlalchemy import select

from app.ai.rag import upsert_company_embedding
from app.core.logging import get_logger
from app.models.company import Company
from app.workers._base import task_session

log = get_logger("workers.embeddings")


@shared_task(name="app.workers.embeddings.embed_pending_rows")
def embed_pending_rows(batch: int = 100):
    """Beat-driven backfill of embeddings for new/updated companies."""
    with task_session() as db:
        rows = db.execute(
            select(Company).where(Company.embedding_pending.is_(True)).limit(batch)
        ).scalars().all()
        for c in rows:
            try:
                upsert_company_embedding(db, c)
            except Exception:
                log.exception("embed_failed", company_id=str(c.id))
    return {"embedded": len(rows)}
