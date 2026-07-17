from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; LeadForgeBot/1.0; +https://leadforge.ai/bot)"


# ---- SSRF guard -----------------------------------------------------------
# Enrichment scrapes attacker-influenced domains (company.domain, search-result
# URLs). Without this, a user could point a domain at localhost, cloud-metadata
# (169.254.169.254), or internal services (redis, postgres) and exfiltrate them.

_BLOCKED_HOSTNAMES = {
    "localhost", "metadata.google.internal", "metadata", "redis", "postgres",
    "db", "api", "worker", "beat", "host.docker.internal",
}


def _ip_is_public(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
        # IPv4-mapped IPv6 (::ffff:127.0.0.1) and 169.254 link-local are covered
        # by is_link_local / is_private above.
    )


def url_is_safe(url: str) -> bool:
    """Reject non-http(s) schemes and any host that resolves to a non-public IP."""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    if host.lower() in _BLOCKED_HOSTNAMES:
        return False
    # A bare IP literal — validate directly.
    try:
        ipaddress.ip_address(host)
        return _ip_is_public(host)
    except ValueError:
        pass
    # Hostname — resolve every address and require ALL to be public.
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    addrs = {info[4][0] for info in infos}
    if not addrs:
        return False
    return all(_ip_is_public(a) for a in addrs)


def _guard(url: str) -> bool:
    if url_is_safe(url):
        return True
    log.warning("ssrf_blocked_url", url=url[:200])
    return False


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)[:30_000]


def fetch_static(url: str, *, timeout: float = 15.0, allow_playwright: bool = True) -> str:
    """Cheap static fetch; falls back to Playwright when content looks JS-shelled.
    Pass allow_playwright=False for fast, best-effort static-only fetches (e.g. bulk
    name scraping) that must not pay the headless-browser cost per page."""
    if not _guard(url):
        return ""
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                          timeout=timeout, max_redirects=3) as client:
            r = client.get(url)
            # Re-validate the final URL after redirects (defends against redirect-to-internal).
            if str(r.url) != url and not _guard(str(r.url)):
                return ""
            r.raise_for_status()
            text = _strip_html(r.text)
            if len(text) >= 400:
                return text
    except Exception as e:
        log.info("static_fetch_failed", url=url, error=str(e))

    if not (allow_playwright and settings.feature_playwright_scrape):
        return ""

    if not _guard(url):   # re-check before the headless browser navigates
        return ""
    try:
        return asyncio.run(_fetch_playwright(url))
    except Exception as e:
        log.warning("playwright_fetch_failed", url=url, error=str(e))
        return ""


async def _fetch_playwright(url: str) -> str:
    """Render a JS-heavy page with Playwright Chromium."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(800)
            html = await page.content()
        finally:
            await browser.close()
    return _strip_html(html)


def fetch_raw_html(url: str, *, timeout: float = 15.0) -> str:
    """Fetch the RAW html (scripts/links intact) for tech-stack fingerprinting.
    Unlike fetch_static this does NOT strip tags — the markers we look for live
    in <script src>, <link>, and inline JS. Static-only (no Playwright) to keep
    it cheap; most tech markers are present in the initial HTML."""
    if not _guard(url):
        return ""
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                          timeout=timeout, max_redirects=3) as client:
            r = client.get(url)
            if str(r.url) != url and not _guard(str(r.url)):
                return ""
            r.raise_for_status()
            return r.text[:400_000]
    except Exception as e:
        log.info("raw_fetch_failed", url=url, error=str(e))
        return ""


# ---- contact-email scraping (no API; SSRF-guarded via fetch_raw_html) ----------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_CONTACT_PATHS = ("", "/contact", "/contact-us", "/contactus", "/about",
                  "/about-us", "/company", "/team", "/get-in-touch", "/support")
# local-parts/domains that are never a real outreach address
_EMAIL_JUNK_LOCAL = ("noreply", "no-reply", "donotreply", "postmaster", "abuse",
                     "mailer-daemon", "example", "your", "name", "email", "user")
# Recruiting / HR inboxes — pitching these reads as careless and never reaches a
# buyer, so they're dropped from outreach entirely. Matched as the WHOLE local-part
# or a clear prefix ("careers", "careers-uae", "hr.dubai"), NOT as a substring — else
# "sarah.roberts" would falsely match "hr" and "christopher" would match "chr".
_ROLE_JUNK = ("careers", "career", "jobs", "job", "recruit", "recruitment",
              "recruiting", "hr", "humanresources", "hiring", "cv", "cvs",
              "vacancy", "vacancies", "apply", "applications", "resume", "resumes",
              "talent", "internship", "internships")


def _is_recruiting_local(local: str) -> bool:
    """True if the mailbox is a recruiting/HR inbox (careers@, hr@, jobs.uae@ ...)."""
    lp = local.lower()
    for r in _ROLE_JUNK:
        if lp == r or lp.startswith(r + ".") or lp.startswith(r + "-") \
                or lp.startswith(r + "_") or lp.startswith(r + "@"):
            return True
    return False
_EMAIL_ASSET_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css",
                       ".js", ".ico", ".woff", ".woff2")
_EMAIL_JUNK_DOMAINS = ("example.com", "sentry.io", "wixpress.com", "godaddy.com",
                       "schema.org", "w3.org", "domain.com", "email.com", "yourdomain.com")


def _registrable(host: str) -> str:
    parts = (host or "").lower().lstrip("www.").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else (host or "").lower()


def scrape_emails_for_domain(domain: str, *, max_pages: int = 6) -> list[str]:
    """Scrape role/contact emails from a company's own website (homepage + common
    contact/about pages). Returns deduped, on-domain emails only — no external API.
    Junk (noreply, asset filenames, third-party domains) is filtered out."""
    if not domain:
        return []
    reg = _registrable(domain)
    found: dict[str, None] = {}
    for path in _CONTACT_PATHS[:max_pages]:
        html = fetch_raw_html(f"https://{domain}{path}")
        if not html:
            continue
        for raw in _EMAIL_RE.findall(html):
            e = raw.strip().strip(".").lower()
            local, _, dom = e.partition("@")
            if not dom or dom in _EMAIL_JUNK_DOMAINS:
                continue
            if e.endswith(_EMAIL_ASSET_SUFFIX):
                continue
            if any(j in local for j in _EMAIL_JUNK_LOCAL):
                continue
            if _is_recruiting_local(local):   # careers@ / hr@ / jobs@ — never outreach
                continue
            # only the company's OWN domain (drop partner/CDN/tracking emails)
            if _registrable(dom) != reg:
                continue
            found.setdefault(e, None)
    return list(found.keys())


# ---- decision-maker (dentist/owner) name scraping -------------------------------

_DR_RE = re.compile(r"\bDr\.?\s+([A-Z][a-zA-Z'\-]{1,}\s+[A-Z][a-zA-Z'\-]{1,})\b")
# Words that follow "Dr." but are NOT a person (street names, section headers, etc.)
_NAME_STOP = {
    "Blvd", "Suite", "Street", "St", "Ave", "Avenue", "Road", "Rd", "Drive", "Dr",
    "Dental", "Office", "Clinic", "Group", "Care", "Health", "Today", "Now", "Here",
    "Our", "The", "Us", "Team", "Pepper", "Who", "Why", "What", "Phone", "Email",
    "Address", "Google", "Reviews", "Recommended", "Visit", "Welcome", "Meet", "About",
    "Martin", "King", "Parkway", "Pkwy", "Lane", "Ln", "Court", "Ct", "Way", "North",
    "South", "East", "West", "New", "Family", "Smile", "Smiles", "Practice",
    "Executive", "Coach", "Marketing", "Strategist", "Consultant", "Author", "Speaker",
    "Founder", "CEO", "President", "Owner", "Reviews", "Patients", "Insurance",
    "Emergency", "Cosmetic", "General", "Pediatric", "Implant", "Sedation",
}
_PERSON_PATHS = ("/about", "/about-us", "/team", "/our-team", "/meet-the-team",
                 "/meet-the-doctor", "/doctors", "/our-doctors", "/dentists", "/staff",
                 "/providers", "/our-dentist", "")


_CRED = {"DMD", "DDS", "MD", "PHD", "JR", "SR", "II", "III", "FAGD", "MS", "MAGD"}


def _clean_person(name: str) -> str:
    toks = name.split()
    while toks and toks[-1].strip(".,").upper() in _CRED:
        toks.pop()
    return " ".join(toks)


def scrape_decision_makers(domain: str, *, max_static_pages: int = 8) -> list[str]:
    """Best-effort: pull dentist/owner names ('Dr. Jane Smith') from a practice's
    About/Team/Doctors pages. Returns unique 'Dr. <Name>' strings, most-frequent first.
    STATIC-ONLY (no Playwright) so it stays fast per company. SSRF-guarded. Filters
    street-name / header false positives + credential suffixes (DMD/DDS)."""
    if not domain:
        return []
    freq: dict[str, int] = {}
    fetched = 0
    for path in _PERSON_PATHS:
        if fetched >= max_static_pages:
            break
        text = fetch_static(f"https://{domain}{path}", timeout=8.0, allow_playwright=False)
        if not text:
            continue
        fetched += 1
        for m in _DR_RE.finditer(text):
            name = _clean_person(re.sub(r"\s+", " ", m.group(1)).strip())
            parts = name.split()
            if len(parts) < 2 or parts[0] in _NAME_STOP or any(w in _NAME_STOP for w in parts):
                continue  # require First + Last, no header/street tokens
            freq[f"Dr. {name}"] = freq.get(f"Dr. {name}", 0) + 1
    names = [n for n, _ in sorted(freq.items(), key=lambda x: -x[1])]
    # Drop a name that is a strict prefix of a longer captured one ("Dr. John" vs
    # "Dr. John Glennon").
    out = [n for n in names if not any(o != n and o.startswith(n + " ") for o in names)]
    return out[:5]


_PHONE_RE = re.compile(
    r"(?<!\d)(\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)")
_PHONE_PATHS = ("", "/contact", "/contact-us", "/about")


def scrape_phone(domain: str) -> str | None:
    """Best-effort practice phone from the homepage/contact page (static-only, fast)."""
    if not domain:
        return None
    for path in _PHONE_PATHS:
        text = fetch_static(f"https://{domain}{path}", timeout=8.0, allow_playwright=False)
        if not text:
            continue
        m = _PHONE_RE.search(text)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip()
    return None


# ---- social-profile scraping (their own site links its socials) -----------------

# platform -> (url regex, junk path fragments to reject)
_SOCIAL_PATTERNS: dict[str, tuple[re.Pattern, tuple[str, ...]]] = {
    "instagram": (re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]{2,40})/?", re.I),
                  ("/p/", "/reel/", "/explore", "/accounts", "sharer")),
    "facebook": (re.compile(r"https?://(?:www\.)?facebook\.com/([A-Za-z0-9_.\-]{2,60})/?", re.I),
                 ("sharer", "share.php", "/plugins", "/dialog", "photo.php", "/events/",
                  "/posts/", "/watch")),
    "linkedin": (re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(company|in)/([A-Za-z0-9_.\-%]{2,80})/?", re.I),
                 ("/share", "shareArticle")),
    "tiktok": (re.compile(r"https?://(?:www\.)?tiktok\.com/@([A-Za-z0-9_.]{2,40})/?", re.I),
               ("/video/",)),
    "youtube": (re.compile(r"https?://(?:www\.)?youtube\.com/(@[A-Za-z0-9_.\-]{2,60}|channel/[A-Za-z0-9_\-]{10,40})/?", re.I),
                ("/watch", "/embed", "/shorts")),
    "whatsapp": (re.compile(r"https?://(?:wa\.me|api\.whatsapp\.com/send)[^\s\"'<>]*", re.I),
                 ()),
}
_SOCIAL_GENERIC = {"instagram": ("instagram", "accounts"), "facebook": ("facebook", "pages")}


def scrape_social_links(domain: str, *, max_pages: int = 3) -> dict[str, str]:
    """Pull the business's OWN social profiles (Instagram/Facebook/LinkedIn/TikTok/
    YouTube + a site-published WhatsApp link) from its website header/footer.
    Static-only (fast), SSRF-guarded. Returns {platform: url} — first hit per platform,
    share/post links rejected. Self-attributed by construction (their site, their links)."""
    if not domain:
        return {}
    out: dict[str, str] = {}
    for path in ("", "/contact", "/contact-us")[:max_pages]:
        html = fetch_raw_html(f"https://{domain}{path}")
        if not html:
            continue
        for platform, (rx, junk) in _SOCIAL_PATTERNS.items():
            if platform in out:
                continue
            for m in rx.finditer(html):
                url = m.group(0).rstrip("/\"'")
                low = url.lower()
                if any(j in low for j in junk):
                    continue
                # reject bare platform homepages ("instagram.com/") and generic slugs
                handle = (m.group(1) if m.lastindex else "").lower().strip("/")
                if platform in _SOCIAL_GENERIC and handle in _SOCIAL_GENERIC[platform]:
                    continue
                out[platform] = url
                break
        if len(out) >= len(_SOCIAL_PATTERNS):
            break
    return out


# Heuristics for finding the careers/jobs page of a domain.
CAREER_HINT_PATTERNS = [
    "/careers", "/jobs", "/work-with-us", "/join", "/hiring",
    "lever.co", "greenhouse.io", "ashbyhq.com", "workable.com",
]


def looks_like_careers_url(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in CAREER_HINT_PATTERNS)
