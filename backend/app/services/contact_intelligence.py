"""Contact Intelligence (Phase 7).

Deterministic per-contact scoring — no LLM needed, so it always works:

  influence_score (0-100): how much organizational sway this person has, from
      seniority + department leadership, with a boost when their title matches
      the seller's target buyer personas (from the ICP).

  buying_power: their role in a purchase decision —
      decision_maker | influencer | gatekeeper | evaluator | end_user

These let a rep instantly see WHO to contact first on an account.
"""
from __future__ import annotations

import re

# Base organizational influence by seniority bucket (matches contacts._seniority_for).
_SENIORITY_BASE = {
    "cxo": 92,
    "vp": 78,
    "director": 64,
    "manager": 48,
    "ic": 28,
}

# Department relevance is contextual; these are mild intrinsic modifiers
# (leadership-heavy functions skew slightly higher in buying influence).
_DEPARTMENT_MOD = {
    "leadership": 6,
    "engineering": 3,
    "sales": 2,
    "operations": 2,
    "marketing": 1,
    "finance": 4,
}

# Founder/owner/C-level tokens — always top influence. All word-boundary anchored.
# 'president' uses a negative lookbehind so it does NOT fire on "Vice President".
# 'owner' requires a business-ownership qualifier so "Product/Process Owner" is excluded.
# CxO acronyms + "chief … officer" are included so a C-level title with a mismatched
# seniority arg still elevates correctly.
_FOUNDER_RE = re.compile(
    r"\b(founder|co-?founder|(?<!vice )president|managing director"
    r"|ceo|cto|cfo|coo|cmo|ciso|cpo|cro"
    r"|chief\s+\w+\s+officer)\b"
    r"|\b(business|company|firm)\s+owner\b",
    re.I,
)
# Procurement/gatekeeper roles — checked FIRST so they never inherit founder scoring.
_GATEKEEPER_RE = re.compile(
    r"\b(procurement|purchasing|executive\s+assistant|chief\s+of\s+staff)\b", re.I
)


def _persona_match_boost(title: str, buyer_personas: list[str] | None) -> int:
    """Boost when the contact's title overlaps the ICP's target buyer personas.

    Word-boundary matching (NOT substring), so persona 'CEO' does not match
    'Executive Assistant to the CEO' partial tokens and 'VP' does not bare-match
    unrelated text. A persona matches when its whole phrase OR all its
    significant words appear as whole words in the title.
    """
    if not buyer_personas or not title:
        return 0
    t = title.lower()

    def whole(word: str) -> bool:
        return re.search(rf"\b{re.escape(word)}\b", t) is not None

    for persona in buyer_personas:
        p = (persona or "").lower().strip()
        if not p:
            continue
        if whole(p):
            return 12
        words = [w for w in re.split(r"[^a-z0-9]+", p) if len(w) > 2]
        if words and all(whole(w) for w in words):
            return 12
    return 0


def compute_influence(*, title: str | None, seniority: str | None,
                      department: str | None, buyer_personas: list[str] | None
                      ) -> tuple[int, str]:
    """Return (influence_score 0-100, buying_power category)."""
    title = (title or "").strip()
    sev = (seniority or "ic").lower()

    base = _SENIORITY_BASE.get(sev, 28)
    base += _DEPARTMENT_MOD.get((department or "").lower(), 0)

    is_gatekeeper = bool(_GATEKEEPER_RE.search(title))
    # Founder/exec elevation — but NEVER for a gatekeeper (an EA "to the CEO" is
    # not a CEO). Gatekeepers keep their seniority-based score.
    if not is_gatekeeper and _FOUNDER_RE.search(title):
        base = max(base, 95)
    base += _persona_match_boost(title, buyer_personas)
    score = max(0, min(100, base))

    buying_power = _buying_power(sev, title, score, is_gatekeeper)
    return score, buying_power


def _buying_power(seniority: str, title: str, score: int, is_gatekeeper: bool) -> str:
    if is_gatekeeper:
        return "gatekeeper"
    if _FOUNDER_RE.search(title) or seniority == "cxo":
        return "decision_maker"
    if seniority == "vp":
        # Use an explicit authority signal (persona/founder already handled above),
        # not the fragile department-modified score, to split VP decision power.
        return "decision_maker" if score >= 82 else "influencer"
    if seniority == "director":
        return "influencer"
    if seniority == "manager":
        return "evaluator"
    return "end_user"
