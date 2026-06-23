from __future__ import annotations

import httpx

from app.ai import demo_data
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _tavily_configured() -> bool:
    k = settings.tavily_api_key or ""
    return k.startswith("tvly-") and not k.endswith("xxx")


def _serper_configured() -> bool:
    k = settings.serper_api_key or ""
    return bool(k) and not k.endswith("xxx") and k != "xxx"


def tavily_search(query: str, *, max_results: int = 10, search_depth: str = "basic") -> list[dict]:
    """Web search via Tavily. Returns [{title, url, content, score}]."""
    if not _tavily_configured():
        log.info("tavily_demo_mode", query=query[:80])
        return demo_data.demo_search(query, max_results=max_results)
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json().get("results", []) or []
    except Exception as e:
        log.warning("tavily_error", error=str(e))
        return []


def serper_search(query: str, *, max_results: int = 10, kind: str = "search") -> list[dict]:
    """Google-equivalent SERP via Serper. `kind` ∈ search | news | jobs."""
    if not _serper_configured():
        log.info("serper_demo_mode", query=query[:80], kind=kind)
        return demo_data.demo_search(query, max_results=max_results)
    try:
        endpoint = {
            "search": "https://google.serper.dev/search",
            "news": "https://google.serper.dev/news",
            "jobs": "https://google.serper.dev/jobs",
        }[kind]
        r = httpx.post(
            endpoint,
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        if kind == "news":
            return data.get("news", []) or []
        if kind == "jobs":
            return data.get("jobs", []) or []
        return data.get("organic", []) or []
    except Exception as e:
        log.warning("serper_error", error=str(e), kind=kind)
        return []
