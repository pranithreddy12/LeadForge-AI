from __future__ import annotations

from app.ai.openai_client import complete_json
from app.ai.prompts import OPPORTUNITY_SYSTEM
from app.ai.schemas import OPPORTUNITY_JSON_SCHEMA


def analyze_opportunity(*, icp: dict, company: dict, signals: list[dict],
                        score: dict | None = None) -> dict:
    """Generate why-now / pain-points / suggested-offer for an account."""
    user = (
        f"ICP:\n{icp}\n\nCompany:\n{company}\n\nSignals:\n{signals}\n\n"
        f"Current score (if any):\n{score or {}}"
    )
    return complete_json(
        system=OPPORTUNITY_SYSTEM,
        user=user,
        schema_name="Opportunity",
        schema=OPPORTUNITY_JSON_SCHEMA,
        temperature=0.3,
    )
