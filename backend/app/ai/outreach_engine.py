from __future__ import annotations

import re

from app.ai.openai_client import complete_json
from app.ai.prompts import OUTREACH_SYSTEM
from app.ai.schemas import OUTREACH_JSON_SCHEMA
from app.core.logging import get_logger

log = get_logger(__name__)


def humanize(text: str | None) -> str:
    """Strip the tell-tale AI punctuation (em/en dashes) from generated copy and replace
    it with normal human punctuation. LLMs ignore 'no em dashes' instructions ~half the
    time, so this post-processor is the guarantee. Applied to every outbound message."""
    if not text:
        return text or ""
    t = text
    # Spaced em/en dashes act as a comma-pause -> use a comma.
    t = t.replace(" — ", ", ").replace(" – ", ", ").replace(" ― ", ", ")
    # Unspaced em dash / horizontal bar between words -> comma-pause.
    t = t.replace("—", ", ").replace("―", ", ")
    # En dash (often a hyphen substitute, e.g. number ranges) -> plain hyphen.
    t = t.replace("–", "-")
    # Tidy artifacts: " ," , doubled commas, doubled spaces.
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()

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


# ---- WhatsApp problem-aware outreach (Section 1D) --------------------------------

WHATSAPP_MAX_CHARS = 500
_BUZZWORDS = ("revolutionary", "cutting-edge", "cutting edge", "game-changing",
              "game changing", "synergy", "disrupt", "best-in-class")

# Severity ranking used to pick "most severe first" when multiple signals fire.
_LOCAL_SIGNAL_SEVERITY = {
    "missed_calls_complaint": 0.85,
    "slow_response_complaint": 0.60,
    "no_online_booking": 0.55,
    "low_rating": 0.40,
}

WHATSAPP_MESSAGE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
}

WHATSAPP_SYSTEM = """\
You write ONE short WhatsApp message (not an email) to the owner of a LOCAL service
business, from an AI automation agency that helps them never miss a call or lead.

HARD RULES:
- Open by addressing the business by its real name and city.
- Name THEIR specific problem using ONLY the real signal facts provided (missed calls,
  slow responses, no online booking, or their actual star rating). INVENT NOTHING.
- One concrete sentence on what you do: an AI that answers every call instantly, 24/7,
  and books appointments automatically.
- End with exactly this style of ask: "Would it be worth a quick 10-minute call this week?"
- Sign off with the provided sender name.
- Under 500 characters total. Plain, human, no buzzwords (no "revolutionary",
  "cutting-edge", "game-changing"). No markdown, no emojis.
- NEVER use em dashes or en dashes (the "—" / "–" characters) - they read as AI-written.
  Use commas, periods, or plain hyphens instead.
"""


def _extract_city(company: dict) -> str:
    """Best-effort real city/region string from Places address or description."""
    places = (company.get("raw") or {}).get("places") or {}
    addr = places.get("address") or company.get("description") or ""
    if not addr:
        return ""
    parts = [p.strip() for p in str(addr).split(",") if p.strip()]
    if len(parts) >= 2:
        # "123 Main St, Dallas, TX 75201" -> "Dallas, TX"
        tail = parts[-1]
        # drop a trailing ZIP if present on the last segment
        region = tail.split()[0] if tail else ""
        city = f"{parts[-2]}, {region}".strip(", ") if region else parts[-2]
    else:
        city = parts[0]
    # Guard: a marketing `description` (not a real address) would yield a long string,
    # never a city — drop it rather than show a sentence.
    return city if len(city) <= 40 else ""


def _rank_signals(signals: list[dict]) -> list[dict]:
    return sorted(
        signals,
        key=lambda s: (s.get("severity") if s.get("severity") is not None
                       else _LOCAL_SIGNAL_SEVERITY.get(s.get("kind"), 0.0)),
        reverse=True,
    )


def _problem_clause(top: dict, rating) -> str:
    """The deterministic, real-data phrasing for the lead signal."""
    kind = top.get("kind")
    if kind == "missed_calls_complaint":
        return ("I noticed several of your customers mention not being able to reach you "
                "by phone")
    if kind == "slow_response_complaint":
        return "I saw some reviews mentioning slow response times"
    if kind == "no_online_booking":
        return "I noticed you don't have online booking set up yet"
    if kind == "low_rating":
        if rating is not None:
            return (f"I saw your Google rating is sitting at {rating} stars and a few "
                    "reviews point to missed calls and slow replies")
        return "I saw a few of your recent reviews mention slow replies"
    # Unknown local signal — fall back to its real label text, never invented.
    return f"I noticed {top.get('label') or 'an opportunity to help'}"


def _whatsapp_template(company: dict, signals: list[dict], *, sender_name: str) -> str:
    """Deterministic message built from REAL signal/Places data (no LLM, no invented
    facts). Used when the LLM provider errors — never a generic, un-personalized blast."""
    name = company.get("name") or "your business"
    city = _extract_city(company)
    places = (company.get("raw") or {}).get("places") or {}
    rating = places.get("rating")
    ranked = _rank_signals(signals)
    greet = f"Hi {name}" + (f" in {city}" if city else "")
    problem = _problem_clause(ranked[0], rating) if ranked else (
        "I came across your business and think we can help you capture more leads")
    solve = ("We set up an AI that answers every call instantly, 24/7, and books "
             "appointments automatically.")
    cta = "Would it be worth a quick 10-minute call this week?"
    sign = f"\n- {sender_name}" if sender_name else ""
    msg = f"{greet} - {problem}. {solve} {cta}{sign}"
    return msg[:WHATSAPP_MAX_CHARS]


def _has_buzzword(text: str) -> bool:
    low = text.lower()
    return any(b in low for b in _BUZZWORDS)


def generate_whatsapp_message(company: dict, signals: list[dict], settings: dict) -> dict:
    """Generate a single problem-aware WhatsApp message grounded in REAL signal data.

    `settings` carries: tone (professional/friendly/direct) and sender_name.

    Returns {"message": str, "source": "llm"|"template"}. NEVER returns a generic
    un-personalized message and NEVER signals "skip the send": on an LLM provider error
    (or an over-long / buzzword-laden draft) it falls back to a deterministic template
    that substitutes the real signal/Places facts.
    """
    tone = (settings or {}).get("tone") or "professional"
    sender_name = (settings or {}).get("sender_name") or ""
    places = (company.get("raw") or {}).get("places") or {}
    ranked = _rank_signals(signals)
    facts = {
        "business_name": company.get("name"),
        "city": _extract_city(company),
        "google_rating": places.get("rating"),
        "review_count": places.get("review_count"),
        "signals_most_severe_first": [
            {"kind": s.get("kind"), "label": s.get("label"),
             "severity": s.get("severity")} for s in ranked
        ],
        "sender_name": sender_name,
    }
    user = (
        f"TONE: {tone}\n\n"
        f"REAL facts about this business (use ONLY these, invent nothing):\n{facts}\n\n"
        "Write ONE WhatsApp message. Return JSON {\"message\": \"...\"}."
    )
    result = complete_json(system=WHATSAPP_SYSTEM, user=user,
                           schema_name="WhatsAppMessage", schema=WHATSAPP_MESSAGE_SCHEMA,
                           temperature=0.5)
    msg = (result or {}).get("message", "").strip() if isinstance(result, dict) else ""
    msg = humanize(msg)
    provider_error = isinstance(result, dict) and result.get("_provider_error")
    if (not provider_error) and msg and len(msg) <= WHATSAPP_MAX_CHARS and not _has_buzzword(msg):
        return {"message": msg, "source": "llm"}
    # Fall back to the deterministic real-data template (never skip the send).
    if provider_error:
        log.info("whatsapp_message_fallback", reason="provider_error",
                 company=company.get("name"))
    else:
        log.info("whatsapp_message_fallback",
                 reason="empty_or_over_limit_or_buzzword", company=company.get("name"))
    return {"message": humanize(_whatsapp_template(company, signals, sender_name=sender_name)),
            "source": "template"}


# ---- Suggested reply (Section 4A — Reply Intelligence) ---------------------------

SUGGESTED_REPLY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"suggested_response": {"type": "string"}},
    "required": ["suggested_response"],
}

SUGGESTED_REPLY_SYSTEM = """\
You draft the NEXT reply a sales rep should send to a prospect who just responded to
our cold outreach. We help businesses never miss a call or lead (AI voice agents that
answer every call 24/7, instant speed-to-lead, automated booking).

HARD RULES:
- Directly address what THEY actually said in their reply.
- Tie back to the specific problem signal that drove our outreach, if provided.
- Propose ONE concrete next step (a quick call, a short demo, or a direct answer to
  their question). Make it easy to say yes.
- Warm, human, concise. No buzzwords. Under 150 words. Plain text, no markdown.
- NEVER use em dashes or en dashes ("—" / "–") - they read as AI-written. Use commas,
  periods, or plain hyphens instead.
"""


def generate_suggested_reply(*, company: dict, their_message: str,
                             signal: str | None = None,
                             channel: str = "email") -> dict:
    """Draft a suggested next reply grounded in the prospect's actual message + the
    driving signal. Returns {"suggested_response": str} or {"_provider_error": True}
    (callers then OMIT the suggestion — never fabricate one)."""
    facts = {
        "business_name": company.get("name"),
        "channel": channel,
        "driving_signal": signal,
        "their_reply": (their_message or "")[:1200],
    }
    user = (
        f"Context (use only what's real):\n{facts}\n\n"
        "Write the suggested reply. Return JSON {\"suggested_response\": \"...\"}."
    )
    result = complete_json(system=SUGGESTED_REPLY_SYSTEM, user=user,
                           schema_name="SuggestedReply", schema=SUGGESTED_REPLY_SCHEMA,
                           temperature=0.5)
    if not isinstance(result, dict) or result.get("_provider_error"):
        return {"_provider_error": True}
    msg = (result.get("suggested_response") or "").strip()
    if not msg:
        return {"_provider_error": True}
    # Enforce the ~150-word ceiling defensively.
    words = msg.split()
    if len(words) > 150:
        msg = " ".join(words[:150])
    return {"suggested_response": humanize(msg)}


def _humanize_variants(result: dict) -> dict:
    """Strip AI-tell punctuation from every draft variant's subject + body."""
    if not isinstance(result, dict) or result.get("_provider_error"):
        return result
    for v in (result.get("variants") or []):
        if isinstance(v, dict):
            if v.get("subject"):
                v["subject"] = humanize(v["subject"])
            if v.get("body"):
                v["body"] = humanize(v["body"])
    return result


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
        return _humanize_variants(complete_json(
            system=LOCAL_OUTREACH_SYSTEM, user=user,
            schema_name="Outreach", schema=OUTREACH_JSON_SCHEMA, temperature=0.5))

    user = (
        f"Channel: {channel}\nTone: {tone}\nFollow-up #: {follow_up}\n"
        f"Variants requested: {variants}\n\n"
        f"Sender's offering (ICP):\n{icp or {}}\n\n"
        f"Account:\n{company}\n\nContact:\n{contact or 'unknown'}\n\n"
        f"Signals:\n{signals}\n\n"
        "Return `variants` array of {subject, body}. For LinkedIn, leave subject empty."
    )
    return _humanize_variants(complete_json(
        system=OUTREACH_SYSTEM,
        user=user,
        schema_name="Outreach",
        schema=OUTREACH_JSON_SCHEMA,
        temperature=0.6,
    ))
