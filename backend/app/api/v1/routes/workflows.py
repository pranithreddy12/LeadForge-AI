import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.tenant import Organization
from app.models.workflow import Workflow, WorkflowRun
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowOut,
    WorkflowRunOut,
    WorkflowUpdate,
)
from app.workers.workflows import run_workflow_task

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    return db.execute(
        select(Workflow).where(Workflow.organization_id == org.id)
        .order_by(Workflow.created_at.desc())
    ).scalars().all()


@router.post("", response_model=WorkflowOut, status_code=201)
def create(payload: WorkflowCreate,
           db: Session = Depends(get_db),
           org: Organization = Depends(current_org)):
    row = Workflow(
        organization_id=org.id,
        name=payload.name,
        description=payload.description,
        schedule=payload.schedule,
        steps=[s.model_dump() for s in payload.steps],
        settings=payload.settings,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def patch(workflow_id: uuid.UUID, payload: WorkflowUpdate,
          db: Session = Depends(get_db),
          org: Organization = Depends(current_org)):
    row = db.get(Workflow, workflow_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Workflow")
    data = payload.model_dump(exclude_unset=True)
    if "steps" in data and data["steps"] is not None:
        data["steps"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in data["steps"]]
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{workflow_id}", status_code=204)
def delete(workflow_id: uuid.UUID, db: Session = Depends(get_db),
           org: Organization = Depends(current_org)):
    row = db.get(Workflow, workflow_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Workflow")
    db.delete(row)
    db.commit()
    return None


@router.post("/{workflow_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_now(workflow_id: uuid.UUID, db: Session = Depends(get_db),
            org: Organization = Depends(current_org)):
    row = db.get(Workflow, workflow_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Workflow")
    task = run_workflow_task.delay(str(workflow_id))
    return {"task_id": task.id, "status": "queued"}


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunOut])
def list_runs(workflow_id: uuid.UUID, db: Session = Depends(get_db),
              org: Organization = Depends(current_org),
              limit: int = 25):
    row = db.get(Workflow, workflow_id)
    if not row or row.organization_id != org.id:
        raise NotFound("Workflow")
    return db.execute(
        select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc()).limit(limit)
    ).scalars().all()
