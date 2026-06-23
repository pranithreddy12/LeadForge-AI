from __future__ import annotations

from app.ai.openai_client import complete_json
from app.ai.prompts import SIGNAL_SYSTEM
from app.ai.schemas import SIGNALS_JSON_SCHEMA


def extract_signals_from_text(
    *, company_name: str, source: str, text: str, url: str | None = None
) -> list[dict]:
    """Extract structured signals from a chunk of source text."""
    if not text or len(text) < 50:
        return []

    user = (
        f"Company: {company_name}\nSource: {source}\nURL: {url or 'n/a'}\n\n"
        f"Text:\n{text[:14_000]}"
    )
    result = complete_json(
        system=SIGNAL_SYSTEM,
        user=user,
        schema_name="Signals",
        schema=SIGNALS_JSON_SCHEMA,
        temperature=0.1,
    )
    return result.get("signals", [])


def signal_kinds_for_hiring(jobs: list[dict], icp_keywords: list[str]) -> list[dict]:
    """Quick deterministic path for hiring signals — no LLM needed when jobs are structured.

    `jobs` should look like [{"title": "...", "url": "...", "posted_at": "..."}].
    """
    out = []
    kw_lower = [k.lower() for k in icp_keywords]
    for j in jobs:
        title = (j.get("title") or "").strip()
        if not title:
            continue
        hits = [k for k in kw_lower if k in title.lower()]
        out.append({
            "kind": "hiring",
            "label": f"Hiring: {title}",
            "description": "Open role detected via job board.",
            "severity": min(1.0, 0.5 + 0.15 * len(hits)),
            "confidence": 0.85 if hits else 0.55,
            "observed_at": j.get("posted_at"),
            "url": j.get("url"),
        })
    return out
