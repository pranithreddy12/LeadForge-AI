"""All-scraped-data explorer — one flat row per discovered company with every key
field pulled from the model + raw Places payload + latest score + signals + contacts.
Powers the /data page (dense sortable table + CSV export)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.models.company import Company
from app.models.contact import Contact
from app.models.scoring import LeadScore
from app.models.signal import Signal
from app.models.tenant import Organization

router = APIRouter(prefix="/data", tags=["data"])

# The column order the frontend renders + exports. Keeping it here means one source of
# truth for both the table and the CSV.
COLUMNS = [
    "name", "domain", "website", "city", "country", "industry",
    "phone", "phone_intl", "rating", "review_count", "hours",
    "online_booking", "score", "grade", "top_signal", "signals",
    "pipeline_stage", "source", "contact_name", "contact_email",
    "decision_maker", "linkedin_url", "instagram", "place_id",
    "created_at",
]


def _row(db: Session, co: Company, score_map: dict, sig_map: dict) -> dict:
    places = (co.raw or {}).get("places") or {}
    dossier = (co.raw or {}).get("dossier") or {}
    socials = co.socials or {}
    sc = score_map.get(co.id)
    kinds = sig_map.get(co.id, [])
    top_signal = kinds[0] if kinds else None

    contact = db.execute(
        select(Contact.name, Contact.email).where(Contact.company_id == co.id)
        .order_by(Contact.email.is_(None)).limit(1)
    ).first()

    hours = places.get("hours")
    return {
        "id": str(co.id),
        "name": co.name,
        "domain": co.domain,
        "website": co.website or places.get("website"),
        "city": co.city or places.get("city"),
        "country": co.country,
        "industry": co.industry,
        "phone": places.get("phone"),
        "phone_intl": places.get("phone_intl"),
        "rating": places.get("rating"),
        "review_count": places.get("review_count"),
        "hours": "; ".join(hours) if isinstance(hours, list) else (hours or None),
        "online_booking": dossier.get("online_booking"),
        "score": int(sc[0]) if sc and sc[0] is not None else None,
        "grade": sc[1] if sc else None,
        "top_signal": top_signal,
        "signals": ", ".join(kinds) if kinds else None,
        "pipeline_stage": co.pipeline_stage,
        "source": co.source,
        "contact_name": contact[0] if contact else None,
        "contact_email": contact[1] if contact else None,
        "decision_maker": dossier.get("decision_maker") or (co.raw or {}).get("decision_maker"),
        "linkedin_url": co.linkedin_url or socials.get("linkedin"),
        "instagram": socials.get("instagram"),
        "place_id": places.get("place_id"),
        "created_at": co.created_at,
    }


@router.get("/leads")
def all_scraped_leads(db: Session = Depends(get_db),
                      org: Organization = Depends(current_org)):
    """Every discovered company for the org, flattened. No pagination — this is the
    'see everything' view (org lead counts are in the hundreds, not millions)."""
    companies = db.execute(
        select(Company).where(Company.organization_id == org.id)
        .order_by(Company.created_at.desc())
    ).scalars().all()
    ids = [c.id for c in companies]

    # Latest score per company (most recent row wins).
    score_map: dict[uuid.UUID, tuple] = {}
    if ids:
        for cid, s, g, created in db.execute(
            select(LeadScore.company_id, LeadScore.score, LeadScore.grade,
                   LeadScore.created_at)
            .where(LeadScore.company_id.in_(ids))
            .order_by(LeadScore.created_at.desc())
        ):
            score_map.setdefault(cid, (s, g))  # first seen = newest

    # Signal kinds per company, strongest first.
    sig_map: dict[uuid.UUID, list] = {}
    if ids:
        for cid, kind in db.execute(
            select(Signal.company_id, Signal.kind).where(Signal.company_id.in_(ids))
            .order_by(Signal.severity.desc().nullslast())
        ):
            sig_map.setdefault(cid, [])
            if kind not in sig_map[cid]:
                sig_map[cid].append(kind)

    rows = [_row(db, c, score_map, sig_map) for c in companies]
    return {"count": len(rows), "columns": COLUMNS, "rows": rows}
