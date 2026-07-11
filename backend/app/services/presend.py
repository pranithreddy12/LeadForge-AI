"""Pre-send checks for the manual review (Today) page: a free MX-record validity check
(via DNS-over-HTTPS, no extra dependency) and a spammy-phrase flagger."""
from __future__ import annotations

import re

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

_MX_CACHE: dict[str, bool | None] = {}


def mx_ok(email: str | None) -> bool | None:
    """True if the email's domain has MX records (can receive mail), False if none,
    None if the check couldn't run. Uses Google's DoH resolver — free, no package."""
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[-1].strip().lower()
    if not domain:
        return None
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]
    try:
        r = httpx.get("https://dns.google/resolve",
                      params={"name": domain, "type": "MX"}, timeout=6.0)
        r.raise_for_status()
        data = r.json()
        ok = bool(data.get("Answer")) and data.get("Status") == 0
    except Exception as e:
        log.info("mx_check_failed", domain=domain, error=str(e)[:120])
        _MX_CACHE[domain] = None
        return None
    _MX_CACHE[domain] = ok
    return ok


def _txt_records(name: str) -> list[str] | None:
    """All TXT strings for a DNS name via DoH; None if the lookup itself failed."""
    try:
        r = httpx.get("https://dns.google/resolve",
                      params={"name": name, "type": "TXT"}, timeout=6.0)
        r.raise_for_status()
        data = r.json()
        if data.get("Status") != 0:
            return []
        return [str(a.get("data") or "").strip('"').replace('" "', "")
                for a in (data.get("Answer") or []) if a.get("type") == 16]
    except Exception as e:
        log.info("txt_lookup_failed", name=name, error=str(e)[:120])
        return None


_DKIM_SELECTORS = ("google", "default", "selector1", "selector2", "k1", "mail", "smtp",
                   "20230601", "20221208", "20161025")  # Google's date-based selectors


def domain_auth(domain: str) -> dict:
    """Deliverability preflight for a SENDING domain (2024+ Gmail/Yahoo bulk-sender
    rules): SPF + DMARC via TXT lookups, DKIM by probing common selectors, MX.
    Every result cites the actual DNS record found — nothing inferred."""
    domain = (domain or "").strip().lower().lstrip("@")
    out: dict = {"domain": domain, "spf": {"found": False, "record": None},
                 "dmarc": {"found": False, "policy": None, "record": None},
                 "dkim": {"found": False, "selector": None},
                 "mx": None, "verdict": "unknown", "notes": []}
    if not domain or "." not in domain:
        out["notes"].append("No valid domain to check.")
        return out

    txts = _txt_records(domain)
    if txts is None:
        out["notes"].append("DNS lookup failed - try again.")
        return out
    for t in txts:
        if t.lower().startswith("v=spf1"):
            out["spf"] = {"found": True, "record": t[:200]}
            break

    dmarc_txts = _txt_records(f"_dmarc.{domain}") or []
    for t in dmarc_txts:
        if "v=dmarc1" in t.lower():
            m = re.search(r"\bp\s*=\s*(none|quarantine|reject)", t, re.I)
            out["dmarc"] = {"found": True,
                            "policy": (m.group(1).lower() if m else None),
                            "record": t[:200]}
            break

    for sel in _DKIM_SELECTORS:
        recs = _txt_records(f"{sel}._domainkey.{domain}") or []
        if any("v=dkim1" in t.lower() or "k=rsa" in t.lower() or "p=" in t for t in recs):
            out["dkim"] = {"found": True, "selector": sel}
            break
    if not out["dkim"]["found"]:
        out["notes"].append("No DKIM key at common selectors - it may use a custom "
                            "selector; check your email provider's DNS instructions.")

    out["mx"] = mx_ok(f"check@{domain}")

    if out["spf"]["found"] and out["dmarc"]["found"]:
        out["verdict"] = "pass" if out["dmarc"]["policy"] in ("quarantine", "reject") \
            or out["dkim"]["found"] else "partial"
    else:
        out["verdict"] = "fail"
        if not out["spf"]["found"]:
            out["notes"].append("Missing SPF record - Gmail hard-rejects bulk mail "
                                "without it (since Nov 2025).")
        if not out["dmarc"]["found"]:
            out["notes"].append("Missing DMARC record (_dmarc TXT) - required by "
                                "Gmail/Yahoo sender rules.")
    if out["dmarc"]["found"] and out["dmarc"]["policy"] == "none":
        out["notes"].append("DMARC policy is p=none (monitor-only) - fine to start; "
                            "move to quarantine/reject once reports look clean.")
    return out


# Spammy phrases + patterns that hurt deliverability / read as spam.
_SPAM_PHRASES = (
    # Full blocklist mirrored from the drafting prompt so a draft that slips one through
    # is auto-flagged before it reaches you.
    "never miss a call", "never miss another", "never miss a lead", "never miss again",
    "instant lead response", "24/7 booking", "24-7 booking", "boost your revenue",
    "guaranteed", "guarantee", "act now", "limited time", "free trial", "revolutionary",
    "cutting-edge", "cutting edge", "game-changer", "game changer",
    "risk free", "risk-free", "100% free", "click here", "buy now", "cash",
    "free money", "no obligation", "winner", "congratulations you", "increase sales",
    "double your", "triple your", "!!!",
    # DHA (UAE health-ad) prohibited-claim style — should never appear in outreach
    # to or about a medical/aesthetic business.
    "best clinic", "100% success", "guaranteed results", "no. 1 clinic", "#1 clinic",
    "books the treatment",
    # AUDIT B9 — FALSE SOCIAL PROOF. The sender has no clinic/spa/dental clients yet,
    # so any phrasing implying a track record in the vertical is a lie. Flag it before
    # it reaches a prospect who can trivially ask "which clinics?".
    "clinics like yours", "practices like yours", "spas like yours",
    "i've seen clinics", "ive seen clinics", "i have seen clinics",
    "we work with clinics", "we work with spas", "our clients", "our other clients",
    "we've helped", "weve helped", "we have helped", "other clinics we",
    "clients we work with", "case studies show", "our customers",
)
_CAPS_RE = re.compile(r"\b[A-Z]{4,}\b")


def spam_flags(text: str | None) -> list[str]:
    """Soft warnings for a draft: excessive exclamation, spammy phrases, ALL-CAPS words."""
    if not text:
        return []
    flags: list[str] = []
    low = text.lower()
    ex = text.count("!")
    if ex >= 3:
        flags.append(f"{ex} exclamation marks")
    elif ex >= 1:
        flags.append("exclamation mark")
    for p in _SPAM_PHRASES:
        if p in low:
            flags.append(f'spammy phrase: "{p}"')
    caps = [w for w in set(_CAPS_RE.findall(text))
            if w not in ("FREE", "ASAP")]  # allow a couple common acronyms out
    # Ignore short all-caps that are likely acronyms/initialisms handled above.
    caps = [w for w in caps if len(w) >= 4]
    if caps:
        flags.append("ALL-CAPS words: " + ", ".join(sorted(caps)[:4]))
    return flags
