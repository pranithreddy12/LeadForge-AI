import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.company import Company
from app.models.signal import Signal
from app.models.tenant import Organization
from app.schemas.common import Page
from app.schemas.signal import SignalCreate, SignalOut
from app.workers.signals import detect_signals_task

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=Page[SignalOut])
def list_signals(
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    company_id: uuid.UUID | None = None,
    kind: str | None = None,
    page: int = 1, page_size: int = 50,
):
    stmt = select(Signal).where(Signal.organization_id == org.id)
    if company_id:
        stmt = stmt.where(Signal.company_id == company_id)
    if kind:
        stmt = stmt.where(Signal.kind == kind)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Signal.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=total,
                has_next=total > page * page_size)


@router.post("", response_model=SignalOut, status_code=201)
def create_signal(payload: SignalCreate, db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    company = db.get(Company, payload.company_id)
    if not company or company.organization_id != org.id:
        raise NotFound("Company")
    row = Signal(
        organization_id=org.id,
        source="manual",
        **payload.model_dump(exclude_none=True),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/detect/{company_id}", status_code=status.HTTP_202_ACCEPTED)
def detect(company_id: uuid.UUID, db: Session = Depends(get_db),
           org: Organization = Depends(current_org)):
    company = db.get(Company, company_id)
    if not company or company.organization_id != org.id:
        raise NotFound("Company")
    task = detect_signals_task.delay(str(org.id), str(company_id))
    return {"task_id": task.id, "status": "queued"}
