from __future__ import annotations

from app.ai.openai_client import complete_json
from app.ai.prompts import OUTREACH_SYSTEM
from app.ai.schemas import OUTREACH_JSON_SCHEMA

# Local-business outreach (Step 7). Every claim MUST come from the provided Places data
# — nothing invented. Tone matches the Settings value.
LOCAL_OUTREACH_SYSTEM = """\
You write short cold outreach to LOCAL service businesses (med spas, dental clinics,
law firms, home services, salons) for an AI automation agency that helps them never
miss a call or lead and respond to inquiries instantly (AI voice agents, speed-to-lead,
24/7 online booking).

HARD RULES:
- Use ONLY the real facts provided about THIS business: its name, city/location, Google
  rating and review count, and any review-based signal (e.g. reviews mentioning missed
  calls, slow response, no online booking). INVENT NOTHING — no fake numbers, no fake
  details. If a fact is not provided, do not state it.
- Lead with the most specific real signal and tie it to ONE concrete outcome ("never
  miss a call again", "respond to every lead in under 30 seconds", "let patients book
  24/7"). Use their rating/review count as a light social-proof anchor if provided.
- Honor the requested TONE exactly: professional = polished and formal; friendly =
  warm and conversational; direct = one short paragraph, one clear ask.
- 3-5 sentences. End with a soft, low-friction ask (a quick reply or a 10-minute call).
"""


def generate_outreach(
    *,
    company: dict,
    contact: dict | None,
    icp: dict | None,
    signals: list[dict],
    channel: str = "email",
    tone: str = "concise",
    follow_up: int = 0,
    variants: int = 2,
    local: bool = False,
) -> dict:
    """Generate `variants` outreach drafts grounded in real signals. When `local`, use
    the local-business path (cites real Google Places facts, tone-aware)."""
    if local:
        places = (company.get("raw") or {}).get("places") or {}
        facts = {
            "name": company.get("name"),
            "location": company.get("description") or places.get("address"),
            "google_rating": places.get("rating"),
            "review_count": places.get("review_count"),
            "review_signals": [{"kind": s.get("kind"), "label": s.get("label")} for s in signals],
        }
        user = (
            f"TONE: {tone}\nVariants requested: {variants}\n\n"
            f"REAL facts about this business (use only these — invent nothing):\n{facts}\n\n"
            "Return `variants` array of {subject, body}."
        )
        return complete_json(system=LOCAL_OUTREACH_SYSTEM, user=user,
                             schema_name="Outreach", schema=OUTREACH_JSON_SCHEMA,
                             temperature=0.5)

    user = (
        f"Channel: {channel}\nTone: {tone}\nFollow-up #: {follow_up}\n"
        f"Variants requested: {variants}\n\n"
        f"Sender's offering (ICP):\n{icp or {}}\n\n"
        f"Account:\n{company}\n\nContact:\n{contact or 'unknown'}\n\n"
        f"Signals:\n{signals}\n\n"
        "Return `variants` array of {subject, body}. For LinkedIn, leave subject empty."
    )
    return complete_json(
        system=OUTREACH_SYSTEM,
        user=user,
        schema_name="Outreach",
        schema=OUTREACH_JSON_SCHEMA,
        temperature=0.6,
    )
