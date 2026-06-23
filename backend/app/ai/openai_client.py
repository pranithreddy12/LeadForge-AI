from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from openai import OpenAI

from app.ai import demo_data
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _openai_configured() -> bool:
    k = settings.openai_api_key or ""
    return k.startswith("sk-") and not k.endswith("xxx")


@lru_cache(maxsize=1)
def client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=2)


# ---- Demo router ----------------------------------------------------------
# Pick a hand-crafted fixture per schema. The router is keyed by `schema_name`
# (the same string we pass to OpenAI's response_format) so the rest of the code
# remains untouched.

def _demo_for_schema(schema_name: str, user: str) -> dict[str, Any]:
    sn = (schema_name or "").lower()
    if sn == "icp":
        return demo_data.demo_icp(user)
    if sn == "signals":
        # `user` looks like "Company: X\nSource: Y\nURL: Z\n\nText:\n..."
        company = "Unknown"
        for line in user.splitlines():
            if line.startswith("Company:"):
                company = line.split(":", 1)[1].strip()
                break
        return {"signals": demo_data.demo_signals(company, "demo")}
    if sn == "score":
        # The scoring engine includes the heuristic subscores in the prompt; we
        # parse them out so the demo "LLM adjust" can react to real inputs.
        base = {
            "fit_score": 65, "funding_score": 50, "hiring_score": 55,
            "growth_score": 50, "tech_match_score": 60, "email_score": 40,
            "activity_score": 55,
        }
        try:
            blob = user.split("Heuristic subscores:", 1)[1]
            for k in list(base):
                if f"'{k}':" in blob:
                    v = blob.split(f"'{k}':", 1)[1].split(",", 1)[0]
                    base[k] = int("".join(c for c in v if c.isdigit()))
        except Exception:
            pass
        return demo_data.demo_score_adjust(base)
    if sn == "opportunity":
        return demo_data.demo_opportunity({"name": "this account"})
    if sn == "outreach":
        return demo_data.demo_outreach({"name": "this account"}, None, "email", "concise")
    return {"demo": True}


def complete_json(
    *,
    system: str,
    user: str,
    schema_name: str,
    schema: dict[str, Any],
    model: str | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Force the model to return JSON matching `schema`.

    Uses OpenAI's `response_format=json_schema` so we don't need to parse free text.
    Falls back to a hand-crafted demo fixture when OPENAI_API_KEY isn't set.
    """
    if not _openai_configured():
        log.warning("openai_demo_mode", schema=schema_name)
        return _demo_for_schema(schema_name, user)

    response = client().chat.completions.create(
        model=model or settings.openai_model_reasoning,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        },
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        log.warning("openai_json_parse_failed", content=content[:500])
        return {}


def complete_text(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> str:
    if not _openai_configured():
        return "[demo mode] " + (user[:200] or "no input")

    response = client().chat.completions.create(
        model=model or settings.openai_model_fast,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


def stream_chat(messages: list[dict], model: str | None = None):
    """Generator yielding token strings — for SSE chat endpoints."""
    if not _openai_configured():
        msg = "[demo mode] OpenAI key not configured. Set OPENAI_API_KEY to enable real chat."
        for word in msg.split():
            yield word + " "
        return

    stream = client().chat.completions.create(
        model=model or settings.openai_model_fast,
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if not _openai_configured():
        return [demo_data.demo_embedding(t, settings.openai_embedding_dim) for t in texts]

    response = client().embeddings.create(
        model=settings.openai_model_embedding,
        input=texts,
        dimensions=settings.openai_embedding_dim,
    )
    return [d.embedding for d in response.data]
