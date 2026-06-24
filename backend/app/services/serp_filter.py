"""Two-track SERP processing (Phase 1D).

Intent-angle queries (1C) surface the right TOPICS but the SERP is dominated by
listicles, directories, and job/funding aggregators — content ABOUT buyers, not
buyer homepages. Two tracks turn that to advantage:

  (1) DEFENSIVE drop  — pure junk (listicles, directories, review marketplaces that
      never name one buyable company) is dropped at collection so it never consumes
      a candidate slot or a gate LLM call.
  (2) OFFENSIVE extract — funding news ("Acme raises $20M Series B") and job
      postings ("RevOps Manager at Acme") DO name a specific hiring/funded company.
      Extract that company name + best-effort domain and attach the signal type as
      metadata, turning a signal source INTO a pre-signaled buyer candidate.

A pre-signaled candidate reaches the gate as a real company with intent already
attached, so fewer gate LLM calls are wasted and buyer-share per call rises.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from app.ai.qualification_engine import Candidate, deterministic_reject

# Listicles / directories / review marketplaces / startup databases — never a single
# buyable company. DROP (track 1).
PURE_JUNK_DOMAINS = {
    "g2.com", "capterra.com", "getapp.com", "trustradius.com", "softwareadvice.com",
    "clutch.co", "owler.com", "growjo.com", "tracxn.com", "crunchbase.com",
    "pitchbook.com", "cbinsights.com", "dealroom.co", "growthlist.co", "topstartups.io",
    "startups.gallery", "failory.com", "startupranking.com", "f6s.com", "seedtable.com",
    "betalist.com", "startupblink.com", "wikipedia.org", "reddit.com", "quora.com",
    "medium.com", "producthunt.com", "gartner.com", "ventureradar.com", "us-fintech.com",
    "fintechmagazine.com", "zoominfo.com", "apollo.io", "rocketreach.co", "leadiq.com",
}

# Funding / startup news — articles NAME a specific funded company. EXTRACT (track 2).
FUNDING_NEWS_DOMAINS = {
    "techcrunch.com", "businesswire.com", "prnewswire.com", "globenewswire.com",
    "finsmes.com", "eu-startups.com", "tech.eu", "venturebeat.com", "axios.com",
    "fortune.com", "siliconangle.com", "fiercehealthcare.com", "techfundingnews.com",
    "saastr.com", "finextra.com",
}

# Job boards / ATS — postings NAME a specific hiring company. EXTRACT (track 2).
JOB_BOARD_DOMAINS = {
    "greenhouse.io", "lever.co", "ashbyhq.com", "ziprecruiter.com", "indeed.com",
    "builtin.com", "wellfound.com", "workable.com", "jobvite.com", "smartrecruiters.com",
    "linkedin.com", "glassdoor.com", "ashby.hq",
}

_FUNDING_VERB = (r"(?:raises?|raised|secures?|secured|closes?|closed|lands?|nabs?|"
                 r"snags?|bags?|announces?|to raise|gets?|scores?|hauls? in)")
_FUNDING_RE = re.compile(rf"^(.{{2,60}}?)\s+{_FUNDING_VERB}\s+.*?\$", re.I)
_FUNDING_POSSESS_RE = re.compile(r"^(.{2,60}?)['’]s\s+\$?[\d.,]+\s*(?:million|billion|[mbk])\b", re.I)
_SERIES_RE = re.compile(r"\b(series\s+[a-e]|seed|pre-seed)\b", re.I)

_JOB_HIRING_RE = re.compile(r"^(.{2,60}?)\s+(?:is\s+)?(?:hiring|seeking|looking for)\b", re.I)
_JOB_AT_RE = re.compile(r"\bat\s+([A-Z][\w&.'\-]+(?:\s+[A-Z][\w&.'\-]+){0,3})\s*$")

_NAME_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|co|gmbh|sa|ag|plc)\.?$", re.I)


def registrable_domain(domain: str | None) -> str:
    """brand.tld from a host (drop subdomains, best-effort)."""
    if not domain:
        return ""
    parts = domain.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain.lower()


def classify_source(domain: str | None, url: str | None, title: str | None) -> str:
    """-> 'junk' | 'funding_news' | 'job_board' | 'company'."""
    reg = registrable_domain(domain)
    if not reg:
        return "junk"
    if reg in PURE_JUNK_DOMAINS:
        return "junk"
    if reg in FUNDING_NEWS_DOMAINS:
        return "funding_news"
    if reg in JOB_BOARD_DOMAINS:
        return "job_board"
    return "company"


def _name_to_domain(name: str) -> str | None:
    base = name.split(" - ")[0].split(",")[0].split("|")[0].strip()
    base = _NAME_SUFFIX.sub("", base).strip()
    slug = re.sub(r"[^a-z0-9]", "", base.lower())
    return f"{slug}.com" if 2 <= len(slug) <= 40 else None


def _domain_from_job_url(url: str | None) -> str | None:
    """greenhouse/lever/ashby company slug, or a company's own careers host."""
    try:
        u = urlparse(url or "")
    except Exception:
        return None
    host = (u.netloc or "").lower()
    reg = registrable_domain(host)
    # Company's own careers page -> domain is the registrable host itself.
    if reg not in JOB_BOARD_DOMAINS and reg not in PURE_JUNK_DOMAINS and reg:
        if host.startswith("careers.") or host.startswith("jobs.") or "/careers" in (u.path or ""):
            return reg
    # ATS slug -> guess slug.com
    if reg in ("greenhouse.io", "lever.co", "ashbyhq.com"):
        segs = [s for s in (u.path or "").split("/") if s]
        if segs:
            slug = re.sub(r"[^a-z0-9]", "", segs[0].lower())
            if 2 <= len(slug) <= 40:
                return f"{slug}.com"
    return None


def _clean_company_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().strip("-–—|:").strip()


def _name_from_domain(domain: str | None) -> str:
    """Readable company name from a domain: molinahealthcare.com -> 'Molinahealthcare'.
    The gate classifies on domain+snippet, so exact casing matters little."""
    sld = registrable_domain(domain).split(".")[0]
    return sld.replace("-", " ").title() if sld else (domain or "")


def extract_company(*, title: str | None, url: str | None, snippet: str | None,
                    source_type: str) -> Candidate | None:
    """Extract a named company + signal from a funding-news / job-board hit.
    Returns a pre-signaled Candidate, or None if no specific company is named."""
    title = (title or "").strip()
    if source_type == "funding_news":
        m = _FUNDING_RE.match(title) or _FUNDING_POSSESS_RE.match(title)
        if not m and _SERIES_RE.search(title):
            # "Series B for Acme" style — take the capitalized run near the series.
            m2 = re.search(r"\bfor\s+([A-Z][\w&.'\-]+(?:\s+[A-Z][\w&.'\-]+){0,3})", title)
            m = m2 if m2 else None
        if not m:
            return None
        name = _clean_company_name(m.group(1))
        dom = _name_to_domain(name)
        if not name or not dom:
            return None
        detail = title[:160]
        return Candidate(title=name, url=url or "", domain=dom,
                         snippet=f"[funding signal] {detail}", source="extracted:funding",
                         signal={"type": "funding", "detail": detail})

    if source_type == "job_board":
        name = None
        m = _JOB_HIRING_RE.match(title)
        if m:
            name = _clean_company_name(m.group(1))
        else:
            m = _JOB_AT_RE.search(title)
            if m:
                name = _clean_company_name(m.group(1))
        if not name:
            return None
        dom = _domain_from_job_url(url) or _name_to_domain(name)
        if not dom:
            return None
        detail = title[:160]
        return Candidate(title=name, url=url or "", domain=dom,
                         snippet=f"[hiring signal] {detail}", source="extracted:hiring",
                         signal={"type": "hiring", "detail": detail})
    return None


def process_hit(*, title: str | None, url: str | None, snippet: str | None,
                source: str, drop_junk: bool = True, extract: bool = True
                ) -> Candidate | None:
    """Two-track processing of one SERP hit. Returns a Candidate to keep, or None to
    drop. `drop_junk`/`extract` toggle the tracks (for before/after measurement)."""
    if not (title and url):
        return None
    domain = registrable_domain(urlparse(url).netloc)
    kind = classify_source(domain, url, title)

    if kind == "junk":
        return None if drop_junk else Candidate(title=title, url=url, domain=domain,
                                                snippet=snippet, source=source)
    if kind in ("funding_news", "job_board"):
        if extract:
            return extract_company(title=title, url=url, snippet=snippet, source_type=kind)
        # extraction off: a signal-source page that isn't a company homepage -> drop
        # if drop_junk, else keep raw (baseline behavior).
        return None if drop_junk else Candidate(title=title, url=url, domain=domain,
                                                snippet=snippet, source=source)
    # "company"-kind by domain. A company's OWN careers/jobs page is the cleanest
    # signal in the whole SERP — the DOMAIN is the company and the page proves it's
    # hiring. Extract it as a pre-signaled hiring candidate instead of letting the
    # content-path heuristic drop it (which was discarding real buyers like a provider
    # group's "Director, Sales - careers" posting).
    u = urlparse(url)
    host = (u.netloc or "").lower()
    path = (u.path or "").lower()
    on_own_careers = (host.startswith("careers.") or host.startswith("jobs.")
                      or "/careers" in path or "/jobs" in path or "/job/" in path)
    if extract and on_own_careers:
        return Candidate(title=_name_from_domain(domain), url=url, domain=domain,
                         snippet=f"[hiring signal] {title[:160]}", source="extracted:hiring",
                         signal={"type": "hiring", "detail": title[:160]})

    # Otherwise the URL/title can still betray a listicle/content page on a random
    # blog domain (not in PURE_JUNK_DOMAINS). Apply the gate's content heuristics so
    # these drop at the SERP level and don't consume a candidate slot.
    cand = Candidate(title=title, url=url, domain=domain, snippet=snippet, source=source)
    if drop_junk and deterministic_reject(cand):
        return None
    return cand
