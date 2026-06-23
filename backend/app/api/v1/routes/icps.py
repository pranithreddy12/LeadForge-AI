import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.icp_engine import generate_icp, refine_icp
from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.core.rate_limit import hit
from app.models.icp import ICP
from app.models.project import Project
from app.models.tenant import Organization
from app.schemas.common import Page
from app.schemas.icp import ICPGenerateRequest, ICPOut, ICPUpdate

router = APIRouter(prefix="/icps", tags=["icps"])


@router.post("/generate", response_model=ICPOut, status_code=status.HTTP_201_CREATED)
def generate(
    payload: ICPGenerateRequest,
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
):
    hit(f"icp_gen:{org.id}", limit=20, window_seconds=60)

    project: Project | None = None
    if payload.project_id:
        project = db.get(Project, payload.project_id)
        if not project or project.organization_id != org.id:
            raise NotFound("Project")
    else:
        # Lazy-create a project to anchor this ICP.
        project = Project(
            organization_id=org.id,
            name="Untitled project",
            business_description=payload.business_description,
            target_offering=payload.target_offering,
        )
        db.add(project)
        db.flush()

    raw = generate_icp(
        business_description=payload.business_description,
        target_offering=payload.target_offering,
        hints=payload.hints,
    )

    icp = ICP(
        project_id=project.id,
        name=raw.get("name") or "Generated ICP",
        summary=raw.get("summary"),
        industries=raw.get("industries") or [],
        sub_industries=raw.get("sub_industries") or [],
        countries=raw.get("countries") or [],
        regions=raw.get("regions") or [],
        employee_min=raw.get("employee_min"),
        employee_max=raw.get("employee_max"),
        revenue_min_usd=raw.get("revenue_min_usd"),
        revenue_max_usd=raw.get("revenue_max_usd"),
        buyer_personas=raw.get("buyer_personas") or [],
        buying_signals=raw.get("buying_signals") or [],
        keywords=raw.get("keywords") or [],
        excluded_keywords=raw.get("excluded_keywords") or [],
        tech_stack_required=raw.get("tech_stack_required") or [],
        tech_stack_excluded=raw.get("tech_stack_excluded") or [],
        weights=raw.get("weights") or {},
        raw_ai_response=raw,
    )
    db.add(icp)
    db.commit()
    db.refresh(icp)
    return icp


@router.get("", response_model=Page[ICPOut])
def list_icps(
    project_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    page: int = 1, page_size: int = 25,
):
    base = (
        select(ICP).join(Project, Project.id == ICP.project_id)
        .where(Project.organization_id == org.id)
        .order_by(ICP.created_at.desc())
    )
    if project_id:
        base = base.where(ICP.project_id == project_id)
    total = len(db.execute(base).scalars().all())
    rows = db.execute(base.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return Page(items=rows, page=page, page_size=page_size, total=total,
                has_next=total > page * page_size)


@router.get("/{icp_id}", response_model=ICPOut)
def get_icp(icp_id: uuid.UUID, db: Session = Depends(get_db),
            org: Organization = Depends(current_org)):
    row = db.get(ICP, icp_id)
    if not row or row.project.organization_id != org.id:
        raise NotFound("ICP")
    return row


@router.patch("/{icp_id}", response_model=ICPOut)
def patch_icp(icp_id: uuid.UUID, payload: ICPUpdate,
              db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    row = db.get(ICP, icp_id)
    if not row or row.project.organization_id != org.id:
        raise NotFound("ICP")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.post("/{icp_id}/refine", response_model=ICPOut)
def refine(icp_id: uuid.UUID, instruction: str,
           db: Session = Depends(get_db),
           org: Organization = Depends(current_org)):
    row = db.get(ICP, icp_id)
    if not row or row.project.organization_id != org.id:
        raise NotFound("ICP")
    refined = refine_icp({c.key: getattr(row, c.key) for c in row.__table__.columns}, instruction)
    for k in [
        "name", "summary", "industries", "sub_industries", "countries", "regions",
        "employee_min", "employee_max", "revenue_min_usd", "revenue_max_usd",
        "buyer_personas", "buying_signals", "keywords", "excluded_keywords",
        "tech_stack_required", "tech_stack_excluded", "weights",
    ]:
        if k in refined:
            setattr(row, k, refined[k])
    row.raw_ai_response = refined
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{icp_id}", status_code=204)
def delete_icp(icp_id: uuid.UUID, db: Session = Depends(get_db),
               org: Organization = Depends(current_org)):
    row = db.get(ICP, icp_id)
    if not row or row.project.organization_id != org.id:
        raise NotFound("ICP")
    db.delete(row)
    db.commit()
    return None
