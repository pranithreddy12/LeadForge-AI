from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models.tenant import Organization, OrganizationMember, User


def get_user_by_clerk_id(db: Session, clerk_user_id: str) -> User | None:
    return db.execute(select(User).where(User.clerk_user_id == clerk_user_id)).scalar_one_or_none()


def get_org_by_clerk_id(db: Session, clerk_org_id: str) -> Organization | None:
    return db.execute(
        select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    ).scalar_one_or_none()


def ensure_user(db: Session, principal: Principal) -> User:
    """Lazily create the local User row when we first see a Clerk principal."""
    user = get_user_by_clerk_id(db, principal.user_id)
    if user is None:
        user = User(
            clerk_user_id=principal.user_id,
            email=principal.email or f"{principal.user_id}@clerk.local",
            name=principal.claims.get("name"),
        )
        db.add(user)
        db.flush()

    if principal.org_id:
        org = get_org_by_clerk_id(db, principal.org_id)
        if org is None:
            name = principal.claims.get("org_name") or "Workspace"
            org = Organization(
                clerk_org_id=principal.org_id,
                name=name,
                slug=_unique_slug(db, name),
                plan="free",
            )
            db.add(org)
            db.flush()
        existing = db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.user_id == user.id,
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role=principal.org_role or "member",
            ))

    db.commit()
    db.refresh(user)
    return user


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "workspace"


def _unique_slug(db: Session, name: str) -> str:
    base = _slug(name)[:100]
    candidate = base
    suffix = 2
    while db.execute(select(Organization).where(Organization.slug == candidate)).first():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate
