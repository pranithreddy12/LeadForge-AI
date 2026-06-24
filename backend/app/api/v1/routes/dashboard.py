from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.models.tenant import Organization
from app.schemas.dashboard import (
    DashboardSummary,
    GradeBucket,
    IndustryBreakdown,
    KPI,
    ScoreTrendPoint,
    SignalFeedItem,
    SourceBreakdown,
)
from app.services.dashboard import (
    industry_breakdown,
    kpi_block,
    score_distribution,
    score_trend,
    signal_counts_today,
    signal_feed,
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


@router.get("/score-distribution", response_model=list[GradeBucket])
def distribution(db: Session = Depends(get_db),
                 org: Organization = Depends(current_org)):
    return score_distribution(db, org.id)


def _serialize_feed(items: list[dict]) -> list[dict]:
    # created_at is NON-nullable on Signal, so .isoformat() is always safe.
    return [
        {**s, "id": str(s["id"]), "company_id": str(s["company_id"]),
         "created_at": s["created_at"].isoformat()}
        for s in items
    ]


@router.get("/signals-today", response_model=list[SignalFeedItem])
def signals_today(hours: int = 48, limit: int = 12,
                  db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    return _serialize_feed(signal_feed(db, org.id, hours=hours, limit=limit))


@router.get("/funding-events", response_model=list[SignalFeedItem])
def funding_events(limit: int = 10, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    return _serialize_feed(signal_feed(db, org.id, kinds=["funding"], limit=limit))


@router.get("/exec-hires", response_model=list[SignalFeedItem])
def exec_hires(limit: int = 10, db: Session = Depends(get_db),
               org: Organization = Depends(current_org)):
    return _serialize_feed(signal_feed(db, org.id, kinds=["leadership_change"], limit=limit))


@router.get("/activity", response_model=dict[str, int])
def activity(hours: int = 24, db: Session = Depends(get_db),
             org: Organization = Depends(current_org)):
    return signal_counts_today(db, org.id, hours=hours)
