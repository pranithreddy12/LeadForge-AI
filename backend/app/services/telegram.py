"""Telegram notifications via the Bot API.

Setup (one-time):
  1. Message @BotFather on Telegram → /newbot → get TELEGRAM_BOT_TOKEN
  2. Message your new bot once, then visit
     https://api.telegram.org/bot<token>/getUpdates to find your chat id
     (or message @userinfobot). Put it in TELEGRAM_CHAT_ID.

Every send is best-effort: a missing config or network error is logged, never
raised, so a notification failure can't break the workflow that triggered it.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_message(text: str, *, parse_mode: str = "HTML",
                 chat_id: str | None = None) -> bool:
    """Send a Telegram message. Returns True on success, False otherwise."""
    if not is_configured():
        log.info("telegram_not_configured")
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": chat_id or settings.telegram_chat_id,
                "text": text[:4000],
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10.0,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("telegram_send_failed", error=str(e))
        return False


def notify_daily_summary(*, found: int, scored: int, hot: int, drafted: int,
                         sent: int, top: list[str]) -> bool:
    lines = [
        "<b>🚀 LeadForge — daily run complete</b>",
        f"• <b>{found}</b> new leads found & qualified",
        f"• <b>{scored}</b> scored, <b>{hot}</b> hot (A/B)",
        f"• <b>{drafted}</b> outreach drafts written" + (f", <b>{sent}</b> sent" if sent else ""),
    ]
    if top:
        lines.append("\n<b>Top accounts:</b>")
        lines += [f"  • {t}" for t in top[:5]]
    return send_message("\n".join(lines))


def notify_reply_rich(*, channel: str, company_name: str, city: str | None = None,
                      grade: str | None = None, score: int | None = None,
                      signal: str | None = None, reply_text: str = "",
                      suggested_response: str | None = None,
                      phone: str | None = None, email: str | None = None,
                      company_id: str | None = None) -> bool:
    """Unified, actionable reply alert for BOTH email and WhatsApp (Section 4A):
    who replied, why we reached out (grade/score + driving signal), their message, an
    AI-suggested next response (omitted on LLM error), and their contact handles."""
    app_url = settings.app_public_url.rstrip("/")
    link = f"\n{app_url}/replies" if company_id else ""
    where = f" {_esc(city)}" if city else ""
    grade_line = ""
    if grade or score is not None:
        grade_line = f"\nScore: {_esc(grade) or '?'}/{score if score is not None else '?'}"
        if signal:
            grade_line += f" | Signal: {_esc(signal)}"
    lines = [
        "<b>REPLY RECEIVED</b>",
        f"<b>{_esc(company_name)}</b>{where}{grade_line}",
        f"Channel: {_esc(channel)}",
        f"\n<b>Their message:</b>\n{_esc(reply_text[:600])}",
    ]
    if suggested_response:
        lines.append(f"\n<b>Suggested response:</b>\n{_esc(suggested_response[:800])}")
    contact_bits = []
    if phone:
        contact_bits.append(f"Phone: {_esc(phone)}")
    if email:
        contact_bits.append(f"Email: {_esc(email)}")
    if contact_bits:
        lines.append("\n" + "\n".join(contact_bits))
    return send_message("\n".join(lines) + link)


def notify_whatsapp_reply(*, company_name: str, city: str | None, grade: str | None,
                          score: int | None, signal: str | None, reply_text: str,
                          suggested_response: str | None = None,
                          phone: str | None = None, email: str | None = None,
                          company_id: str | None = None) -> bool:
    """Thin WhatsApp wrapper over notify_reply_rich (kept for call-site clarity)."""
    return notify_reply_rich(
        channel="WhatsApp", company_name=company_name, city=city, grade=grade,
        score=score, signal=signal, reply_text=reply_text,
        suggested_response=suggested_response, phone=phone, email=email,
        company_id=company_id)


def _esc(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
