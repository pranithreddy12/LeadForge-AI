import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import verify_clerk_webhook
from app.services.billing import apply_stripe_event
from app.services.tenant import get_org_by_clerk_id, get_user_by_clerk_id

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = get_logger("webhooks")


@router.post("/clerk")
async def clerk_webhook(request: Request,
                        db: Session = Depends(get_db),
                        event: dict = Depends(verify_clerk_webhook)):
    et = event.get("type")
    data = event.get("data") or {}
    log.info("clerk_event", event_type=et)

    if et == "user.deleted":
        u = get_user_by_clerk_id(db, data.get("id"))
        if u:
            db.delete(u)
            db.commit()
    elif et == "organization.deleted":
        org = get_org_by_clerk_id(db, data.get("id"))
        if org:
            db.delete(org)
            db.commit()
    # user.created / organization.created / membership events are handled lazily
    # on first authenticated request via ensure_user/get_principal.
    return {"ok": True}


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise HTTPException(status_code=400, detail=f"invalid signature: {e}")

    log.info("stripe_event", event_type=event["type"])
    apply_stripe_event(db, event)
    return {"received": True}
