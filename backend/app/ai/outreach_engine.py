from __future__ import annotations

from app.ai.openai_client import complete_json
from app.ai.prompts import OUTREACH_SYSTEM
from app.ai.schemas import OUTREACH_JSON_SCHEMA


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
) -> dict:
    """Generate `variants` outreach drafts grounded in real signals."""
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
