"""Active-ICP management — exactly one active ICP per org.

Before this, every ICP defaulted to is_active=True, so discovery/dry-run/eval each
guessed which ICP to use by name-matching (and hit empty ones). Now there is one
canonical active ICP per org, enforced by `uq_icp_one_active_per_org` (partial-unique
index) + this service.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.icp import ICP
from app.models.project import Project


def get_active_icp(db: Session, organization_id: uuid.UUID) -> ICP | None:
    """The org's single active ICP, or None if none is active."""
    return db.execute(
        select(ICP).where(ICP.organization_id == organization_id, ICP.is_active.is_(True))
    ).scalars().first()


def activate_icp(db: Session, icp: ICP) -> ICP:
    """Make `icp` the org's single active ICP. Deactivates every other ICP in the org
    FIRST (so the partial-unique index never collides), backfilling org from the
    project if needed. Idempotent."""
    org_id = icp.organization_id
    if org_id is None and icp.project_id:
        proj = db.get(Project, icp.project_id)
        org_id = proj.organization_id if proj else None
        icp.organization_id = org_id
    if org_id is not None:
        db.execute(update(ICP).where(ICP.organization_id == org_id, ICP.id != icp.id)
                   .values(is_active=False))
    icp.is_active = True
    db.commit()
    db.refresh(icp)
    return icp
