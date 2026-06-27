"""Keep the org's single active ICP in sync with Settings (B2B mode).

D1: Settings is the source of truth. On save we update ONE ICP row from the Settings
B2B fields and make it the single active ICP. We REUSE an existing ICP (never create a
new one when one exists) so this also fixes the proliferation bug — the org converges
to exactly one active ICP derived from Settings.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.icp import ICP
from app.models.project import Project
from app.models.settings import Settings
from app.services.icp import activate_icp, get_active_icp

log = get_logger(__name__)


def sync_active_icp_from_settings(db: Session, settings: Settings) -> ICP | None:
    org_id = settings.organization_id
    # Prefer the current active ICP; else reuse the most-recent existing one (no new row).
    icp = get_active_icp(db, org_id)
    if icp is None:
        icp = db.execute(
            select(ICP).where(ICP.organization_id == org_id)
            .order_by(ICP.created_at.desc())
        ).scalars().first()
    if icp is None:
        proj = db.execute(
            select(Project).where(Project.organization_id == org_id)
            .order_by(Project.created_at.desc())
        ).scalars().first()
        if proj is None:
            log.warning("settings_sync_no_project", org=str(org_id))
            return None
        icp = ICP(project_id=proj.id, organization_id=org_id,
                  name=settings.icp_name or "B2B ICP")
        db.add(icp)
        db.flush()

    icp.organization_id = org_id
    icp.name = settings.icp_name or icp.name
    icp.summary = settings.icp_name
    icp.employee_min = settings.employee_min
    icp.employee_max = settings.employee_max
    icp.industries = settings.target_industries or []
    icp.countries = settings.target_geography or []
    # verticals as buyer-targeting keywords; clear the cached queries so discovery
    # regenerates from the new config (the stale-query bug fixed earlier).
    icp.keywords = settings.target_industries or []
    icp.search_queries = []
    db.commit()
    activate_icp(db, icp)
    log.info("settings_synced_active_icp", icp=str(icp.id), name=icp.name)
    return icp
