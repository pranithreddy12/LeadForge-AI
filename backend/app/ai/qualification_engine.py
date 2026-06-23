"""Company Qualification Engine (Phase 1).

Search results are noisy: blogs, "what is X" explainers, "top 10 X" listicles,
vendor directories, job boards, news articles. Persisting those as companies is
what turns a lead-intelligence platform back into a junk database.

Two-stage filter:

  1. Deterministic pre-filter (instant, no LLM) — kills the obvious junk by URL
     shape and title pattern. Cheap and removes ~60-80% of noise.
  2. Batched AI classifier (ONE LLM call for all survivors) — judges whether each
     remaining entry is a real operating company and extracts a clean name +
     industry + confidence. Batching keeps it fast and free-tier friendly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.ai.openai_client import complete_json
from app.core.logging import get_logger

log = get_logger(__name__)


# ---- Stage 1: deterministic pre-filter ------------------------------------

# Domains that are never "a company we'd sell to" in this context.
_JUNK_DOMAINS = {
    "ziprecruiter.com", "glassdoor.com", "indeed.com", "lever.co", "greenhouse.io",
    "ashbyhq.com", "workable.com", "g2.com", "capterra.com", "getapp.com",
    "trustradius.com", "clutch.co", "ventureradar.com", "crunchbase.com",
    "wikipedia.org", "reddit.com", "quora.com", "medium.com", "substack.com",
    "youtube.com", "forbes.com", "techcrunch.com", "businesswire.com",
    "prnewswire.com", "globenewswire.com", "yahoo.com", "bloomberg.com",
    "gartner.com", "softwareadvice.com", "producthunt.com", "wellfound.com",
    "angel.co", "builtin.com",
    # accelerators / VC portfolio listings / startup directories — not target accounts
    "ycombinator.com", "techstars.com", "500.co", "techcrunch.com",
    "us-fintech.com", "fintechmagazine.com", "growjo.com", "owler.com",
    "zoominfo.com", "apollo.io", "rocketreach.co", "leadiq.com",
}

# Title patterns that signal a content/listicle/explainer page, not a company.
_JUNK_TITLE_PATTERNS = [
    r"^\s*what\s+is\b", r"^\s*how\s+to\b", r"^\s*why\b", r"\bguide\b",
    r"\btop\s+\d+\b",
    r"\bbest\s+[\w&/\s]*?(companies|services|solutions|tools|platforms|software|vendors|providers|firms|agencies)\b",
    r"\b(companies|services|tools|platforms|software|vendors|providers)\s+(for|to)\b",
    r"\b\d+\s+(best|top)\b", r"\bvs\.?\b", r"\balternatives?\b", r"\bcomparison\b",
    r"\breview(s|ed)?\b", r"\branked\b", r"\blist of\b", r"\bexamples?\b",
    r"\b(ultimate|complete|beginner'?s)\s+guide\b", r"\bblog\b", r"\bnews\b",
    r"\bjobs?\b\s*(now hiring|openings?)?", r"\bhiring\b", r"\bcareers?\b",
    r"\bdefinition\b", r"\btutorial\b", r"\bfaq\b", r"\bpricing\b",
]

# URL path fragments that indicate a content page rather than a homepage.
_JUNK_PATH_FRAGMENTS = [
    "/blog/", "/news/", "/article", "/articles/", "/guide", "/resources/",
    "/wiki/", "/jobs/", "/careers/", "/category/", "/tag/", "/press/",
    "/learn/", "/what-is", "/how-to", "/glossary/", "/comparison",
]

_TITLE_RE = re.compile("|".join(_JUNK_TITLE_PATTERNS), re.IGNORECASE)


def _clean_title(title: str) -> str:
    """Best-effort company-name cleanup for the no-AI fallback path:
    'NowCFO - Fractional CFO Services' -> 'NowCFO'."""
    t = re.sub(r"\s+", " ", title or "").strip()
    # Cut at the first separator that usually precedes a tagline.
    t = re.split(r"\s[-–—|:]\s", t)[0].strip()
    return t[:200] or title


@dataclass
class Candidate:
    title: str
    url: str
    domain: str | None
    snippet: str | None
    source: str


def deterministic_reject(c: Candidate) -> str | None:
    """Return a reason string if the candidate is obvious junk, else None."""
    dom = (c.domain or "").lower()
    if any(dom == d or dom.endswith("." + d) for d in _JUNK_DOMAINS):
        return "junk_domain"
    url = (c.url or "").lower()
    if any(frag in url for frag in _JUNK_PATH_FRAGMENTS):
        return "content_path"
    if _TITLE_RE.search(c.title or ""):
        return "content_title"
    # A homepage title is usually short-ish. Article titles run long.
    if len((c.title or "").split()) > 14:
        return "title_too_long"
    return None


# ---- Stage 2: batched AI classifier ---------------------------------------

_QUALIFY_SYSTEM = """\
You are a B2B company qualifier. You receive a numbered list of web search
results (title, domain, snippet). For EACH entry decide whether it represents a
REAL operating company that could be sold to — NOT a blog post, news article,
"what is / how to" explainer, "top N / best X" listicle, vendor directory,
comparison page, job board, or encyclopedia entry.

For real companies, extract a clean company name (strip taglines / " - " suffix)
and best-guess industry. Be strict: when in doubt, is_company=false.
"""

_QUALIFY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "is_company": {"type": "boolean"},
                    "company_name": {"type": "string"},
                    "industry": {"type": "string"},
                    "confidence": {"type": "integer"},
                    "reject_reason": {"type": "string"},
                },
                "required": ["index", "is_company", "company_name", "industry",
                             "confidence", "reject_reason"],
            },
        }
    },
    "required": ["results"],
}


def ai_qualify(candidates: list[Candidate], *, min_confidence: int = 55) -> list[dict]:
    """Classify all candidates in ONE batched LLM call.

    Returns a list aligned by input index:
        {"index", "is_company", "company_name", "industry", "confidence"}
    Entries the model couldn't judge (e.g. provider error) are returned with
    is_company=False so nothing junky slips through on failure.
    """
    if not candidates:
        return []

    listing = "\n".join(
        f"{i}. title={c.title!r} domain={c.domain!r} snippet={(c.snippet or '')[:160]!r}"
        for i, c in enumerate(candidates)
    )
    user = (
        f"Classify these {len(candidates)} search results. Return one object per "
        f"index (0..{len(candidates) - 1}).\n\n{listing}"
    )
    out = complete_json(
        system=_QUALIFY_SYSTEM,
        user=user,
        schema_name="Qualify",
        schema=_QUALIFY_SCHEMA,
        temperature=0.0,
    )
    if out.get("_provider_error"):
        # AI qualifier unavailable (e.g. rate-limited). The candidates already
        # survived the deterministic junk filter, so accept them at reduced
        # confidence rather than discarding real companies. Marked so the UI /
        # downstream can tell these weren't AI-verified.
        log.warning("qualify_provider_error_deterministic_fallback", n=len(candidates))
        return [{"index": i, "is_company": True,
                 "company_name": _clean_title(c.title), "industry": "",
                 "confidence": 50, "ai_verified": False}
                for i, c in enumerate(candidates)]

    by_index = {r["index"]: r for r in out.get("results", []) if "index" in r}
    results = []
    for i, c in enumerate(candidates):
        r = by_index.get(i, {})
        is_co = bool(r.get("is_company")) and int(r.get("confidence", 0)) >= min_confidence
        results.append({
            "index": i,
            "is_company": is_co,
            "company_name": (r.get("company_name") or c.title).strip(),
            "industry": (r.get("industry") or "").strip(),
            "confidence": int(r.get("confidence", 0)),
            "ai_verified": True,   # this row came from a real AI judgment
        })
    return results


def qualify_candidates(candidates: list[Candidate], *, min_confidence: int = 55
                       ) -> tuple[list[dict], dict]:
    """Full pipeline: deterministic reject → AI classify the survivors.

    Returns (accepted, stats) where accepted is a list of
        {"candidate", "company_name", "industry", "confidence", "ai_verified"}
    and stats summarizes the funnel for logging/telemetry.
    """
    stats = {"total": len(candidates), "rejected_deterministic": 0,
             "rejected_ai": 0, "accepted": 0}

    survivors: list[Candidate] = []
    for c in candidates:
        reason = deterministic_reject(c)
        if reason:
            stats["rejected_deterministic"] += 1
        else:
            survivors.append(c)

    judged = ai_qualify(survivors, min_confidence=min_confidence)
    accepted: list[dict] = []
    for j in judged:
        c = survivors[j["index"]]
        if j["is_company"]:
            accepted.append({
                "candidate": c,
                "company_name": j["company_name"],
                "industry": j["industry"],
                "confidence": j["confidence"],
                "ai_verified": j.get("ai_verified", True),
            })
        else:
            stats["rejected_ai"] += 1

    stats["accepted"] = len(accepted)
    log.info("qualification_funnel", **stats)
    return accepted, stats
