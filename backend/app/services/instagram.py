"""Instagram as a first-class outreach channel.

For UAE med-spas Instagram is where the OWNER actually is — 62 of our leads have an
IG profile vs exactly 1 with a person-level email. This module turns a scraped profile
URL into a handle + a direct-message link, so a DM is one click from /today.

Deliberately MANUAL-ONLY: there is no Instagram send API here, and that is a feature.
Meta bans cold DM automation (7-day restriction on the first detected wave, 30-day on
the second, permanent for blasting), and unofficial API wrappers carry ~11-17% quarterly
ban risk vs 0.4% for official ones. So we open the chat and you type/paste — the app
never sends on your behalf, which is the only safe way to use this channel.
"""
from __future__ import annotations

import re

# Not a person/brand handle we can DM — IG's own routes and common junk.
_RESERVED = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "direct",
             "about", "developer", "legal", "privacy", "terms", "help", "web",
             "invites", "contact", "share", "s"}

_IG_URL = re.compile(
    r"^(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?", re.I)


def handle_from_url(url: str | None) -> str | None:
    """'https://www.instagram.com/lavidaclinic.ae/?hl=en' -> 'lavidaclinic.ae'.
    Returns None for a non-profile URL (a post/reel link isn't a DM-able account)."""
    if not url:
        return None
    m = _IG_URL.match(url.strip())
    if not m:
        return None
    h = m.group(1).strip(" ./")
    if not h or h.lower() in _RESERVED or len(h) > 30:
        return None
    return h


def dm_link(url_or_handle: str | None) -> str | None:
    """A link that opens the DM composer for that account.

    ig.me/m/<handle> is Instagram's own official message deep-link: on mobile it opens
    the app's chat, on desktop it lands in the web inbox. Falls back to nothing rather
    than guessing a URL that would 404 in front of the user.
    """
    if not url_or_handle:
        return None
    h = handle_from_url(url_or_handle) or (
        url_or_handle.lstrip("@").strip()
        if re.fullmatch(r"@?[A-Za-z0-9_.]{1,30}", url_or_handle or "") else None)
    if not h or h.lower() in _RESERVED:
        return None
    return f"https://ig.me/m/{h}"


def profile_link(url_or_handle: str | None) -> str | None:
    """The public profile — for a quick look before you DM (are they active? is this
    really the clinic?). Prefer checking this over blind-DMing."""
    h = handle_from_url(url_or_handle) or (
        url_or_handle.lstrip("@").strip()
        if re.fullmatch(r"@?[A-Za-z0-9_.]{1,30}", url_or_handle or "") else None)
    return f"https://www.instagram.com/{h}" if h else None
