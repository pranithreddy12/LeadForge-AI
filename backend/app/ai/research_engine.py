"""Account Research Engine (Phase 6).

Synthesizes everything we know about an account — firmographics, signals,
tech stack, contacts — plus fresh web research into a deep account brief a
seller can act on: summary, pain points, current initiatives, growth signals,
and a recommended pitch.

Like every other engine here it NEVER fabricates: on provider error it returns
{"_provider_error": True} so the caller persists nothing.
"""
from __future__ import annotations

from app.ai.openai_client import complete_json
from app.core.logging import get_logger

log = get_logger(__name__)

RESEARCH_SYSTEM = """\
You are a B2B account researcher writing a briefing for a salesperson about to
reach out. You receive structured facts about the account (firmographics, tech
stack, observed buying signals, known contacts) plus raw web-research snippets
(news, careers, about page). Synthesize a concise, ACTIONABLE brief.

HARD RULES:
- Ground every claim in the provided evidence. If evidence is thin, say so and
  keep the brief short — do NOT invent funding, headcount, or initiatives.
- pain_points: infer likely pains from the seller's offering + the account's
  situation; phrase them as the account's problems, not the seller's pitch.
- recommended_pitch: 2-3 sentences a rep could paste, citing a real signal.
- confidence: integer 0-100 — how strong/grounded this brief is given the evidence.
- Be specific and concrete. No filler, no "in today's fast-paced world".
"""

RESEARCH_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "pain_points": {"type": "array", "items": {"type": "string"}},
        "current_initiatives": {"type": "array", "items": {"type": "string"}},
        "growth_signals": {"type": "array", "items": {"type": "string"}},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "recommended_pitch": {"type": "string"},
        "suggested_contact_title": {"type": "string"},
        "confidence": {"type": "integer"},
    },
    "required": [
        "summary", "pain_points", "current_initiatives", "growth_signals",
        "key_facts", "recommended_pitch", "suggested_contact_title", "confidence",
    ],
}


def synthesize_research(*, company: dict, icp: dict | None, seller_offering: str,
                        signals: list[dict], contacts: list[dict],
                        web_snippets: str) -> dict:
    """Produce a structured account brief. Returns {} / {_provider_error} on failure."""
    user = (
        f"SELLER offering:\n{seller_offering or '(unknown)'}\n\n"
        f"ACCOUNT (firmographics):\n{company}\n\n"
        f"ICP (who the seller targets):\n{icp or {}}\n\n"
        f"OBSERVED SIGNALS:\n{signals or '(none)'}\n\n"
        f"KNOWN CONTACTS:\n{contacts or '(none)'}\n\n"
        f"WEB RESEARCH SNIPPETS:\n{web_snippets[:8000] or '(none)'}\n\n"
        "Write the briefing."
    )
    return complete_json(
        system=RESEARCH_SYSTEM,
        user=user,
        schema_name="AccountResearch",
        schema=RESEARCH_SCHEMA,
        temperature=0.3,
    )
