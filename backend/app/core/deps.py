from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Principal, get_principal
from app.models.tenant import Organization, User
from app.services.tenant import ensure_user, get_org_by_clerk_id


def current_user(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> User:
    """Resolve (or lazy-create) the local User row for the authenticated principal."""
    return ensure_user(db, principal)


def current_org(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Organization:
    if not principal.org_id:
        raise HTTPException(status_code=400, detail="No active organization")
    org = get_org_by_clerk_id(db, principal.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org
