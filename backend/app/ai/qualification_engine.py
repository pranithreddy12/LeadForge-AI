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
    # startup/funding directories & listicle sites
    "tracxn.com", "topstartups.io", "growthlist.co", "startups.gallery",
    "crunchbase.com", "pitchbook.com", "cbinsights.com", "dealroom.co",
    "failory.com", "eu-startups.com", "startupranking.com", "f6s.com",
    "seedtable.com", "startuplist.co", "betalist.com", "startupblink.com",
}

# Title patterns that signal a content/listicle/explainer page, not a company.
# DELIBERATELY HIGH-PRECISION: these only fire on clearly-content phrasings. Bare
# single-word tokens (guide, news, blog, jobs, pricing, faq, "<noun> for/to")
# were removed because they collide with real brand names ("Insurance Guide Inc",
# "Gusto - Payroll Software for Small Businesses"). Ambiguous cases are left for
# the AI classifier — false-rejecting a real buyer is worse than one extra LLM row.
# Content surfaces (blog/news/jobs/careers) are still caught by path + subdomain.
_JUNK_TITLE_PATTERNS = [
    r"^\s*what\s+is\b", r"^\s*how\s+to\b", r"^\s*why\s+\w",
    # listicles — all anchored on top/best/N so they can't match plain brands
    r"\btop\s+\d+\b",
    r"\btop\s+[\w&/\s]*?(startups?|companies|firms|tools|platforms|vendors|providers|software|services|solutions)\b",
    r"\bbest\s+[\w&/\s]*?(startups?|companies|services|solutions|tools|platforms|software|vendors|providers|firms|agencies)\b",
    r"\b\d[\d,]*\+?\s+[\w&/\s]*?(startups?|companies)\b",   # "11,130+ Series A Startups"
    r"\b(startups?|companies|funding)\s+(list|directory|database|rankings?)\b",
    r"\bways?\s+to\b",                                      # "Seven ways to finance…"
    r"\blist of\b",
    # comparison/alternatives are listicle signals only in anchored forms
    r"\b\w+\s+vs\.?\s+\w+\b",                               # "Asana vs Monday"
    r"\balternatives?\s+(to|for)\b",                        # "alternatives to X"
    # explainer "guide" only when anchored — bare "guide" collides with brands
    r"\b(ultimate|complete|beginner'?s|step[- ]by[- ]step)\s+guide\b",
    r"\bguide\s+to\b",                                      # "Guide to fundraising"
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


# First-labels that mark a job/ATS or content SUBDOMAIN (only when a parent
# domain exists, so the apex brands help.com / status.io / boards.ie survive).
_JUNK_SUBDOMAIN_LABELS = {"careers", "jobs", "apply", "boards", "blog", "news",
                          "support", "help", "docs", "status"}


def _is_junk_subdomain(dom: str) -> bool:
    labels = dom.split(".")
    # require >=3 labels (label0 . brand . tld) so apex 'help.com' is NOT junk
    return len(labels) >= 3 and labels[0] in _JUNK_SUBDOMAIN_LABELS


def deterministic_reject(c: Candidate) -> str | None:
    """Return a reason string if the candidate is obvious junk, else None.

    Tuned for HIGH PRECISION — when unsure, return None and let the AI classifier
    decide. Wrongly killing a real buyer here is worse than one extra LLM row.
    """
    dom = (c.domain or "").lower()
    if any(dom == d or dom.endswith("." + d) for d in _JUNK_DOMAINS):
        return "junk_domain"
    if _is_junk_subdomain(dom):
        return "junk_subdomain"
    # Check path fragments against the URL PATH only — matching the whole URL
    # string would false-positive on the domain (e.g. "/guide" in "//guidewire").
    from urllib.parse import urlparse
    path = urlparse((c.url or "").lower()).path
    if any(frag in path for frag in _JUNK_PATH_FRAGMENTS):
        return "content_path"
    if _TITLE_RE.search(c.title or ""):
        return "content_title"
    # Length check on the BRAND portion only (before the " - tagline"), so an
    # SEO homepage like "Notion - The all-in-one workspace …" isn't dropped.
    if len(_clean_title(c.title or "").split()) > 12:
        return "title_too_long"
    return None


# ---- Stage 2: batched AI classifier ---------------------------------------

_QUALIFY_SYSTEM = """\
You are a B2B company qualifier. You receive a numbered list of web search
results (title, domain, snippet). For EACH entry decide whether it represents a
REAL operating company that could be sold to — NOT a blog post, news article,
"what is / how to" explainer, "top N / best X" listicle, vendor directory,
comparison page, job board, or encyclopedia entry.

If a SELLER description is provided, ALSO flag direct COMPETITORS: companies
whose primary business is offering the same product/service as the seller. A
competitor is NOT a buyer — set is_competitor=true AND is_company=false for them
(we never want competitors in the lead list). Example: if the seller offers
"fractional CFO services", another fractional-CFO firm is a competitor.

For real, non-competitor companies, extract a clean company name (strip taglines
/ " - " suffix) and best-guess industry. Be strict: when in doubt, is_company=false.
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
                    "is_competitor": {"type": "boolean"},
                    "company_name": {"type": "string"},
                    "industry": {"type": "string"},
                    "confidence": {"type": "integer"},
                    "reject_reason": {"type": "string"},
                },
                "required": ["index", "is_company", "is_competitor", "company_name",
                             "industry", "confidence", "reject_reason"],
            },
        }
    },
    "required": ["results"],
}


def ai_qualify(candidates: list[Candidate], *, min_confidence: int = 55,
               seller_description: str | None = None) -> list[dict]:
    """Classify all candidates in ONE batched LLM call.

    Returns a list aligned by input index:
        {"index", "is_company", "company_name", "industry", "confidence", "ai_verified"}
    On provider error, falls back to deterministic-accept (see below).
    """
    if not candidates:
        return []

    listing = "\n".join(
        f"{i}. title={c.title!r} domain={c.domain!r} snippet={(c.snippet or '')[:160]!r}"
        for i, c in enumerate(candidates)
    )
    # Keep the OFFERING (strongest competitor signal) — put it first so a long
    # business_description can't truncate it away.
    seller_block = ""
    if seller_description:
        sd = seller_description.strip()
        offering = ""
        if "Offering:" in sd:
            sd, _, offering = sd.partition("Offering:")
            offering = " Offering:" + offering.strip()
        seller_block = f"SELLER offers:{offering[:200]} {sd[:300]}\n\n"
    user = (
        f"{seller_block}Classify these {len(candidates)} search results. Return one "
        f"object per index (0..{len(candidates) - 1}).\n\n{listing}"
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
        # confidence rather than discarding real companies. Marked ai_verified=
        # False so downstream can re-screen.
        # IMPORTANT BLIND SPOT: with the LLM down we CANNOT detect competitors,
        # so competitor exclusion is disabled for these rows. They must be
        # treated as un-vetted (ai_verified=False) until re-qualified.
        log.warning("qualify_provider_error_deterministic_fallback",
                    n=len(candidates), competitor_filter="disabled")
        return [{"index": i, "is_company": True, "is_competitor": False,
                 "company_name": _clean_title(c.title), "industry": "",
                 "confidence": 50, "ai_verified": False}
                for i, c in enumerate(candidates)]

    by_index = {r["index"]: r for r in out.get("results", []) if "index" in r}
    results = []
    for i, c in enumerate(candidates):
        r = by_index.get(i, {})
        is_competitor = bool(r.get("is_competitor"))
        is_co = (
            bool(r.get("is_company"))
            and not is_competitor
            and int(r.get("confidence", 0)) >= min_confidence
        )
        results.append({
            "index": i,
            "is_company": is_co,
            "is_competitor": is_competitor,
            "company_name": (r.get("company_name") or c.title).strip(),
            "industry": (r.get("industry") or "").strip(),
            "confidence": int(r.get("confidence", 0)),
            "ai_verified": True,   # this row came from a real AI judgment
        })
    return results


def qualify_candidates(candidates: list[Candidate], *, min_confidence: int = 55,
                       seller_description: str | None = None
                       ) -> tuple[list[dict], dict]:
    """Full pipeline: deterministic reject → AI classify the survivors.

    When `seller_description` is provided, direct competitors are rejected too.

    Returns (accepted, stats) where accepted is a list of
        {"candidate", "company_name", "industry", "confidence", "ai_verified"}
    and stats summarizes the funnel for logging/telemetry.
    """
    stats = {"total": len(candidates), "rejected_deterministic": 0,
             "rejected_ai": 0, "rejected_competitor": 0, "accepted": 0}

    survivors: list[Candidate] = []
    for c in candidates:
        reason = deterministic_reject(c)
        if reason:
            stats["rejected_deterministic"] += 1
        else:
            survivors.append(c)

    judged = ai_qualify(survivors, min_confidence=min_confidence,
                        seller_description=seller_description)
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
        elif j.get("is_competitor"):
            stats["rejected_competitor"] += 1
        else:
            stats["rejected_ai"] += 1

    stats["accepted"] = len(accepted)
    log.info("qualification_funnel", **stats)
    return accepted, stats
