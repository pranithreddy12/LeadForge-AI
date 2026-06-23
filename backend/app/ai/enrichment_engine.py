"""Company Enrichment Engine (Phase 2).

Turns a bare (name, domain) into an actionable firmographic profile by:
  1. Scraping the company's own website (about / homepage text).
  2. Pulling targeted search snippets (employees, revenue, funding, HQ).
  3. Asking the LLM to extract ONE strict JSON record from that evidence.

Crucially: the model is instructed to return null for anything it cannot
ground in the provided text — we never want fabricated headcounts or funding.
"""
from __future__ import annotations

from app.ai.openai_client import complete_json
from app.core.logging import get_logger

log = get_logger(__name__)

ENRICH_SYSTEM = """\
You are a company data analyst. From the provided website text and web search
snippets about ONE company, extract a structured firmographic profile.

HARD RULES:
- Only state facts grounded in the provided text. If a field is not supported,
  return null (or [] for lists). NEVER guess headcount, revenue, or funding.
- employee_count: a single integer best-estimate if stated or strongly implied
  (e.g. "200+ employees" -> 200), else null.
- revenue_usd: integer USD if stated/derivable, else null.
- founded_year: 4-digit year if stated, else null.
- country / city: headquarters location if stated, else null.
- funding_total_usd: cumulative funding in USD if stated, else null.
- last_funding_stage: e.g. "Seed", "Series A", "Series B", "Series C", "IPO",
  "Bootstrapped", else null.
- industry: a concise industry label.
- description: 1-2 sentence plain description of what the company does.
"""

ENRICH_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "description": {"type": ["string", "null"]},
        "industry": {"type": ["string", "null"]},
        "sub_industries": {"type": "array", "items": {"type": "string"}},
        "employee_count": {"type": ["integer", "null"]},
        "employee_range": {"type": ["string", "null"]},
        "revenue_usd": {"type": ["integer", "null"]},
        "revenue_range": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "city": {"type": ["string", "null"]},
        "region": {"type": ["string", "null"]},
        "founded_year": {"type": ["integer", "null"]},
        "linkedin_url": {"type": ["string", "null"]},
        "funding_total_usd": {"type": ["integer", "null"]},
        "last_funding_stage": {"type": ["string", "null"]},
        "confidence": {"type": "integer"},
    },
    "required": [
        "description", "industry", "sub_industries", "employee_count",
        "employee_range", "revenue_usd", "revenue_range", "country", "city",
        "region", "founded_year", "linkedin_url", "funding_total_usd",
        "last_funding_stage", "confidence",
    ],
}


def extract_profile(*, company_name: str, domain: str | None,
                    website_text: str, search_snippets: str) -> dict:
    """Extract a firmographic profile. Returns {} / {_provider_error} on failure
    so the caller can decide whether to persist (never fabricate on error)."""
    evidence = (
        f"Company: {company_name}\nDomain: {domain or 'unknown'}\n\n"
        f"=== Website text ===\n{website_text[:12000]}\n\n"
        f"=== Web search snippets ===\n{search_snippets[:5000]}"
    )
    if len(website_text) + len(search_snippets) < 80:
        return {}  # nothing to extract from
    return complete_json(
        system=ENRICH_SYSTEM,
        user=evidence,
        schema_name="Enrichment",
        schema=ENRICH_SCHEMA,
        temperature=0.0,
    )


def employee_range_for(count: int | None) -> str | None:
    if not count:
        return None
    bands = [(10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
             (1000, "501-1000"), (5000, "1001-5000"), (10**9, "5000+")]
    for ceiling, label in bands:
        if count <= ceiling:
            return label
    return None


def revenue_range_for(rev: int | None) -> str | None:
    if not rev:
        return None
    m = rev / 1_000_000
    if m < 1:
        return "<$1M"
    if m < 10:
        return "$1M-$10M"
    if m < 50:
        return "$10M-$50M"
    if m < 100:
        return "$50M-$100M"
    if m < 500:
        return "$100M-$500M"
    return "$500M+"
