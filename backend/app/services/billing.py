from __future__ import annotations

import stripe
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.billing import Subscription
from app.models.tenant import Organization

stripe.api_key = settings.stripe_secret_key

PRICE_MAP = {
    "starter": settings.stripe_price_starter,
    "growth": settings.stripe_price_growth,
    "scale": settings.stripe_price_scale,
}


def get_or_create_customer(db: Session, org: Organization) -> str:
    if org.stripe_customer_id:
        return org.stripe_customer_id
    cust = stripe.Customer.create(name=org.name, metadata={"org_id": str(org.id)})
    org.stripe_customer_id = cust.id
    db.commit()
    return cust.id


def create_checkout_session(db: Session, org: Organization, *, plan: str,
                            return_url: str | None) -> str:
    price = PRICE_MAP.get(plan)
    if not price:
        raise ValueError(f"unknown plan {plan}")
    customer = get_or_create_customer(db, org)
    success = (return_url or settings.app_public_url) + "?checkout=success"
    cancel = (return_url or settings.app_public_url) + "?checkout=cancel"
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer,
        line_items=[{"price": price, "quantity": 1}],
        success_url=success,
        cancel_url=cancel,
        allow_promotion_codes=True,
        metadata={"org_id": str(org.id), "plan": plan},
    )
    return session.url


def apply_stripe_event(db: Session, event: dict) -> None:
    """Idempotently project a Stripe event onto Subscription/Organization."""
    et = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    org_id = (obj.get("metadata") or {}).get("org_id")

    if not org_id or "subscription" not in et and et != "checkout.session.completed":
        return

    org = db.get(Organization, org_id)
    if not org:
        return

    sub = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    if sub is None:
        sub = Subscription(
            organization_id=org.id,
            stripe_customer_id=obj.get("customer") or org.stripe_customer_id or "",
        )
        db.add(sub)

    sub.stripe_subscription_id = obj.get("id") or obj.get("subscription") or sub.stripe_subscription_id
    sub.price_id = (obj.get("items", {}).get("data") or [{}])[0].get("price", {}).get("id")
    sub.status = obj.get("status") or sub.status
    sub.plan = (obj.get("metadata") or {}).get("plan") or sub.plan
    sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    sub.raw = obj

    org.plan = sub.plan
    db.commit()
