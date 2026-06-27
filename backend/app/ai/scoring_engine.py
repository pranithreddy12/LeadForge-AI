from __future__ import annotations

import math
from dataclasses import dataclass

from app.ai.openai_client import complete_json
from app.ai.prompts import SCORING_SYSTEM
from app.ai.schemas import SCORING_JSON_SCHEMA

DEFAULT_WEIGHTS: dict[str, float] = {
    "fit": 1.6,
    "funding": 1.2,
    "hiring": 1.4,
    "growth": 1.1,
    "tech_match": 1.0,
    "email": 0.6,
    "activity": 0.8,
}

GRADE_BANDS = [
    (90, "A+"), (80, "A"), (70, "B"), (55, "C"), (40, "D"), (0, "F"),
]


@dataclass
class ScoreInput:
    icp: dict        # ICP row as dict
    company: dict    # Company row as dict
    signals: list[dict]
    contacts: list[dict]


def grade_for(score: int) -> str:
    for cutoff, grade in GRADE_BANDS:
        if score >= cutoff:
            return grade
    return "F"


def _heuristic_subscores(inp: ScoreInput) -> dict[str, int]:
    """Cheap, fully-deterministic baseline subscores. Used when no LLM is invoked
    or as a sanity floor on top of the LLM output."""
    icp = inp.icp or {}
    company = inp.company or {}
    signals = inp.signals or []
    contacts = inp.contacts or []

    # --- fit ---
    fit = 50
    if company.get("industry") and company["industry"] in (icp.get("industries") or []):
        fit += 25
    if company.get("country") and company["country"] in (icp.get("countries") or []):
        fit += 10

    # Employee-size fit: reward being INSIDE the ICP band, but PENALIZE being
    # outside it proportionally to how far off-size the company is. A grossly
    # off-size account (a 27k-employee industrial giant or a 9-person shop for a
    # 50–1000 ICP) is a strong disqualifier, not merely a missed bonus — without
    # this penalty such rows kept the base 50 + industry/country bonuses and
    # passed scoring. Unknown size (0/None) is left neutral so freshly-discovered,
    # not-yet-enriched rows aren't unfairly punished.
    emp = company.get("employee_count") or 0
    emp_min = icp.get("employee_min") or 0
    emp_max = icp.get("employee_max") or 10**9
    if emp > 0:
        if emp_min <= emp <= emp_max:
            fit += 15
        else:
            ratio = (emp / emp_max) if emp > emp_max else (emp_min / max(1, emp))
            # log2 ramp: 1.5x→-14, 2x→-24, 3x→-38, 5x→-56, ≥~5.7x→-60 (capped)
            fit -= min(60, int(24 * math.log2(max(1.0, ratio))))
    fit = max(0, min(100, fit))

    # --- per-signal subscores ---
    def by_kind(kind: str) -> list[dict]:
        return [s for s in signals if s.get("kind") == kind]

    def sig_score(kind: str) -> int:
        relevant = by_kind(kind)
        if not relevant:
            return 0
        # blend severity * confidence; saturating to 100. A single CONFIDENT buying
        # signal should register real intent: the old log curve floored a strong,
        # fresh "just raised a round" at ~56, which (combined with the contact/tech
        # drag) kept genuine buyers stuck at C. Saturating-exponential: one solid
        # signal ~70-74, several strong ones 85+.
        agg = sum(min(1.0, s.get("severity", 0.5) * s.get("confidence", 0.7)) for s in relevant)
        return min(100, int(45 + 48 * (1 - math.exp(-1.4 * agg))))

    funding = sig_score("funding")
    hiring = sig_score("hiring")
    growth = max(sig_score("growth"), sig_score("traffic_growth"),
                 sig_score("office_expansion"))
    product_launch = sig_score("product_launch")

    # --- tech match ---
    required = set([t.lower() for t in (icp.get("tech_stack_required") or [])])
    excluded = set([t.lower() for t in (icp.get("tech_stack_excluded") or [])])
    stack = set([t.lower() for t in (company.get("tech_stack") or [])])
    if required and required & stack:
        tech_match = 60 + 10 * len(required & stack)
    elif required:
        tech_match = 30
    else:
        tech_match = 50
    if excluded and excluded & stack:
        tech_match = max(0, tech_match - 40)
    tech_match = min(100, tech_match)

    # --- email/contacts ---
    if not contacts:
        email_score = 20
    else:
        valid = [c for c in contacts if c.get("email_status") == "valid"]
        risky = [c for c in contacts if c.get("email_status") == "risky"]
        email_score = min(100, 30 + 20 * len(valid) + 5 * len(risky))

    # --- activity (recency) ---
    activity = max(40, min(100, 40 + 10 * len(signals)))

    # Apply event-launch as a boost to growth when present (product launch ≈ growth signal).
    growth = min(100, growth + product_launch // 4)

    return {
        "fit_score": fit,
        "funding_score": funding,
        "hiring_score": hiring,
        "growth_score": growth,
        "tech_match_score": tech_match,
        "email_score": email_score,
        "activity_score": activity,
    }


def _weighted_total(sub: dict[str, int], icp_weights: dict[str, float] | None,
                    active: set[str] | None = None) -> int:
    """Weighted blend of subscores. `active` is the set of subscore keys that carry
    signal for THIS lead; keys not in `active` are dropped from the blend and the
    denominator is renormalized over what remains. This is how an uninformative axis
    (no contacts searched yet -> email; ICP sets no tech stack -> tech_match) stays
    out of the grade instead of dragging a strong fit/intent lead toward 50/20."""
    w = {**DEFAULT_WEIGHTS}
    if icp_weights:
        # ICP weights are keyed by signal kind; remap onto subscore weights.
        # (fit/email/activity always use defaults.)
        for k in ("funding", "hiring", "growth", "tech_match"):
            if k in icp_weights:
                w[k] = float(icp_weights[k])

    pairs = [
        ("fit_score", w["fit"]),
        ("funding_score", w["funding"]),
        ("hiring_score", w["hiring"]),
        ("growth_score", w["growth"]),
        ("tech_match_score", w["tech_match"]),
        ("email_score", w["email"]),
        ("activity_score", w["activity"]),
    ]
    if active is not None:
        pairs = [(k, weight) for k, weight in pairs if k in active]
    if not pairs:
        return 0
    num = sum(sub[k] * weight for k, weight in pairs)
    den = sum(weight for _, weight in pairs) * 100
    score = int(round(100 * num / den))
    return max(0, min(100, score))


def score_lead(inp: ScoreInput, *, use_llm: bool = True) -> dict:
    """Score a single (company, ICP) pair.

    Strategy:
    - Compute heuristic subscores deterministically.
    - Ask the LLM to *adjust* and provide reasoning. Cap +/- 15 per axis.
    - Weighted blend into a 0..100 score; assign letter grade.
    """
    base = _heuristic_subscores(inp)

    llm = {}
    if use_llm:
        user = (
            f"ICP:\n{inp.icp}\n\nCompany:\n{inp.company}\n\n"
            f"Signals:\n{inp.signals}\n\nHeuristic subscores:\n{base}\n\n"
            "Adjust each subscore +/-15 max based on the evidence, and supply "
            "3-5 reasoning bullets a sales rep would put in a CRM."
        )
        llm = complete_json(
            system=SCORING_SYSTEM,
            user=user,
            schema_name="Score",
            schema=SCORING_JSON_SCHEMA,
            temperature=0.2,
        ) or {}

    sub = dict(base)
    for k in ("fit_score", "funding_score", "hiring_score", "growth_score",
              "tech_match_score", "email_score", "activity_score"):
        adj = llm.get(k)
        if isinstance(adj, int):
            adj = max(base[k] - 15, min(base[k] + 15, adj))
            sub[k] = max(0, min(100, adj))

    # Which axes carry signal for THIS lead. Contactability and tech-match are only
    # informative when we've actually searched contacts / the ICP defines a stack —
    # otherwise they must not drag a strong fit/intent lead down (the bug that floored
    # fresh, not-yet-contacted buyers to C/D, i.e. the all-C daily run).
    icp = inp.icp or {}
    company = inp.company or {}
    active = {"fit_score", "funding_score", "hiring_score", "growth_score", "activity_score"}
    if inp.contacts:
        active.add("email_score")
    if (icp.get("tech_stack_required") or icp.get("tech_stack_excluded")
            or company.get("tech_stack")):
        active.add("tech_match_score")

    # Don't penalize a lead that IS showing buying intent for the signal TYPES it
    # happens to lack: grade it on the signals it has (richer signal COUNT is still
    # rewarded via activity_score). A lead with NO signals at all keeps every intent
    # axis (each at 0) so it correctly scores cold regardless of fit.
    if inp.signals:
        for axis in ("funding_score", "hiring_score", "growth_score"):
            if sub.get(axis, 0) <= 0:
                active.discard(axis)

    weights = icp.get("weights") or {}
    final = _weighted_total(sub, weights, active)

    # Hard size ceiling. The fit penalty is ONE axis in the blend and can be outvoted
    # by strong intent signals — in production a 1,479- or 27,000-emp firm with real
    # funding/hiring signals climbed back to B/C. Size is a stated hard ICP constraint,
    # so a grossly off-size company must not reach B/A regardless of signal strength.
    # (Mirrors the daily workflow's enforce_icp_size filter at the score level.) A 15%
    # grace avoids a cliff right at the band boundary.
    emp = company.get("employee_count") or 0
    emp_min = icp.get("employee_min") or 0
    emp_max = icp.get("employee_max") or 10**9
    if emp > 0 and not (emp_min <= emp <= emp_max):
        ratio = (emp / emp_max) if emp > emp_max else (emp_min / max(1, emp))
        if ratio > 1.15:
            final = min(final, max(40, int(69 - 12 * math.log2(ratio))))

    # BUG 5: a non-buyer GATE VERDICT hard-caps the score. A vendor/competitor/VC scores
    # like a great buyer on firmographics+signals, so without this it can be the top lead.
    # Consult the gate's verdict (classification_label) and cap at 40 / grade F.
    label = (company.get("classification_label") or "").strip().lower()
    grade = grade_for(final)
    if label and label != "buyer":
        final = min(final, 40)
        grade = "F"
        reasoning = [f"Gate classified this company as '{label}', not a buyer — excluded "
                     "from the lead pool regardless of firmographics."]
    else:
        reasoning = list(llm.get("reasoning") or [])

    probability = round(final / 100.0, 2)
    return {
        **sub,
        "score": final,
        "grade": grade,
        "probability": probability,
        "reasoning": reasoning[:6],
        "raw": {"heuristic": base, "llm": llm},
    }
