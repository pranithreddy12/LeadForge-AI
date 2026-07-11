"""Do-not-contact / opt-out registry API (UAE PDPL + unsubscribe duty)."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.optout import DoNotContact
from app.models.tenant import Organization
from app.services.optout import add_optout, normalize_email, normalize_phone

router = APIRouter(prefix="/optout", tags=["optout"])


class OptOutAdd(BaseModel):
    value: str
    kind: str = "email"   # email | phone | domain
    reason: str | None = None


@router.get("")
def list_optouts(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    rows = db.execute(
        select(DoNotContact).where(DoNotContact.organization_id == org.id)
        .order_by(DoNotContact.created_at.desc())
    ).scalars().all()
    return {"count": len(rows), "items": [{
        "id": str(r.id), "value": r.value, "kind": r.kind, "reason": r.reason,
        "source": r.source, "at": r.created_at,
    } for r in rows]}


@router.post("", status_code=201)
def add(body: OptOutAdd, db: Session = Depends(get_db),
        org: Organization = Depends(current_org)):
    value = body.value
    if body.kind == "email":
        value = normalize_email(value) or value
    elif body.kind == "phone":
        value = normalize_phone(value) or value
    else:
        value = (value or "").strip().lower()
    row = add_optout(db, org.id, value, kind=body.kind, reason=body.reason,
                     source="manual")
    if row is None:
        raise NotFound("value")
    return {"id": str(row.id), "value": row.value, "kind": row.kind}


@router.delete("/{optout_id}", status_code=204)
def remove(optout_id: uuid.UUID, db: Session = Depends(get_db),
           org: Organization = Depends(current_org)):
    row = db.get(DoNotContact, optout_id)
    if not row or row.organization_id != org.id:
        raise NotFound("OptOut")
    db.delete(row)
    db.commit()
