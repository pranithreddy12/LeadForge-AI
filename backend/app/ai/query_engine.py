"""Buyer-intent search query generation.

The hardest part of B2B discovery is finding BUYERS, not competitors. Templating
"{industry} companies {keyword}" off an ICP tends to surface other vendors who
offer the same thing. This engine asks the LLM for queries explicitly designed
to find TARGET BUYER companies showing buying intent, given what the seller does.

Used at discovery time when an ICP has no stored `search_queries` (older ICPs,
or ICPs imported without generation).
"""
from __future__ import annotations

from app.ai.openai_client import complete_json
from app.core.logging import get_logger

log = get_logger(__name__)

_QUERY_SYSTEM = """\
You generate web-search queries to find TARGET BUYER companies for a B2B seller.

You are given: what the SELLER does, and their ICP (industries, buyer personas,
buying signals, geographies). Produce 6-10 search queries that would surface
companies likely to BUY — i.e. companies in the target industries that exhibit
buying signals (recent funding, hiring, growth, launches).

HARD RULE: never produce a query that returns COMPETITORS (other companies that
offer the same service as the seller). For "fractional CFO services", do NOT
output "fractional CFO firms"; output "Series A startups hiring finance 2026".
Combine industry + buying-signal + geography. Keep each query short and literal.
"""

_QUERY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["queries"],
}


def generate_search_queries(*, business_description: str, icp: dict,
                            limit: int = 8) -> list[str]:
    """Return buyer-intent queries, or [] if the provider is unavailable."""
    user = (
        f"SELLER does:\n{business_description or '(unknown)'}\n\n"
        f"ICP:\nindustries={icp.get('industries')}\n"
        f"buyer_personas={icp.get('buyer_personas')}\n"
        f"buying_signals={icp.get('buying_signals')}\n"
        f"countries={icp.get('countries')}\n"
        f"keywords={icp.get('keywords')}\n\n"
        f"Produce up to {limit} buyer-finding queries."
    )
    out = complete_json(
        system=_QUERY_SYSTEM, user=user, schema_name="Queries",
        schema=_QUERY_SCHEMA, temperature=0.3,
    )
    if out.get("_provider_error"):
        return []
    queries = [q.strip() for q in (out.get("queries") or []) if q and q.strip()]
    return queries[:limit]
