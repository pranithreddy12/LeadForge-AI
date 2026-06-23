import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org, current_user
from app.core.errors import NotFound
from app.models.company import Company
from app.models.crm import CRMActivity, CRMTask
from app.models.tenant import Organization, User
from app.schemas.common import Page
from app.schemas.crm import (
    ActivityCreate,
    ActivityOut,
    PipelineSummary,
    StageMove,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services.crm import move_stage, pipeline_summary

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("/pipeline", response_model=list[PipelineSummary])
def pipeline(db: Session = Depends(get_db),
             org: Organization = Depends(current_org)):
    return pipeline_summary(db, org.id)


@router.post("/{company_id}/stage", status_code=200)
def set_stage(company_id: uuid.UUID, payload: StageMove,
              db: Session = Depends(get_db),
              org: Organization = Depends(current_org),
              user: User = Depends(current_user)):
    c = db.get(Company, company_id)
    if not c or c.organization_id != org.id:
        raise NotFound("Company")
    move_stage(db, c, payload.stage, user_id=user.id)
    return {"ok": True, "stage": payload.stage}


# --- activities ----------------------------------------------------------------

@router.get("/activities", response_model=Page[ActivityOut])
def list_activities(db: Session = Depends(get_db),
                    org: Organization = Depends(current_org),
                    company_id: uuid.UUID | None = None,
                    page: int = 1, page_size: int = 50):
    stmt = select(CRMActivity).where(CRMActivity.organization_id == org.id)
    if company_id:
        stmt = stmt.where(CRMActivity.company_id == company_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(CRMActivity.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=total,
                has_next=total > page * page_size)


@router.post("/activities", response_model=ActivityOut, status_code=201)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db),
                    org: Organization = Depends(current_org),
                    user: User = Depends(current_user)):
    row = CRMActivity(organization_id=org.id, user_id=user.id,
                      **payload.model_dump(exclude_none=True))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- tasks --------------------------------------------------------------------

@router.get("/tasks", response_model=Page[TaskOut])
def list_tasks(db: Session = Depends(get_db),
               org: Organization = Depends(current_org),
               page: int = 1, page_size: int = 50,
               open_only: bool = True):
    stmt = select(CRMTask).where(CRMTask.organization_id == org.id)
    if open_only:
        stmt = stmt.where(CRMTask.is_done.is_(False))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(CRMTask.due_at.is_(None), CRMTask.due_at, CRMTask.priority)
            .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=total,
                has_next=total > page * page_size)


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db),
                org: Organization = Depends(current_org)):
    row = CRMTask(organization_id=org.id, **payload.model_dump(exclude_none=True))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def patch_task(task_id: uuid.UUID, payload: TaskUpdate,
               db: Session = Depends(get_db),
               org: Organization = Depends(current_org)):
    row = db.get(CRMTask, task_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Task")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: uuid.UUID, db: Session = Depends(get_db),
                org: Organization = Depends(current_org)):
    row = db.get(CRMTask, task_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Task")
    db.delete(row)
    db.commit()
    return None
