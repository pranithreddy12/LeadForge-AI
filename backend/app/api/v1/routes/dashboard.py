from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.models.tenant import Organization
from app.schemas.dashboard import (
    DashboardSummary,
    IndustryBreakdown,
    KPI,
    ScoreTrendPoint,
    SourceBreakdown,
)
from app.services.dashboard import (
    industry_breakdown,
    kpi_block,
    score_trend,
    source_breakdown,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db),
            org: Organization = Depends(current_org)):
    k = kpi_block(db, org.id)
    return DashboardSummary(
        leads_found=KPI(**k["leads_found"]),
        qualified_leads=KPI(**k["qualified_leads"]),
        avg_score=KPI(**k["avg_score"]),
        conversion_rate=KPI(**k["conversion_rate"]),
        revenue=KPI(**k["revenue"]),
    )


@router.get("/industries", response_model=list[IndustryBreakdown])
def industries(db: Session = Depends(get_db),
               org: Organization = Depends(current_org)):
    return industry_breakdown(db, org.id)


@router.get("/sources", response_model=list[SourceBreakdown])
def sources(db: Session = Depends(get_db),
            org: Organization = Depends(current_org)):
    return source_breakdown(db, org.id)


@router.get("/trend", response_model=list[ScoreTrendPoint])
def trend(days: int = 30, db: Session = Depends(get_db),
          org: Organization = Depends(current_org)):
    return score_trend(db, org.id, days=days)
