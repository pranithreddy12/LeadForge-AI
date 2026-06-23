from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.models.tenant import Organization
from app.schemas.opportunity import OpportunityCard, OpportunityStats
from app.services.opportunities import list_opportunities, opportunity_stats

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", response_model=list[OpportunityCard])
def list_opps(
    db: Session = Depends(get_db),
    org: Organization = Depends(current_org),
    min_score: int = 0,
    limit: int = 50,
    offset: int = 0,
):
    return list_opportunities(db, organization_id=org.id, min_score=min_score,
                              limit=limit, offset=offset)


@router.get("/stats", response_model=OpportunityStats)
def stats(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    return opportunity_stats(db, organization_id=org.id)
