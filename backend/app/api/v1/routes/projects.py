import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org, current_user
from app.core.errors import NotFound
from app.models.project import Project
from app.models.tenant import Organization, User
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=Page[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    page: int = 1,
    page_size: int = 25,
):
    q = select(Project).where(Project.organization_id == org.id) \
        .order_by(Project.created_at.desc())
    total = db.execute(
        select(Project.id).where(Project.organization_id == org.id)
    ).scalars().all()
    rows = db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=len(total),
                has_next=len(total) > page * page_size)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    user: User = Depends(current_user),
):
    p = Project(
        organization_id=org.id,
        created_by_id=user.id,
        name=payload.name,
        business_description=payload.business_description,
        target_offering=payload.target_offering,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db),
                org: Organization = Depends(current_org)):
    p = db.get(Project, project_id)
    if not p or p.organization_id != org.id:
        raise NotFound("Project")
    return p


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, payload: ProjectUpdate,
                   db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    p = db.get(Project, project_id)
    if not p or p.organization_id != org.id:
        raise NotFound("Project")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    p = db.get(Project, project_id)
    if not p or p.organization_id != org.id:
        raise NotFound("Project")
    db.delete(p)
    db.commit()
    return None
