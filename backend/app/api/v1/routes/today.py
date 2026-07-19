"""Manual-send sprint (Today's Leads) — review drafted leads, copy + send yourself,
mark sent / skip, and track the 7-day funnel. Drafts accumulate when
Settings.outreach_send_mode == 'manual' (the workflow drafts but never sends)."""
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_org
from app.core.errors import NotFound
from app.models.campaign import EmailMessage
from app.models.company import Company
from app.models.contact import Contact
from app.models.manual_outreach import ManualOutreachLog
from app.models.scoring import LeadScore
from app.models.signal import Signal
from app.models.tenant import Organization
from app.models.workflow import Workflow
from app.services.instagram import dm_link as ig_dm_link
from app.services.instagram import handle_from_url as ig_handle
from app.services.instagram import profile_link as ig_profile
from app.services.presend import mx_ok, spam_flags
from app.services.settings_resolver import outreach_send_mode
from app.services.whatsapp_sender import normalize_phone, wa_link

router = APIRouter(prefix="/today", tags=["today"])


class SkipBody(BaseModel):
    reason: str = "other"   # bad_fit | no_contact | looks_wrong | other


class LogUpdate(BaseModel):
    replied: bool | None = None
    notes: str | None = None


def _top_signal(db: Session, company_id) -> str | None:
    r = db.execute(
        select(Signal.label, Signal.kind).where(Signal.company_id == company_id)
        .order_by(Signal.severity.desc().nullslast()).limit(1)
    ).first()
    return (r[0] or r[1]) if r else None


def _latest_score(db: Session, company_id):
    return db.execute(
        select(LeadScore.score, LeadScore.grade).where(LeadScore.company_id == company_id)
        .order_by(LeadScore.created_at.desc()).limit(1)
    ).first()


def _recipient(db: Session, m: EmailMessage) -> str | None:
    if m.contact_id:
        c = db.get(Contact, m.contact_id)
        if c and c.email:
            return c.email
    return (m.meta or {}).get("to")


def _decision_maker(db: Session, company_id) -> str | None:
    r = db.execute(
        select(Contact.name).where(Contact.company_id == company_id,
                                   Contact.name.ilike("Dr.%"))
        .order_by(Contact.is_primary.desc()).limit(1)
    ).first()
    return r[0] if r else None


def _lead_card(db: Session, co: Company, m: EmailMessage | None) -> dict:
    """The full review card for one lead: score, qualifying signal, all reachable
    channels (phone/WhatsApp/socials) and the saved draft + DM (if one exists).
    `m` may be None — the card still returns channels + signal so the lead detail
    page can show everything and offer to draft."""
    places = (co.raw or {}).get("places") or {}
    sc = _latest_score(db, co.id)
    score, grade = (int(sc[0]) if sc and sc[0] is not None else None,
                    sc[1] if sc else None)
    to_addr = _recipient(db, m) if m else None
    return {
        "draft_id": str(m.id) if m else None,
        "draft_status": m.status if m else None,   # 'draft' | 'sent' — so a sent lead's
                                                   # content is still visible on the page
        "company_id": str(co.id),
        "company_name": co.name,
        "domain": co.domain,
        "score": score,
        "grade": grade,
        "signal": _top_signal(db, co.id),
        "subject": m.subject if m else None,
        "body": m.body if m else None,
        "to": to_addr,
        "phone": places.get("phone") or (co.raw or {}).get("phone"),
        "decision_maker": _decision_maker(db, co.id),
        "email_mx_ok": mx_ok(to_addr) if to_addr else None,
        "spam_flags": (spam_flags(m.subject) + spam_flags(m.body)) if m else [],
        "dm": (m.meta or {}).get("dm") if m else None,
        "dm_ar": (m.meta or {}).get("dm_ar") if m else None,
        "auto_reply_comeback": (m.meta or {}).get("auto_reply_comeback") if m else None,
        "edited": bool((m.meta or {}).get("edited")) if m else False,
        # LinkedIn — only when the account actually has a LinkedIn presence. Seeded from
        # the DM (or body) so there's an editable draft immediately; the user can tailor
        # it and we persist their version in meta.linkedin_dm.
        "linkedin_url": ((co.raw or {}).get("socials") or {}).get("linkedin"),
        "linkedin_dm": (
            (m.meta or {}).get("linkedin_dm")
            or (m.meta or {}).get("dm")
            or (m.body if m else None)
        ) if (m and ((co.raw or {}).get("socials") or {}).get("linkedin")) else None,
        "wa_link": wa_link(places.get("phone_intl")
                           or normalize_phone(places.get("phone"))),
        "socials": (co.raw or {}).get("socials") or {},
        # Instagram — where a med-spa OWNER actually is (62 of our leads have one, vs
        # 1 with a person-level email). Manual-only: we open the chat, never auto-send.
        "ig_handle": ig_handle(((co.raw or {}).get("socials") or {}).get("instagram")),
        "ig_dm_link": ig_dm_link(((co.raw or {}).get("socials") or {}).get("instagram")),
        "ig_profile": ig_profile(((co.raw or {}).get("socials") or {}).get("instagram")),
    }


@router.get("")
def todays_leads(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """All drafted leads awaiting manual review/send (status='draft'), best score first."""
    drafts = db.execute(
        select(EmailMessage).where(
            EmailMessage.organization_id == org.id,
            EmailMessage.status == "draft",
            EmailMessage.channel == "email",
            EmailMessage.step < 2,   # primaries here; follow-ups live on /pipeline
        )
    ).scalars().all()

    leads = []
    for m in drafts:
        co = db.get(Company, m.company_id) if m.company_id else None
        if co is None:
            continue
        leads.append(_lead_card(db, co, m))
    leads.sort(key=lambda x: (x["score"] is not None, x["score"] or 0), reverse=True)
    from app.services.sending_health import sending_health
    return {"mode": outreach_send_mode(db, org.id), "count": len(leads), "leads": leads,
            "send_window": _send_window(), "sending_health": sending_health(db, org.id)}


def _send_window() -> dict:
    """Best-time-to-send hint. Messaging outside business hours reliably hits an
    auto-responder instead of a human (the exact failure the WhatsApp tests showed),
    so nudge toward 10:00-17:00 in the UAE (GST = UTC+4, no DST)."""
    gst_hour = (datetime.utcnow().hour + 4) % 24
    good = 10 <= gst_hour < 17
    return {
        "ok": good,
        "gst_hour": gst_hour,
        "hint": ("Good time to send — it's business hours in the UAE, so a human is "
                 "likely to reply."
                 if good else
                 "Outside UAE business hours — messages now usually hit an auto-reply, "
                 "not a person. Best window: 10:00-17:00 GST."),
    }


@router.get("/company/{company_id}")
def lead_card(company_id: uuid.UUID, db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    """The same review card the /today list shows, for ONE lead — so the lead detail
    page surfaces the saved draft + DM + all channels, not a throwaway regenerate."""
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    m = _latest_message(db, org.id, company_id)   # draft OR the sent copy
    return _lead_card(db, co, m)


@router.post("/company/{company_id}/draft")
def redraft_lead(company_id: uuid.UUID, db: Session = Depends(get_db),
                 org: Organization = Depends(current_org)):
    """(Re)draft this one lead using the SAME pipeline path as the daily engine
    (local mode, dossier, booking link, decision-maker greeting) and save it, so it
    shows up here and on /today. Replaces any existing unsent draft."""
    from app.workers.outreach import draft_outreach_for_company
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    # Replace only an UNSENT draft; never delete the sent record (it's your history).
    existing = _draft_for_company(db, org.id, company_id)
    if existing is not None:
        db.delete(existing)
        db.commit()
    # force=True: an explicit manual click must always produce content, even for a
    # lead already marked sent/contacted (so you can see/reuse what you sent).
    draft_outreach_for_company(str(org.id), str(company_id), channel="email", force=True)
    m = _latest_message(db, org.id, company_id)
    return _lead_card(db, co, m)


_DISCOVER_TYPES = {"discover_companies", "discover_local", "discover_places"}
_LOCAL_TYPES = {"discover_local", "discover_places"}


@router.post("/run", status_code=202)
def run_discovery(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Trigger discovery NOW (the morning 'Run Today's Discovery' button). Runs the
    workflow matching the current discovery mode, REGARDLESS of the daily-scheduler
    'enabled' flag — in a manual sprint the workflows are intentionally off for Beat but
    still runnable on demand here. In manual send mode they draft but never send."""
    from app.workers.workflows import run_workflow_task
    all_wfs = db.execute(
        select(Workflow).where(Workflow.organization_id == org.id)
    ).scalars().all()

    def types_of(wf):
        return {s.get("type") for s in (wf.steps or [])}

    disc = [wf for wf in all_wfs if types_of(wf) & _DISCOVER_TYPES]
    from app.services.settings_resolver import pipeline_config
    dmode = pipeline_config(db, org.id)["discovery_mode"]
    if dmode == "local":
        chosen = [wf for wf in disc if types_of(wf) & _LOCAL_TYPES] or disc
    else:
        chosen = [wf for wf in disc if "discover_companies" in types_of(wf)] or disc

    kicked = []
    for wf in chosen:
        task = run_workflow_task.delay(str(wf.id))
        kicked.append({"workflow": wf.name, "task_id": task.id})
    return {"triggered": kicked, "count": len(kicked),
            "discovery_mode": dmode,
            "note": ("No discovery workflow found — seed one with "
                     "`python -m app.cli daily-workflow`." if not kicked else None)}


@router.post("/rescan", status_code=202)
def rescan_signals(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Fresh-signal re-scan NOW (also runs weekly): refresh Places facts on every
    uncontacted lead, surface new signals, retire stale ones, re-score what changed.
    Sends nothing."""
    from app.workers.signals import rescan_local_signals
    task = rescan_local_signals.delay(str(org.id))
    return {"status": "queued", "task_id": task.id}


def _draft_for_company(db: Session, org_id, company_id: uuid.UUID) -> EmailMessage | None:
    return db.execute(
        select(EmailMessage).where(
            EmailMessage.organization_id == org_id,
            EmailMessage.company_id == company_id,
            EmailMessage.status == "draft",
        ).order_by(EmailMessage.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _latest_message(db: Session, org_id, company_id: uuid.UUID) -> EmailMessage | None:
    """Latest outreach message for the lead detail page — a DRAFT if one exists, else
    the most recent SENT one. Without this, marking a lead 'sent' hides its content
    (the reader only looked for status='draft') AND re-drafting is suppressed, so the
    copy you sent becomes unreachable."""
    return db.execute(
        select(EmailMessage).where(
            EmailMessage.organization_id == org_id,
            EmailMessage.company_id == company_id,
            EmailMessage.status.in_(("draft", "sent")),
        ).order_by((EmailMessage.status == "draft").desc(),
                   EmailMessage.created_at.desc()).limit(1)
    ).scalar_one_or_none()


@router.post("/{company_id}/sent")
def mark_sent(company_id: uuid.UUID, db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    """I sent this one myself — log it, take it off the review queue, advance CRM."""
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    m = _draft_for_company(db, org.id, company_id)
    to_addr = _recipient(db, m) if m else None
    if m is not None:
        # Leave the queue + enable reply-matching if a reply lands in the connected inbox.
        m.status = "sent"
        m.sent_at = func.now()
        m.meta = {**(m.meta or {}), "manual_sent": True,
                  **({"to": to_addr} if to_addr else {})}
    if co.pipeline_stage in ("new", "qualified"):
        co.pipeline_stage = "contacted"
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=co.id, company_name=co.name,
        channel="email", action="sent", sent_by_me=True))
    db.commit()
    return {"ok": True, "company": co.name, "logged": "sent"}


@router.post("/enrich-owner-emails")
def enrich_owner_emails(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Batch: turn every qualified lead's scraped owner NAME into a verified
    decision-maker email. Runs the owner-email finder across the pool, skipping leads
    that already have a person-level address. Requires a Hunter or NeverBounce key —
    without one it reports needs_key rather than persisting an unverified guess."""
    from app.services.contacts import _email_quality
    from app.services.email_validation import _has_real_key
    from app.services.owner_email import find_owner_email
    from app.services.settings_resolver import resolve_credential
    from app.models.contact import Contact

    # A REAL key, not the demo placeholder — mirror the finder's own check
    # (hunter.py rejects keys ending in "xxx" or shorter than 20 chars) so we don't
    # promise results a placeholder key can't deliver.
    _hk = (resolve_credential(db, org.id, "hunter_api_key") or "").strip()
    has_key = (bool(_hk) and not _hk.endswith("xxx") and len(_hk) >= 20) or _has_real_key()
    leads = db.execute(
        select(Company).where(Company.organization_id == org.id,
                              Company.pipeline_stage.in_(("qualified", "contacted")),
                              Company.domain.is_not(None))
    ).scalars().all()
    scanned = found = already = 0
    for co in leads:
        # Skip leads that already have a person-level (non-front-desk) email.
        best = max((_email_quality(c.email) for c in db.execute(
            select(Contact).where(Contact.company_id == co.id,
                                  Contact.email.is_not(None))).scalars() if c.email),
            default=0)
        if best >= 2:
            already += 1
            continue
        scanned += 1
        if not has_key:
            continue
        try:
            if find_owner_email(db, co).get("found"):
                found += 1
        except Exception:
            pass
    return {
        "found": found, "scanned": scanned, "already_had": already,
        "needs_key": not has_key,
        "detail": ("Add a Hunter or NeverBounce key in Settings — the names are ready, "
                   "we just can't verify an address without it."
                   if not has_key else
                   f"Found {found} decision-maker email(s) across {scanned} leads."),
    }


@router.post("/{company_id}/find-owner-email")
def find_owner_email_now(company_id: uuid.UUID, db: Session = Depends(get_db),
                         org: Organization = Depends(current_org)):
    """Turn this lead's scraped owner NAME into a verified decision-maker email
    (vs the generic info@). Only persists an address that Hunter or a validator
    confirms — an unverified guess would bounce, so it's never saved."""
    from app.services.owner_email import find_owner_email
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    res = find_owner_email(db, co)
    if res.get("found"):
        return {"found": True, "email": res["email"], "name": res.get("name"),
                "method": res.get("method"), "card": _lead_card(db, co, _draft_for_company(db, org.id, company_id))}
    hints = {
        "no_domain": "This lead has no website — reach them on WhatsApp.",
        "no_owner_name": "No owner name found on the site to build an address from.",
        "no_verified_email": "Couldn't verify a personal address — no deliverable match.",
        "needs_hunter_or_neverbounce_key": "Add a Hunter or NeverBounce key in Settings to verify constructed addresses.",
    }
    return {"found": False, "reason": res.get("reason"),
            "detail": hints.get(res.get("reason"), "No owner email found.")}


class DraftEdit(BaseModel):
    subject: str | None = None
    body: str | None = None
    # Every channel variant is editable, not just the email. These live in message.meta.
    dm: str | None = None                    # WhatsApp / generic DM
    dm_ar: str | None = None                 # Arabic DM
    auto_reply_comeback: str | None = None   # what to send if they auto-reply
    linkedin_dm: str | None = None           # LinkedIn message


@router.patch("/{company_id}/draft")
def edit_draft(company_id: uuid.UUID, payload: DraftEdit,
               db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Save your edits to this lead's draft (subject/body) before sending. Returns the
    refreshed card so the spam-flag + MX checks re-run on YOUR wording, not the AI's."""
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    m = _draft_for_company(db, org.id, company_id)
    if m is None:
        return {"ok": False, "reason": "no_draft",
                "detail": "Generate a draft first, then edit it."}
    if payload.subject is not None:
        m.subject = payload.subject.strip()[:300]
    if payload.body is not None:
        m.body = payload.body
    meta = {**(m.meta or {}), "edited": True}
    # Persist any edited channel variant into meta (only fields that were sent).
    for field in ("dm", "dm_ar", "auto_reply_comeback", "linkedin_dm"):
        val = getattr(payload, field)
        if val is not None:
            meta[field] = val
    m.meta = meta
    db.commit()
    return {"ok": True, "card": _lead_card(db, co, m)}


@router.post("/{company_id}/send-email")
def send_email_now(company_id: uuid.UUID, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    """Actually SEND this lead's saved draft via the configured Gmail, right now.

    A deliberate, one-lead-at-a-time action (never bulk / never automatic). Every
    guard the pipeline has still applies at the boundary:
      - Gmail must be configured (else nothing is attempted);
      - the lead must not be opted-out / already-contacted (suppression_reason);
      - there must be a real recipient email, and its domain must have MX;
      - the org's daily send cap is respected.
    On success the draft flips to 'sent', the lead advances to 'contacted', and it is
    written to the manual outreach log — same end state as 'Mark as sent'.
    """
    from app.services.email_sender import (daily_cap_remaining, is_configured,
                                           send_email_message, suppression_reason)
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    if not is_configured():
        return {"sent": False, "reason": "gmail_not_configured",
                "detail": "Add a Gmail address + app password in Settings first."}

    m = _draft_for_company(db, org.id, company_id)
    if m is None:
        return {"sent": False, "reason": "no_draft",
                "detail": "Generate a draft for this lead before sending."}

    # Hard guards BEFORE we touch SMTP, with human-readable reasons.
    reason = suppression_reason(db, co)
    if reason:
        return {"sent": False, "reason": "suppressed", "detail": reason}
    to_addr = _recipient(db, m)
    if not to_addr:
        return {"sent": False, "reason": "no_recipient_email",
                "detail": "No email address found for this lead — reach them on WhatsApp."}
    if not mx_ok(to_addr):
        return {"sent": False, "reason": "bad_mx",
                "detail": f"{to_addr} has no valid mail server (MX) — it would bounce."}
    if daily_cap_remaining(db, org.id) <= 0:
        return {"sent": False, "reason": "daily_cap_reached",
                "detail": "You've hit today's send cap. Continue tomorrow."}

    result = send_email_message(db, m)   # marks sent / bounced + stores Message-ID
    if not result.get("sent"):
        return {"sent": False, "reason": result.get("reason", "send_failed"),
                "detail": result.get("reason")}

    # Same downstream bookkeeping as a manual 'Mark as sent'.
    if co.pipeline_stage in ("new", "qualified"):
        co.pipeline_stage = "contacted"
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=co.id, company_name=co.name,
        channel="email", action="sent", sent_by_me=True,
        notes=f"sent from app to {result.get('to')}"))
    db.commit()
    return {"sent": True, "to": result.get("to"), "company": co.name}


@router.get("/{company_id}/demo")
def lead_demo(company_id: uuid.UUID, db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    """A shareable WhatsApp-style demo of THIS clinic's AI receptionist booking an
    after-hours enquiry — grounded in the lead's real facts + signal, DHA-compliant,
    clearly labelled as a simulation. Returned as HTML for the owner to screenshot into
    a WhatsApp/IG chat. 'Show, don't tell' — the counter to a $97 competitor."""
    from app.services.demo_asset import build_demo_html
    from app.services.settings_resolver import settings_row
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    kinds = {k for (k,) in db.execute(
        select(Signal.kind).where(Signal.company_id == co.id))}
    s = settings_row(db, org.id)
    sender = (s.gmail_from_name if s and getattr(s, "gmail_from_name", None) else None) \
        or (org.name if getattr(org, "name", None) else "your team")
    html = build_demo_html(co, kinds, sender_name=sender,
                           doctor=_decision_maker(db, co.id))
    return {"company": co.name, "html": html}


class ReplyIn(BaseModel):
    their_message: str
    channel: str = "whatsapp"   # whatsapp | instagram | linkedin | email


@router.post("/{company_id}/log-reply")
def log_reply(company_id: uuid.UUID, body: ReplyIn, db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    """A lead replied to your DM/message. Record it, advance the lead to 'replied',
    and draft the NEXT reply with AI — grounded in what they actually said + the
    signal that qualified them. This is the manual-channel counterpart to the inbox
    poller: WhatsApp/Instagram replies never reach our webhooks, so you paste them."""
    from app.ai.outreach_engine import generate_suggested_reply
    from app.models.crm import CRMActivity
    from app.services.settings_resolver import settings_row
    from app.services.whatsapp_inbound import _driving_signal

    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    their = (body.their_message or "").strip()
    if not their:
        return {"ok": False, "reason": "empty", "detail": "Paste what they replied first."}
    channel = body.channel if body.channel in ("whatsapp", "instagram", "linkedin", "email") else "whatsapp"

    # Ground the reply in what WE actually sell + the message we last sent them, so the
    # AI continues THIS thread instead of pitching cold again.
    s = settings_row(db, org.id)
    services = getattr(s, "outreach_services", None) if s else None
    last = _latest_message(db, org.id, company_id)
    our_last = None
    if last is not None:
        meta = last.meta or {}
        our_last = meta.get("dm") or last.body or last.subject

    _mark_company_replied(db, org.id, company_id)     # stage -> replied, flip the message

    signal = _driving_signal(db, company_id)
    res = generate_suggested_reply(company={"name": co.name}, their_message=their,
                                   signal=signal, channel=channel,
                                   services=services, our_last_message=our_last)
    suggested = None if res.get("_provider_error") else res.get("suggested_response")

    # Log the inbound + suggestion as a CRM activity so it also shows on /replies.
    db.add(CRMActivity(
        organization_id=org.id, company_id=co.id, kind=channel,
        body=f"Reply received ({channel}): {their[:280]}",
        payload={"direction": "inbound", "channel": channel, "reply": their[:1200],
                 "suggested_response": suggested, "manual_logged": True}))
    db.commit()
    return {"ok": True, "company": co.name, "channel": channel,
            "suggested_response": suggested,
            "detail": None if suggested else "Reply saved. AI draft unavailable right now — reply in your own words."}


class SentVia(BaseModel):
    channel: str = "email"   # email | whatsapp | instagram | linkedin


@router.post("/{company_id}/sent-via")
def mark_sent_via(company_id: uuid.UUID, body: SentVia, db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    """'I DM'd / messaged this lead myself on <channel>' — logs the real channel so the
    funnel reflects where outreach actually happens. Instagram and WhatsApp are manual
    by design (Meta bans cold-DM automation), so this is how they enter the pipeline."""
    channel = body.channel if body.channel in ("email", "whatsapp", "instagram", "linkedin") else "email"
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    # Take the email draft off the review queue no matter which channel you used.
    #   - email  -> the draft was sent, mark it 'sent' (enables reply-matching).
    #   - wa/ig  -> you reached them another way, so 'contacted' now suppresses the
    #     email Send button. Marking the draft 'skipped' removes the lead from /today
    #     so it doesn't linger with a Send button that would just error (review #1).
    m = _draft_for_company(db, org.id, company_id)
    if m is not None:
        if channel == "email":
            m.status = "sent"
            m.sent_at = func.now()
            m.meta = {**(m.meta or {}), "manual_sent": True}
        else:
            m.status = "skipped"
            m.meta = {**(m.meta or {}), "skip_reason": f"contacted via {channel}"}
    if co.pipeline_stage in ("new", "qualified"):
        co.pipeline_stage = "contacted"
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=co.id, company_name=co.name,
        channel=channel, action="sent", sent_by_me=True,
        notes=f"manual {channel} outreach"))
    db.commit()
    return {"ok": True, "company": co.name, "channel": channel}


@router.post("/{company_id}/optout")
def optout_lead(company_id: uuid.UUID, db: Session = Depends(get_db),
                org: Organization = Depends(current_org)):
    """Opt this lead out permanently (they asked not to be contacted, or bad target):
    register its domain + all contact emails/phone on the do-not-contact list and drop
    any pending draft. Future discovery/drafting will skip it (PDPL + unsubscribe)."""
    from app.services.optout import optout_company
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    n = optout_company(db, co, reason="manual opt-out from Today", source="manual")
    m = _draft_for_company(db, org.id, company_id)
    if m is not None:
        m.status = "skipped"
        m.meta = {**(m.meta or {}), "skip_reason": "opted_out"}
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=co.id, company_name=co.name,
        channel="email", action="skipped", skip_reason="opted_out"))
    db.commit()
    return {"ok": True, "company": co.name, "identifiers_suppressed": n}


@router.post("/{company_id}/skip")
def skip_lead(company_id: uuid.UUID, body: SkipBody, db: Session = Depends(get_db),
              org: Organization = Depends(current_org)):
    """Skip this draft (with a reason) — take it off the queue, record why."""
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    m = _draft_for_company(db, org.id, company_id)
    if m is not None:
        m.status = "skipped"
        m.meta = {**(m.meta or {}), "skip_reason": body.reason}
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=co.id, company_name=co.name,
        channel="email", action="skipped", skip_reason=body.reason))
    db.commit()
    return {"ok": True, "company": co.name, "logged": "skipped", "reason": body.reason}


@router.post("/{company_id}/flag-invalid-whatsapp")
def flag_invalid_whatsapp(company_id: uuid.UUID, db: Session = Depends(get_db),
                          org: Organization = Depends(current_org)):
    """The lead's WhatsApp number is invalid/unreachable. Park it: flag it, take it off
    the Today queue, and surface it on the Invalid Numbers page to revisit later (find
    another number, or discard). Not an opt-out — the lead is fine, the number isn't."""
    from sqlalchemy.orm.attributes import flag_modified
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    co.raw = {**(co.raw or {}), "invalid_whatsapp": True}
    flag_modified(co, "raw")
    m = _draft_for_company(db, org.id, company_id)   # take it off Today
    if m is not None:
        m.status = "skipped"
        m.meta = {**(m.meta or {}), "skip_reason": "invalid_whatsapp"}
    db.commit()
    return {"ok": True, "company": co.name}


@router.post("/{company_id}/restore-number")
def restore_number(company_id: uuid.UUID, db: Session = Depends(get_db),
                   org: Organization = Depends(current_org)):
    """Un-park a lead flagged invalid-WhatsApp: clear the flag and regenerate its draft
    so it returns to Today (e.g. after you found a working number)."""
    from sqlalchemy.orm.attributes import flag_modified
    from app.workers.outreach import draft_outreach_for_company
    co = db.get(Company, company_id)
    if not co or co.organization_id != org.id:
        raise NotFound("Company")
    raw = dict(co.raw or {})
    raw.pop("invalid_whatsapp", None)
    co.raw = raw
    flag_modified(co, "raw")
    db.commit()
    draft_outreach_for_company(str(org.id), str(company_id), channel="email", force=True)
    return {"ok": True, "company": co.name}


@router.get("/invalid-numbers")
def invalid_numbers(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Leads parked because their WhatsApp number is invalid — to revisit later."""
    rows = db.execute(
        select(Company).where(
            Company.organization_id == org.id,
            Company.raw["invalid_whatsapp"].astext == "true")
        .order_by(Company.name)
    ).scalars().all()
    items = []
    for co in rows:
        places = (co.raw or {}).get("places") or {}
        phone = places.get("phone")
        sc = _latest_score(db, co.id)
        items.append({
            "company_id": str(co.id), "company_name": co.name,
            "phone": phone,
            "wa_link": wa_link(places.get("phone_intl") or normalize_phone(phone)),
            "socials": (co.raw or {}).get("socials") or {},
            "score": int(sc[0]) if sc and sc[0] is not None else None,
            "grade": sc[1] if sc else None,
        })
    return {"count": len(items), "items": items}


# ---- /log lives under the same router file but its own prefix ----
log_router = APIRouter(prefix="/log", tags=["today"])


@log_router.get("")
def manual_log(db: Session = Depends(get_db), org: Organization = Depends(current_org),
               days: int = 7):
    rows = db.execute(
        select(ManualOutreachLog).where(
            ManualOutreachLog.organization_id == org.id,
            ManualOutreachLog.created_at >= datetime.utcnow() - timedelta(days=days),
        ).order_by(ManualOutreachLog.created_at.desc())
    ).scalars().all()
    items = [{
        "id": str(r.id), "company_name": r.company_name, "channel": r.channel,
        "action": r.action, "skip_reason": r.skip_reason, "sent_by_me": r.sent_by_me,
        "replied": r.replied, "notes": r.notes, "at": r.created_at,
    } for r in rows]
    sent = sum(1 for r in rows if r.action == "sent")
    skipped = sum(1 for r in rows if r.action == "skipped")
    replied = sum(1 for r in rows if r.replied)
    return {"summary": {"reviewed": len(rows), "sent": sent, "skipped": skipped,
                        "replied": replied, "days": days}, "items": items}


@log_router.patch("/{log_id}")
def update_log(log_id: uuid.UUID, body: LogUpdate, db: Session = Depends(get_db),
               org: Organization = Depends(current_org)):
    r = db.get(ManualOutreachLog, log_id)
    if not r or r.organization_id != org.id:
        raise NotFound("LogEntry")
    if body.replied is not None:
        r.replied = body.replied
        # AUDIT B7: ticking 'replied' on the log used to change nothing else, so the
        # company sat at 'contacted' forever and the reply never entered the pipeline.
        # Advance the CRM stage + the message so /pipeline and suppression both see it.
        if body.replied and r.company_id:
            _mark_company_replied(db, org.id, r.company_id)
    if body.notes is not None:
        r.notes = body.notes
    db.commit()
    return {"ok": True, "replied": r.replied, "notes": r.notes}


def _mark_company_replied(db: Session, org_id, company_id: uuid.UUID) -> bool:
    """Single place that records 'they replied': advance the CRM stage and flip the
    sent message to 'replied' so the funnel, /pipeline and follow-up suppression agree."""
    co = db.get(Company, company_id)
    if not co or co.organization_id != org_id:
        return False
    if co.pipeline_stage in ("new", "qualified", "contacted"):
        co.pipeline_stage = "replied"
    m = db.execute(
        select(EmailMessage).where(EmailMessage.company_id == company_id,
                                   EmailMessage.status == "sent")
        .order_by(EmailMessage.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if m is not None:
        m.status = "replied"
        m.replied_at = func.now()
    return True


@router.post("/{company_id}/replied")
def mark_replied(company_id: uuid.UUID, db: Session = Depends(get_db),
                 org: Organization = Depends(current_org)):
    """'They replied to me' — the manual counterpart to the IMAP poller. Without this,
    a reply that lands in Gmail leaves the lead stuck at 'contacted' forever (audit B7)."""
    if not _mark_company_replied(db, org.id, company_id):
        raise NotFound("Company")
    log_row = db.execute(
        select(ManualOutreachLog).where(ManualOutreachLog.company_id == company_id)
        .order_by(ManualOutreachLog.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if log_row is not None:
        log_row.replied = True
    db.commit()
    return {"ok": True, "stage": "replied"}


# ---- /pipeline: follow-up sequence view --------------------------------------
pipeline_router = APIRouter(prefix="/pipeline", tags=["today"])


@pipeline_router.post("/refresh", status_code=200)
def refresh_followups(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Draft any due day-3 / day-6 follow-ups for sent-but-unreplied leads."""
    from app.workers.outreach import draft_followups_for_org
    return draft_followups_for_org(db, org.id)


@pipeline_router.get("")
def pipeline(db: Session = Depends(get_db), org: Organization = Depends(current_org)):
    """Sent leads + any follow-up drafts ready to send (the 'Follow-up ready' queue)."""
    from datetime import datetime
    from app.models.manual_outreach import ManualOutreachLog
    logs = db.execute(
        select(ManualOutreachLog).where(
            ManualOutreachLog.organization_id == org.id,
            ManualOutreachLog.action == "sent",
        ).order_by(ManualOutreachLog.created_at.desc())
    ).scalars().all()
    now = datetime.utcnow()
    seen: set = set()
    out = []
    for lg in logs:
        if not lg.company_id or lg.company_id in seen:
            continue
        seen.add(lg.company_id)
        co = db.get(Company, lg.company_id)
        if co is None:
            continue
        age = (now - lg.created_at.replace(tzinfo=None)).days if lg.created_at else 0
        fups = db.execute(
            select(EmailMessage).where(EmailMessage.company_id == co.id,
                                       EmailMessage.step >= 2,
                                       EmailMessage.status == "draft")
            .order_by(EmailMessage.step)
        ).scalars().all()
        out.append({
            "company_id": str(co.id), "company_name": co.name,
            "sent_days_ago": age, "replied": lg.replied or co.pipeline_stage == "replied",
            "followups_ready": [{
                "draft_id": str(m.id), "step": m.step,
                "day": (m.meta or {}).get("followup_day"),
                "subject": m.subject, "body": m.body,
                "to": _recipient(db, m),
            } for m in fups],
        })
    return {"leads": out}


@pipeline_router.post("/{draft_id}/sent")
def followup_sent(draft_id: uuid.UUID, db: Session = Depends(get_db),
                  org: Organization = Depends(current_org)):
    """I sent this follow-up myself — take it off the queue + log it."""
    m = db.get(EmailMessage, draft_id)
    if not m or m.organization_id != org.id:
        raise NotFound("Draft")
    m.status = "sent"
    m.sent_at = func.now()
    m.meta = {**(m.meta or {}), "manual_sent": True}
    co = db.get(Company, m.company_id) if m.company_id else None
    db.add(ManualOutreachLog(
        organization_id=org.id, company_id=m.company_id,
        company_name=(co.name if co else "lead"), channel="email",
        action="sent", sent_by_me=True))
    db.commit()
    return {"ok": True, "step": m.step}
