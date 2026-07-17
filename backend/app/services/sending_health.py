"""Sending health — the early-warning system for your sending account.

Cold outreach dies two ways, and neither announces itself:

  1. BOUNCES. Scraped addresses go stale. Mailbox providers read a bounce rate above
     ~2% as "this sender doesn't know who they're mailing" — it is a STRONGER
     suspension signal than spam complaints, and it is the realistic risk when every
     address came off a website rather than an opt-in.
  2. VOLUME on a cold-reputation account. A brand-new domain (or a personal Gmail with
     no sending history) that jumps to daily volume looks exactly like a spammer.

So this reports the two numbers that actually predict trouble, plus what kind of
account you're sending from — because the same 15 emails/day is routine from a warmed
domain and reckless from a personal Gmail whose loss would take your Drive, Photos and
2FA recovery with it.

Read-only: it measures, it never blocks. The send guards do the blocking.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.campaign import EmailMessage

# Industry thresholds (Google/Yahoo bulk-sender era).
BOUNCE_WARN = 2.0     # % — the level providers start treating as a bad list
BOUNCE_CRIT = 5.0     # % — suspension territory
FRESH_DOMAIN_SAFE_DAILY = 30   # /day ceiling while an account has no warm reputation

_ATTEMPTED = ("sent", "replied", "bounced")   # a real delivery attempt happened


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def sending_health(db: Session, organization_id) -> dict:
    """Bounce rate, today's volume vs cap, and the account-risk read."""
    from app.services.email_sender import sent_today_count
    from app.services.settings_resolver import resolve_caps, settings_row

    since = datetime.utcnow() - timedelta(days=30)

    def _count(*statuses: str, windowed: bool = True) -> int:
        q = select(func.count(EmailMessage.id)).where(
            EmailMessage.organization_id == organization_id,
            EmailMessage.status.in_(statuses),
        )
        if windowed:
            q = q.where(EmailMessage.created_at >= since)
        return db.execute(q).scalar_one() or 0

    attempted = _count(*_ATTEMPTED)
    bounced = _count("bounced")
    replied = _count("replied")
    bounce_rate = _pct(bounced, attempted)
    reply_rate = _pct(replied, attempted)

    _run_cap, per_day = resolve_caps(db, organization_id)
    sent_today = sent_today_count(db, organization_id)

    s = settings_row(db, organization_id)
    from_addr = (s.gmail_address if s else None) or ""
    domain = from_addr.split("@")[-1].lower() if "@" in from_addr else None
    # A free consumer mailbox has no domain reputation you can build or isolate — and
    # losing it costs far more than losing a sending domain.
    personal = domain in ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com",
                          "icloud.com", "live.com", "protonmail.com")

    issues: list[dict] = []
    if attempted >= 10 and bounce_rate >= BOUNCE_CRIT:
        issues.append({"level": "critical", "text":
                       f"Bounce rate {bounce_rate}% — above {BOUNCE_CRIT}%. Stop sending "
                       f"to scraped addresses and verify before every send."})
    elif attempted >= 10 and bounce_rate >= BOUNCE_WARN:
        issues.append({"level": "warning", "text":
                       f"Bounce rate {bounce_rate}% — over the {BOUNCE_WARN}% line "
                       f"providers treat as a bad list. Check MX before sending."})
    if personal:
        issues.append({"level": "warning", "text":
                       f"Sending from a personal {domain} account. Fine for a few "
                       f"hand-sent emails; a suspension would take your whole Google "
                       f"account, not just outreach. Move to a dedicated domain before volume."})
    if sent_today > FRESH_DOMAIN_SAFE_DAILY:
        issues.append({"level": "warning", "text":
                       f"{sent_today} sent today — above the {FRESH_DOMAIN_SAFE_DAILY}/day "
                       f"ceiling that's safe on an account with no warmed reputation."})
    if attempted < 10:
        issues.append({"level": "info", "text":
                       f"Only {attempted} delivery attempts so far — bounce rate isn't "
                       f"meaningful yet. Treat it as unknown, not good."})

    level = ("critical" if any(i["level"] == "critical" for i in issues)
             else "warning" if any(i["level"] == "warning" for i in issues)
             else "ok")
    return {
        "status": level,
        "bounce_rate": bounce_rate if attempted else None,
        "reply_rate": reply_rate if attempted else None,
        "attempted_30d": attempted,
        "bounced_30d": bounced,
        "replied_30d": replied,
        "sent_today": sent_today,
        "daily_cap": per_day,
        "cap_remaining": max(0, per_day - sent_today),
        "from_address": from_addr or None,
        "personal_account": personal,
        "issues": issues,
    }
