from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; LeadForgeBot/1.0; +https://leadforge.ai/bot)"


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)[:30_000]


def fetch_static(url: str, *, timeout: float = 15.0) -> str:
    """Cheap static fetch; falls back to Playwright when content looks JS-shelled."""
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                          timeout=timeout) as client:
            r = client.get(url)
            r.raise_for_status()
            text = _strip_html(r.text)
            if len(text) >= 400:
                return text
    except Exception as e:
        log.info("static_fetch_failed", url=url, error=str(e))

    if not settings.feature_playwright_scrape:
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
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                          timeout=timeout) as client:
            r = client.get(url)
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
