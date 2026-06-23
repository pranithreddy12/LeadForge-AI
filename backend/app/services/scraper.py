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


def fetch_static(url: str, *, timeout: float = 15.0) -> str:
    """Cheap static fetch; falls back to Playwright when content looks JS-shelled."""
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

    if not settings.feature_playwright_scrape:
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


# Heuristics for finding the careers/jobs page of a domain.
CAREER_HINT_PATTERNS = [
    "/careers", "/jobs", "/work-with-us", "/join", "/hiring",
    "lever.co", "greenhouse.io", "ashbyhq.com", "workable.com",
]


def looks_like_careers_url(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in CAREER_HINT_PATTERNS)
