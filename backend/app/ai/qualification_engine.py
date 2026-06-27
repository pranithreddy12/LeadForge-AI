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

# ---- name-sanity (P0 #2) --------------------------------------------------
# Live SERP leaks ARTICLE HEADLINES as company names ("Canada's Top SME Employers
# 2026", "How This Logistics Company Dealt With Manual Work"). A real company name
# never looks like these. Reject the name itself, deterministically, before any LLM.
_NAME_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
# starts with Top/Best/The Best/How/What/Why or any digit (10 Best, 50 Greatest, ...)
_NAME_START_RE = re.compile(r"^\s*(?:the\s+best|top|best|how|what|why|\d)", re.IGNORECASE)
_NAME_ORDINAL_RE = re.compile(
    r"\b\d{1,4}\s+(?:best|top|greatest|companies|company|firms?|startups?|tools?|"
    r"platforms?|providers?|vendors?|solutions?|ways?|reasons?|employers?|tips?|examples?)\b",
    re.IGNORECASE,
)
# article separators (checked on the RAW title — _clean_title strips them)
_NAME_SEP_RE = re.compile(r"\s\|\s|\svs\.?\s", re.IGNORECASE)
# article words — only when QUALIFIED ("Complete Guide", "Buyer's Guide", "Annual
# Report"), so a real company like "Insurance Guide Inc" is NOT rejected.
_NAME_WORD_RE = re.compile(
    r"\b(?:complete|ultimate|definitive|comprehensive|in-?depth|buyer'?s|full|"
    r"annual|quarterly|essential)\s+(?:guide|reviews?|reports?|rankings?|listicle|list)\b",
    re.IGNORECASE)


def name_is_junk(title: str) -> str | None:
    """Return a reason if `title` looks like an ARTICLE/LISTICLE headline rather than a
    company name. Separators are checked on the raw title; the rest on the cleaned brand
    name so a real company's long SEO tagline isn't mistaken for a listicle. High
    precision — real brand names match none of these."""
    raw = (title or "").strip()
    if not raw:
        return None
    if _NAME_SEP_RE.search(raw):
        return "name_separator"
    name = _clean_title(raw)
    if len(name) > 80:
        return "name_too_long"
    if _NAME_YEAR_RE.search(name):
        return "name_has_year"
    if _NAME_START_RE.search(name):
        return "name_listicle_start"
    if _NAME_ORDINAL_RE.search(name):
        return "name_ordinal"
    if _NAME_WORD_RE.search(name):
        return "name_article_word"
    return None


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
    # Pre-attached buying signal when this candidate was EXTRACTED from a signal
    # source (funding news / job posting), e.g. {"type": "funding", "detail": "..."}.
    signal: dict | None = None


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
    # Name-sanity (runs before the LLM — free, deterministic): reject article/listicle
    # headlines masquerading as company names.
    if (nr := name_is_junk(c.title or "")):
        return nr
    return None


# ---- 8-way classifier (Phase 1B) ------------------------------------------
#
# The binary is_company gate leaked the IN-BAND classes (vendor/investor_vc/too_large)
# as "buyer" — precision ~50%. This replaces it with an explicit label per candidate:
TAXONOMY = ["buyer", "competitor", "vendor", "investor_vc",
            "job_board_or_directory", "listicle_or_content", "too_large", "unknown"]
# Only `buyer` proceeds to enrich/score/outreach. `unknown` is HELD (persist flagged,
# re-classify next run) — never dropped, never sent. Everything else is rejected.

# Maps the deterministic_reject reason -> a taxonomy label, so heuristic catches are
# free, fast, and reported separately from the LLM.
_DET_REASON_TO_LABEL = {
    "junk_domain": "job_board_or_directory",
    "junk_subdomain": "job_board_or_directory",
    "content_path": "listicle_or_content",
    "content_title": "listicle_or_content",
    "title_too_long": "listicle_or_content",
    "name_too_long": "listicle_or_content",
    "name_has_year": "listicle_or_content",
    "name_listicle_start": "listicle_or_content",
    "name_ordinal": "listicle_or_content",
    "name_separator": "listicle_or_content",
    "name_article_word": "listicle_or_content",
}


def heuristic_classify(c: Candidate) -> tuple[str | None, str]:
    """Deterministic, LLM-free first pass. Returns (label, reason) when confident,
    else (None, "") to defer to the AI classifier. HIGH PRECISION only — a wrong
    reject here is worse than one extra LLM row."""
    reason = deterministic_reject(c)
    if reason:
        return _DET_REASON_TO_LABEL.get(reason, "job_board_or_directory"), reason
    dom = (c.domain or "").lower()
    # VC/investor by TLD — VCs are firmographically tiny and in-band, so only a
    # what-they-are cue catches them deterministically.
    if dom.endswith(".vc") or dom.endswith(".ventures"):
        return "investor_vc", "vc_tld"
    return None, ""


_CLASSIFY_SYSTEM = """\
You classify B2B web-search results for a lead-gen system. For EACH numbered entry
(title, domain, snippet) assign exactly ONE label:

- buyer: a real operating company that could BUY the seller's service. A buyer
  CONSUMES automation/software to run its business. This INCLUDES software companies
  whose product is something OTHER than automation — e.g. security/compliance (Vanta),
  content creation (Jasper), planning/forecasting (Pigment), banking (Mercury),
  e-commerce platforms (OroCommerce), customer engagement/retention (Stellar), as well
  as non-software operators (DTC brands, clinics, insurance brokerages). Selling
  software does NOT make a company a vendor.
- competitor: a company whose offering is the SAME as the seller's (see SELLER
  block) — e.g. another agency / done-for-you service selling the same outcomes.
- vendor: ONLY when the company's PRIMARY PRODUCT IS automation / workflow / integration
  / RPA / RevOps tooling itself — i.e. it sells AUTOMATION as the product. Examples:
  Zapier, Make, UiPath (RPA), Clari (RevOps), Notable (workflow-automation), an
  industrial-automation maker. DECISIVE TEST: would a buyer purchase THIS company's
  product to automate their own work? If yes -> vendor. If the company merely USES
  automation while selling something else -> buyer. IGNORE the words "automated/
  automation" used as a marketing adjective (e.g. "automated compliance") — classify by
  what the company SELLS, not buzzwords.
- investor_vc: a venture capital firm, accelerator, or investor.
- job_board_or_directory: job board, staffing site, software/agency directory,
  review marketplace.
- listicle_or_content: a blog post, "what is / how to" explainer, "top N / best X"
  listicle, news article — a PAGE, not a company.
- too_large: a real company but far too big for a mid-market ICP (snippet implies
  many thousands of employees / global enterprise giant).
- unknown: you genuinely cannot tell from the evidence. Use this rather than
  guessing "buyer".

KEY RULE: consumes automation => buyer; SELLS automation/RevOps/AI-workflow =>
vendor or competitor. When unsure, prefer unknown over buyer. Give a one-line
reason citing a CONCRETE fact from the title/snippet (what the company does).
"""

_CLASSIFY_SCHEMA: dict = {
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
                    "label": {"type": "string", "enum": TAXONOMY},
                    "reason": {"type": "string"},
                    "confidence": {"type": "integer"},
                },
                "required": ["index", "label", "reason", "confidence"],
            },
        }
    },
    "required": ["results"],
}


def ai_classify(candidates: list[Candidate], *, seller_description: str | None = None) -> dict:
    """One batched LLM call -> {"results": [...]} or {"_provider_error": True}."""
    if not candidates:
        return {"results": []}
    listing = "\n".join(
        f"{i}. title={c.title!r} domain={c.domain!r} snippet={(c.snippet or '')[:160]!r}"
        for i, c in enumerate(candidates)
    )
    seller_block = ""
    if seller_description:
        sd = seller_description.strip()
        offering = ""
        if "Offering:" in sd:
            sd, _, offering = sd.partition("Offering:")
            offering = " Offering:" + offering.strip()
        seller_block = f"SELLER offers:{offering[:200]} {sd[:300]}\n\n"
    user = (f"{seller_block}Classify these {len(candidates)} results. One object per "
            f"index (0..{len(candidates) - 1}).\n\n{listing}")
    out = complete_json(system=_CLASSIFY_SYSTEM, user=user, schema_name="Classify",
                        schema=_CLASSIFY_SCHEMA, temperature=0.0)
    if out.get("_provider_error"):
        return {"_provider_error": True}
    return out


def classify_candidates(candidates: list[Candidate], *, seller_description: str | None = None,
                        min_confidence: int = 55) -> list[dict]:
    """Heuristic-first, then LLM for the rest. Returns one dict per candidate:
        {index, label, reason, source: heuristic|llm|provider_error, confidence}

    On provider error the unresolved candidates become `unknown` (HELD — never
    `buyer`, never dropped). A low-confidence `buyer` from the LLM is downgraded to
    `unknown` so only confident buyers proceed.
    """
    results: list[dict | None] = [None] * len(candidates)
    to_llm: list[int] = []
    for i, c in enumerate(candidates):
        label, reason = heuristic_classify(c)
        if label:
            results[i] = {"index": i, "label": label, "reason": reason,
                          "source": "heuristic", "confidence": 95}
        else:
            to_llm.append(i)

    if to_llm:
        judged = ai_classify([candidates[i] for i in to_llm],
                             seller_description=seller_description)
        if judged.get("_provider_error"):
            log.warning("classify_provider_error_unknown_hold", n=len(to_llm),
                        domains=[candidates[i].domain for i in to_llm])
            for i in to_llm:
                results[i] = {"index": i, "label": "unknown",
                              "reason": "provider_error: hold and re-classify next run",
                              "source": "provider_error", "confidence": 0}
        else:
            by_sub = {r["index"]: r for r in judged.get("results", []) if "index" in r}
            for sub_i, i in enumerate(to_llm):
                r = by_sub.get(sub_i, {})
                label = r.get("label") if r.get("label") in TAXONOMY else "unknown"
                conf = int(r.get("confidence", 0))
                # Only CONFIDENT buyers proceed; a shaky buyer is held as unknown.
                if label == "buyer" and conf < min_confidence:
                    label = "unknown"
                results[i] = {"index": i, "label": label,
                              "reason": (r.get("reason") or "").strip(),
                              "source": "llm", "confidence": conf}
    return [r for r in results if r is not None]


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
                       ) -> tuple[list[dict], dict, list[dict]]:
    """Full 8-way pipeline (Phase 1B): heuristic-first, then LLM for the rest.

    Returns (accepted, stats, held):
      - accepted: candidates labeled `buyer` -> proceed to enrich/score/outreach.
          [{"candidate","company_name","industry","confidence","ai_verified","reason"}]
      - held: candidates labeled `unknown` (incl. provider-error) -> HOLD, never sent,
          re-classify next run. [{"candidate","reason","source"}]
      - stats: funnel counts incl. per-label and per-source (heuristic vs llm).
    Everything else (vendor/competitor/investor_vc/job_board/listicle/too_large) is
    rejected. NOTHING-STATIC: on provider error rows become `unknown` (held), never
    `buyer`, never demo-fallback.
    """
    judged = classify_candidates(candidates, seller_description=seller_description,
                                 min_confidence=min_confidence)
    accepted: list[dict] = []
    held: list[dict] = []
    stats = {"total": len(candidates), "accepted": 0, "held_unknown": 0,
             "by_label": {}, "by_source": {}}
    for j in judged:
        c = candidates[j["index"]]
        stats["by_label"][j["label"]] = stats["by_label"].get(j["label"], 0) + 1
        stats["by_source"][j["source"]] = stats["by_source"].get(j["source"], 0) + 1
        if j["label"] == "buyer":
            accepted.append({"candidate": c, "company_name": _clean_title(c.title),
                             "industry": "", "confidence": j["confidence"],
                             "ai_verified": j["source"] != "provider_error",
                             "reason": j["reason"]})
        elif j["label"] == "unknown":
            held.append({"candidate": c, "reason": j["reason"], "source": j["source"]})

    stats["accepted"] = len(accepted)
    stats["held_unknown"] = len(held)
    log.info("classification_funnel", total=stats["total"], accepted=stats["accepted"],
             held=stats["held_unknown"], by_label=stats["by_label"],
             by_source=stats["by_source"])
    return accepted, stats, held
