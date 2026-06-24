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


def notify_reply(*, contact_name: str, company_name: str, subject: str,
                 snippet: str, company_id: str | None = None) -> bool:
    app_url = settings.app_public_url.rstrip("/")
    link = f"\n{app_url}/leads/{company_id}" if company_id else ""
    text = (
        "<b>📨 New reply!</b>\n"
        f"<b>{_esc(contact_name)}</b> at <b>{_esc(company_name)}</b> replied\n"
        f"<i>Re: {_esc(subject)}</i>\n\n"
        f"{_esc(snippet[:300])}{link}"
    )
    return send_message(text)


def _esc(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
