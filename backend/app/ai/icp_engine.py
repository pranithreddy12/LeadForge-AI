from __future__ import annotations

from app.ai.openai_client import complete_json
from app.ai.prompts import ICP_SYSTEM
from app.ai.schemas import ICP_JSON_SCHEMA


def generate_icp(*, business_description: str, target_offering: str | None = None,
                 hints: dict | None = None) -> dict:
    """Turn a business description into a structured ICP dict.

    Returned dict matches `ICP_JSON_SCHEMA` and is ready to persist after
    light validation by the calling service.
    """
    user_parts = [f"Business description:\n{business_description.strip()}"]
    if target_offering:
        user_parts.append(f"\nService offering:\n{target_offering.strip()}")
    if hints:
        user_parts.append(f"\nUser hints (JSON): {hints}")

    return complete_json(
        system=ICP_SYSTEM,
        user="\n".join(user_parts),
        schema_name="ICP",
        schema=ICP_JSON_SCHEMA,
        temperature=0.3,
    )


def refine_icp(current: dict, instruction: str) -> dict:
    """Apply a natural-language refinement to an existing ICP."""
    user = (
        f"Current ICP (JSON):\n{current}\n\n"
        f"User instruction:\n{instruction}\n\n"
        "Return a complete, updated ICP."
    )
    return complete_json(
        system=ICP_SYSTEM,
        user=user,
        schema_name="ICP",
        schema=ICP_JSON_SCHEMA,
        temperature=0.2,
    )
