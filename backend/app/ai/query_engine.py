"""Intent-first search query generation (Phase 1C).

Topic-keyword queries ("AI automation companies") surface ADJACENTS — vendors,
competitors, VCs, giants — because they match what the seller *does*. This engine
instead generates queries around BUYER INTENT SIGNALS: companies in the target
verticals AND size band that are doing something that implies they'd buy now.

Four intent angles (not topics):
  funding - recently raised Series A-C
  hiring  - hiring RevOps / Operations / "ops" roles
  pain    - language like "reduce manual work" / "scaling operations"
  tech    - recently adopted/rolled out HubSpot or Salesforce

The ICP's industry + employee band + geography are baked into each query so the
SERP itself is pre-filtered toward in-band buyers.
"""
from __future__ import annotations

import datetime

from app.ai.openai_client import complete_json
from app.core.logging import get_logger

log = get_logger(__name__)

INTENT_ANGLES = ["funding", "hiring", "pain", "tech"]

_INTENT_SYSTEM = """\
You generate web-search queries that surface mid-market companies showing BUYING
INTENT for a B2B seller — NOT competitors, NOT vendors, NOT investors.

You are given the SELLER's offering and their ICP (industries, employee size band,
geographies). Generate queries across these INTENT ANGLES — signals that a company
would BUY soon, never topic keywords about the seller's service:

  funding : companies in the target industries that recently raised Series A/B/C
  hiring  : companies hiring RevOps / Revenue Operations / Operations / "ops" roles now
  pain    : companies using language like "reduce manual work", "scaling operations",
            "manual processes", "drowning in spreadsheets", "streamline operations"
  tech    : companies that recently adopted or rolled out HubSpot or Salesforce

HARD RULES:
- Bake the ICP's INDUSTRY + employee SIZE band + GEOGRAPHY into each query so the SERP
  is pre-filtered to in-band buyers (e.g. "Series B fintech 50-500 employees US 2026"
  or "mid-market healthcare provider hiring RevOps 2026").
- NEVER produce a query for the SELLER's own service category (no "AI automation
  agency", no "voice agent providers") — that returns competitors/vendors.
- Each query must be short, literal, and something a person would actually type into
  Google. Vary phrasing; do not just append the angle word.
- Produce 2-3 queries per angle, covering all four angles.
"""

_INTENT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "angle": {"type": "string", "enum": INTENT_ANGLES},
                    "query": {"type": "string"},
                },
                "required": ["angle", "query"],
            },
        }
    },
    "required": ["queries"],
}


def _icp_block(icp: dict) -> str:
    band = ""
    lo, hi = icp.get("employee_min"), icp.get("employee_max")
    if lo or hi:
        band = f"{lo or '?'}-{hi or '?'} employees"
    return (
        f"industries={icp.get('industries')}\n"
        f"employee_size_band={band}\n"
        f"countries={icp.get('countries')}\n"
        f"buyer_personas={icp.get('buyer_personas')}"
    )


def generate_intent_queries(*, business_description: str, icp: dict,
                            limit: int = 10) -> list[dict]:
    """Return [{"angle", "query"}, ...] across the four intent angles, or [] on
    provider error (NOTHING-STATIC: no demo fallback)."""
    year = datetime.date.today().year
    user = (
        f"SELLER does:\n{business_description or '(unknown)'}\n\n"
        f"ICP:\n{_icp_block(icp)}\n\n"
        f"Target RECENT intent — the last 12-18 months. The current year is {year}; use "
        f"{year} (and {year - 1}) in recency-sensitive queries, never older years.\n"
        f"Produce up to {limit} intent queries spread across all four angles."
    )
    out = complete_json(system=_INTENT_SYSTEM, user=user, schema_name="IntentQueries",
                        schema=_INTENT_SCHEMA, temperature=0.3)
    if out.get("_provider_error"):
        return []
    seen: set[str] = set()
    result: list[dict] = []
    for item in (out.get("queries") or []):
        q = (item.get("query") or "").strip()
        angle = item.get("angle")
        if q and angle in INTENT_ANGLES and q.lower() not in seen:
            seen.add(q.lower())
            result.append({"angle": angle, "query": q})
    return result[:limit]


def generate_search_queries(*, business_description: str, icp: dict,
                            limit: int = 10) -> list[str]:
    """Backward-compatible string list for discovery's build_queries. Returns the
    intent queries' text (angle-balanced), or [] if the provider is unavailable."""
    intent = generate_intent_queries(business_description=business_description,
                                     icp=icp, limit=limit)
    return [i["query"] for i in intent]
