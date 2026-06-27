"""Hourly retry of held-unknown candidates (BUG 4).

Candidates the gate couldn't confirm on a transient provider error are persisted with
classification_status="held_unknown" and suppressed from outreach. Without a retry they
rot forever. This task re-runs the gate hourly:
  buyer            -> status=None,    label="buyer"     (allowed into the pipeline)
  definitive reject-> status="rejected", label=<verdict> (permanently excluded)
  unknown again    -> leave held_unknown, log, retry next hour
  provider error   -> classify returns "unknown" -> left held, retried next hour
"""
from __future__ import annotations

from celery import shared_task
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.company import Company
from app.models.project import Project
from app.workers._base import task_session

log = get_logger("workers.reclassify")

_REJECT_LABELS = {"vendor", "competitor", "investor_vc",
                  "job_board_or_directory", "listicle_or_content", "too_large"}


@shared_task(name="app.workers.reclassify.retry_held_unknowns")
def retry_held_unknowns(limit: int = 100) -> dict:
    from app.ai.qualification_engine import Candidate, classify_candidates
    res = {"checked": 0, "reclassified_buyer": 0, "rejected": 0, "still_held": 0}
    with task_session() as db:
        org_ids = db.execute(
            select(Company.organization_id)
            .where(Company.classification_status == "held_unknown").distinct()
        ).scalars().all()
        for oid in org_ids:
            held = db.execute(
                select(Company).where(Company.organization_id == oid,
                                      Company.classification_status == "held_unknown")
                .limit(limit)
            ).scalars().all()
            if not held:
                continue
            proj = db.execute(
                select(Project).where(Project.organization_id == oid)
                .order_by(Project.created_at.desc())
            ).scalars().first()
            seller = (proj.business_description or "") if proj else ""
            cands = [Candidate(title=c.name, url=c.website or "", domain=c.domain,
                               snippet=c.description, source=c.source or "db") for c in held]
            judged = classify_candidates(cands, seller_description=seller)
            by_idx = {j["index"]: j for j in judged}
            for i, c in enumerate(held):
                res["checked"] += 1
                label = (by_idx.get(i) or {}).get("label", "unknown")
                if label == "buyer":
                    c.classification_status = None
                    c.classification_label = "buyer"
                    res["reclassified_buyer"] += 1
                elif label in _REJECT_LABELS:
                    c.classification_status = "rejected"
                    c.classification_label = label
                    res["rejected"] += 1
                else:  # "unknown" (still ambiguous OR provider error) -> leave held
                    res["still_held"] += 1
                    log.info("held_still_unknown", company=str(c.id))
            db.commit()
    log.info("retry_held_unknowns", **res)
    return res
