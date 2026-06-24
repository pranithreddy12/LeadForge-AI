"""LLM client abstraction.

Despite the filename, this module is provider-agnostic. It speaks the OpenAI
client library but can target either:

    - OpenAI                  (OPENAI_API_KEY=sk-…)
    - Google Gemini           (GEMINI_API_KEY=…)  via the OpenAI-compat endpoint
    - Demo fixtures           when neither key is set

Selection is automatic, with this priority: OpenAI → Gemini → demo. Set the
environment variable for whichever provider you want and restart.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any, Literal

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

from app.ai import demo_data
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

Provider = Literal["openai", "mistral", "gemini", "demo"]

# Transient provider errors worth retrying before giving up. Gemini's free tier
# returns 503 "high demand" and 429 rate-limit fairly often; both clear quickly.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_TRANSIENT_RETRIES = 3

# --- Circuit breaker -------------------------------------------------------
# When the provider is hard-down (e.g. daily free-tier quota exhausted),
# retrying every single call wastes ~9s each and grinds batch jobs (scoring a
# list of companies) to a halt. After N consecutive failures we "open" the
# breaker: subsequent calls fail fast (no network, no sleep) until a cooldown
# elapses, then we try one probe. `monotonic` is import-time safe (unlike the
# wall clock helpers that are stubbed in workflow scripts).
#
# SCOPE (intentional): this state is PER-PROCESS and best-effort. With Celery's
# prefork pool (concurrency=2) each worker child trips its own breaker, and a
# child recycle (worker_max_tasks_per_child) resets it. That's acceptable — it
# still bounds wasted retries within each process's task stream, which is where
# the cost lives. A Redis-backed shared breaker was considered and rejected: it
# would add a network round-trip to EVERY llm call to save a handful of slow
# calls per child per cooldown window. Not worth the latency at this scale.
_CB_FAIL_THRESHOLD = 3
_CB_COOLDOWN_SECONDS = 120
_cb_consecutive_failures = 0
_cb_open_until = 0.0


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    return status in _TRANSIENT_STATUS


def _circuit_open() -> bool:
    return time.monotonic() < _cb_open_until


def _record_success() -> None:
    global _cb_consecutive_failures, _cb_open_until
    _cb_consecutive_failures = 0
    _cb_open_until = 0.0


def _record_failure() -> None:
    global _cb_consecutive_failures, _cb_open_until
    _cb_consecutive_failures += 1
    if _cb_consecutive_failures >= _CB_FAIL_THRESHOLD:
        _cb_open_until = time.monotonic() + _CB_COOLDOWN_SECONDS
        log.warning("llm_circuit_open", cooldown=_CB_COOLDOWN_SECONDS,
                    failures=_cb_consecutive_failures)


class _ProviderDown(APIError):
    """Raised when the circuit breaker is open — short-circuits without a call."""
    def __init__(self):
        Exception.__init__(self, "circuit_open")


def _with_retry(call, *, what: str):
    """Run an LLM call with retry + circuit breaker.

    - Circuit open  → fail fast (no network, no sleep).
    - Transient err → retry with linear backoff, up to _MAX_TRANSIENT_RETRIES.
    - Success       → reset the breaker.
    """
    if _circuit_open():
        raise _ProviderDown()

    last: Exception | None = None
    for attempt in range(_MAX_TRANSIENT_RETRIES):
        try:
            result = call()
            _record_success()
            return result
        except APIError as exc:
            last = exc
            if not _is_transient(exc):
                raise
            _record_failure()
            if _circuit_open():       # breaker tripped mid-loop — stop retrying
                raise
            wait = 1.5 * (attempt + 1)
            log.warning("llm_transient_retry", what=what, attempt=attempt + 1,
                        wait=wait, error=str(exc)[:160])
            time.sleep(wait)
    assert last is not None
    raise last


def _is_openai_configured() -> bool:
    k = settings.openai_api_key or ""
    return k.startswith("sk-") and len(k) > 30 and not k.endswith("xxx")


def _is_mistral_configured() -> bool:
    k = settings.mistral_api_key or ""
    return len(k) > 20 and not k.endswith("xxx") and not k.endswith("placeholder")


def _is_gemini_configured() -> bool:
    k = settings.gemini_api_key or ""
    return len(k) > 20 and not k.endswith("xxx") and not k.endswith("placeholder")


def _provider() -> Provider:
    # Priority: a real OpenAI key wins, then Mistral (explicitly chosen for
    # testing), then Gemini, then demo. Mistral sits above Gemini so adding a
    # Mistral key takes over even if a (possibly quota-exhausted) Gemini key
    # is still present.
    if _is_openai_configured():
        return "openai"
    if _is_mistral_configured():
        return "mistral"
    if _is_gemini_configured():
        return "gemini"
    return "demo"


# providers reached through the OpenAI-compatible chat endpoint that do NOT
# enforce strict json_schema — we send json_object + schema-in-prompt instead.
_JSON_OBJECT_PROVIDERS = {"gemini", "mistral"}


@lru_cache(maxsize=1)
def client() -> OpenAI:
    p = _provider()
    if p == "mistral":
        return OpenAI(api_key=settings.mistral_api_key,
                      base_url=settings.mistral_base_url, timeout=60.0, max_retries=2)
    if p == "gemini":
        return OpenAI(api_key=settings.gemini_api_key,
                      base_url=settings.gemini_base_url, timeout=60.0, max_retries=2)
    return OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=2)


def _model_reasoning() -> str:
    p = _provider()
    if p == "mistral":
        return settings.mistral_model_reasoning
    if p == "gemini":
        return settings.gemini_model_reasoning
    return settings.openai_model_reasoning


def _model_fast() -> str:
    p = _provider()
    if p == "mistral":
        return settings.mistral_model_fast
    if p == "gemini":
        return settings.gemini_model_fast
    return settings.openai_model_fast


def _model_embedding() -> str:
    return (
        settings.gemini_model_embedding if _provider() == "gemini"
        else settings.openai_model_embedding
    )


# ---- Demo router ----------------------------------------------------------

def _demo_for_schema(schema_name: str, user: str) -> dict[str, Any]:
    sn = (schema_name or "").lower()
    if sn == "icp":
        return demo_data.demo_icp(user)
    if sn == "signals":
        company = "Unknown"
        for line in user.splitlines():
            if line.startswith("Company:"):
                company = line.split(":", 1)[1].strip()
                break
        return {"signals": demo_data.demo_signals(company, "demo")}
    if sn == "score":
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
    # No demo fixture for this schema (e.g. AccountResearch). Signal "unavailable"
    # so callers persist NOTHING rather than a hollow/empty row.
    return {"_provider_error": True}


# ---- Public API ------------------------------------------------------------


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

    OpenAI: uses `response_format=json_schema` (strict mode).
    Gemini: uses `response_format=json_object` with the schema appended to the
    system prompt — Gemini's OpenAI-compat layer doesn't yet enforce strict
    json_schema, but reliably produces valid JSON when asked.
    """
    p = _provider()
    if p == "demo":
        log.info("llm_demo_mode", schema=schema_name)
        return _demo_for_schema(schema_name, user)

    if p in _JSON_OBJECT_PROVIDERS:
        # Gemini/Mistral: append the schema as an explicit instruction (their
        # OpenAI-compat layer doesn't enforce strict json_schema) and ask for a
        # plain JSON object.
        sys_with_schema = (
            f"{system}\n\n"
            f"Return ONLY a JSON object matching this JSON Schema (no markdown, no commentary):\n"
            f"{json.dumps(schema)}"
        )
        kwargs = dict(
            model=model or _model_reasoning(),
            temperature=temperature,
            messages=[
                {"role": "system", "content": sys_with_schema},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
    else:
        kwargs = dict(
            model=model or _model_reasoning(),
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        )

    try:
        response = _with_retry(
            lambda: client().chat.completions.create(**kwargs),
            what=f"complete_json:{schema_name}",
        )
    except APIError as exc:
        # A REAL provider was configured but failed (e.g. rate-limited) after all
        # retries. Do NOT fabricate demo data — that would silently pollute the
        # DB with fake rows. Return empty so callers add nothing. Demo fixtures
        # are ONLY for the no-key-configured path (handled above as p == "demo").
        log.warning("llm_provider_unavailable", provider=p, schema=schema_name,
                    error=str(exc)[:160])
        return {"_provider_error": True}

    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        log.warning("llm_json_parse_failed", provider=p, content=content[:500])
        return {}


def complete_text(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> str:
    if _provider() == "demo":
        return "[demo mode] " + (user[:200] or "no input")

    response = client().chat.completions.create(
        model=model or _model_fast(),
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
    if _provider() == "demo":
        msg = (
            "[demo mode] No LLM key configured. Set OPENAI_API_KEY, "
            "MISTRAL_API_KEY, or GEMINI_API_KEY to enable real chat."
        )
        for word in msg.split():
            yield word + " "
        return

    stream = client().chat.completions.create(
        model=model or _model_fast(),
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
    p = _provider()
    # Mistral's embedding model is 1024-dim, which won't fit our 1536-dim vector
    # column. Use the deterministic local embedding so semantic search keeps
    # working at the right dimension without a schema migration. (Chat/scoring
    # quality is unaffected — only semantic similarity is lower-fidelity.)
    if p in ("demo", "mistral"):
        return [demo_data.demo_embedding(t, settings.openai_embedding_dim) for t in texts]

    kwargs: dict[str, Any] = {"model": _model_embedding(), "input": texts}
    # Both OpenAI and Gemini's `gemini-embedding-001` accept `dimensions` via the
    # OpenAI-compat endpoint. The smaller embedding-004 model maxes at 768 and
    # would error if we sent dimensions=1536, so only opt in when safe.
    target_dim = settings.openai_embedding_dim
    if p == "openai" or "embedding-001" in _model_embedding():
        kwargs["dimensions"] = target_dim

    # Route through the breaker too: the embeddings backfill is exactly the
    # batch job the breaker exists to protect from per-call quota retries.
    try:
        response = _with_retry(lambda: client().embeddings.create(**kwargs), what="embed")
    except APIError:
        # Real provider unavailable → return [] (NOT fabricated vectors). The
        # caller (upsert_company_embedding) leaves embedding_pending=True so the
        # row is retried next cycle instead of being polluted with a mismatched-
        # space vector. Demo embeddings are only for the no-key path above.
        log.warning("embed_provider_unavailable", n=len(texts))
        return []
    return [d.embedding for d in response.data]


def current_provider() -> Provider:
    """Public accessor for the active provider — used by /health and `keys` CLI."""
    return _provider()
