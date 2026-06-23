from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.models.billing import Subscription
from app.models.tenant import Organization
from app.schemas.billing import CheckoutRequest, CheckoutResponse, SubscriptionOut
from app.services.billing import create_checkout_session

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(db: Session = Depends(get_db),
                     org: Organization = Depends(current_org)):
    sub = db.execute(
        select(Subscription).where(Subscription.organization_id == org.id)
    ).scalar_one_or_none()
    if not sub:
        return SubscriptionOut(plan=org.plan or "free", status="active", seats=1)
    return SubscriptionOut(
        plan=sub.plan,
        status=sub.status,
        seats=sub.seats,
        current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
        cancel_at_period_end=sub.cancel_at_period_end,
    )


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(payload: CheckoutRequest, db: Session = Depends(get_db),
             org: Organization = Depends(current_org)):
    url = create_checkout_session(db, org, plan=payload.plan, return_url=payload.return_url)
    return CheckoutResponse(url=url)
