"""Demo-mode fixtures for when external API keys are not configured.

Every helper here returns realistic-looking, hand-crafted data that matches
the same JSON shape the real provider would return — so the rest of the
pipeline (scoring, persistence, UI) works end-to-end without any real keys.

Each payload includes ``"demo": true`` (or `source="demo"`) so demo output
can never be confused with production output downstream.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any

# ---- ICP -------------------------------------------------------------------

def demo_icp(business_description: str) -> dict[str, Any]:
    """Templated ICP — tries to react to a few obvious vertical keywords."""
    bd = (business_description or "").lower()
    if "qa" in bd or "test automation" in bd:
        industries = ["SaaS", "Fintech", "Healthcare"]
        personas = ["CTO", "VP Engineering", "QA Manager", "Director of Engineering"]
        signals = ["Hiring QA Engineers", "Recent Series A/B funding", "Mobile app launch"]
        keywords = ["QA engineer", "test automation", "SDET", "mobile testing"]
    elif "cyber" in bd or "security" in bd or "soc" in bd:
        industries = ["SaaS", "Fintech", "Healthcare", "B2B Marketplaces"]
        personas = ["CISO", "VP Security", "Head of Engineering"]
        signals = ["SOC 2 hiring", "Recent breach in vertical", "ISO 27001 audit"]
        keywords = ["SOC analyst", "security engineer", "compliance"]
    elif "chatbot" in bd or "ecommerce" in bd:
        industries = ["E-commerce", "DTC Brands", "Retail SaaS"]
        personas = ["Head of CX", "VP Marketing", "Director of E-commerce"]
        signals = ["Shopify Plus install", "Traffic growth", "New Klaviyo install"]
        keywords = ["Shopify", "DTC", "customer experience", "support automation"]
    else:
        industries = ["SaaS", "B2B Services", "Mid-market"]
        personas = ["CEO", "Founder", "VP Sales", "VP Marketing"]
        signals = ["Recent funding", "Hiring spree", "Product launch"]
        keywords = ["growth", "scale", "operations"]

    return {
        "name": "Demo ICP — auto-generated",
        "summary": (
            f"Mid-market companies likely to need: {business_description.strip() or 'your offering'}. "
            "Generated in demo mode (no OpenAI key set)."
        ),
        "industries": industries,
        "sub_industries": [],
        "countries": ["USA", "UK", "Canada", "Germany"],
        "regions": ["North America", "EMEA"],
        "employee_min": 20,
        "employee_max": 500,
        "revenue_min_usd": 1_000_000,
        "revenue_max_usd": 100_000_000,
        "buyer_personas": personas,
        "buying_signals": signals,
        "keywords": keywords,
        "excluded_keywords": ["intern", "student"],
        "tech_stack_required": [],
        "tech_stack_excluded": [],
        "weights": {
            "hiring": 1.4, "funding": 1.3, "growth": 1.1, "product_launch": 1.0,
            "tech_install": 0.9, "leadership_change": 0.8, "partnership": 0.8,
            "news": 0.6, "traffic_growth": 1.0, "office_expansion": 0.9,
        },
        "demo": True,
    }


# ---- Signals ---------------------------------------------------------------

DEMO_SIGNAL_BANK: list[dict[str, Any]] = [
    {"kind": "hiring", "label": "Hiring: Senior QA Automation Engineer",
     "description": "Open role for an SDET with Playwright/Cypress; team expanding.",
     "severity": 0.8, "confidence": 0.85},
    {"kind": "funding", "label": "Raised $14M Series A",
     "description": "Series A led by Accel; will hire across engineering and GTM.",
     "severity": 0.9, "confidence": 0.95},
    {"kind": "product_launch", "label": "Launched mobile beta",
     "description": "Public TestFlight beta of their iOS app — strong intent on mobile QA.",
     "severity": 0.7, "confidence": 0.8},
    {"kind": "tech_install", "label": "Salesforce + HubSpot detected",
     "description": "BuiltWith shows recent Salesforce and HubSpot installs.",
     "severity": 0.5, "confidence": 0.7},
    {"kind": "growth", "label": "Headcount +25% over 90 days",
     "description": "LinkedIn employee count up 25% quarter-over-quarter.",
     "severity": 0.7, "confidence": 0.75},
    {"kind": "leadership_change", "label": "New VP of Engineering",
     "description": "VP Eng started 2 weeks ago — new vendor evaluations likely.",
     "severity": 0.65, "confidence": 0.7},
]


def demo_signals(company_name: str, source: str) -> list[dict[str, Any]]:
    rng = random.Random(_seed(company_name + source))
    pool = list(DEMO_SIGNAL_BANK)
    rng.shuffle(pool)
    n = rng.randint(2, 4)
    out = []
    for s in pool[:n]:
        out.append({
            **s,
            "observed_at": None,
            "url": f"https://example-source.com/{rng.randint(1000, 9999)}",
            "source": "demo",
        })
    return out


# ---- Scoring ---------------------------------------------------------------

def demo_score_adjust(base: dict[str, int]) -> dict[str, Any]:
    """Mimics the LLM-adjust step of scoring with deterministic +/- nudges."""
    return {
        "fit_score": base["fit_score"],
        "funding_score": min(100, base["funding_score"] + 5),
        "hiring_score": min(100, base["hiring_score"] + 8),
        "growth_score": base["growth_score"],
        "tech_match_score": base["tech_match_score"],
        "email_score": base["email_score"],
        "activity_score": base["activity_score"],
        "reasoning": [
            "Series A funding within last 6 months — budget cycle aligns.",
            "Active engineering hiring with QA-adjacent roles posted.",
            "Tech stack matches your typical buyer profile.",
            "Recent VP-level leadership change opens vendor re-evaluation.",
        ],
        "probability": 0.78,
        "demo": True,
    }


# ---- Opportunity -----------------------------------------------------------

def demo_opportunity(company: dict[str, Any]) -> dict[str, Any]:
    return {
        "probability": 0.78,
        "why_now": [
            f"{company.get('name', 'This account')} raised a Series A and is hiring engineers.",
            "Mobile launch in progress — QA bandwidth likely strained.",
            "New VP Eng signals openness to new tooling and partners.",
        ],
        "pain_points": [
            "Flaky E2E tests slowing release cadence.",
            "No dedicated QA hire yet — engineers self-test.",
            "Mobile coverage near zero.",
        ],
        "suggested_contact_title": "VP Engineering",
        "suggested_offer": (
            "Embedded QA automation engagement — 6 weeks to ship Playwright + mobile coverage."
        ),
        "talking_points": [
            "We helped a similar Series A SaaS cut their release time from 2 weeks to 2 days.",
            "Free 30-min audit of their current CI test pipeline.",
            "Async loom walkthrough of a tailored proposal.",
        ],
        "risks": [
            "VP Eng may be in initial 90-day evaluation — slower to commit.",
        ],
        "demo": True,
    }


# ---- Outreach --------------------------------------------------------------

def demo_outreach(company: dict[str, Any], contact: dict[str, Any] | None,
                  channel: str, tone: str) -> dict[str, Any]:
    name = (contact or {}).get("first_name") or (contact or {}).get("name", "there").split(" ")[0]
    cname = company.get("name", "your team")
    if channel == "linkedin":
        return {
            "variants": [
                {
                    "subject": "",
                    "body": (
                        f"Hi {name} — saw {cname}'s Series A and the mobile beta. "
                        "We helped two similar Series A SaaS teams ship Playwright + "
                        "mobile coverage in 6 weeks. Worth a 15-min look?"
                    ),
                },
            ],
            "demo": True,
        }
    return {
        "variants": [
            {
                "subject": f"Mobile QA bandwidth at {cname}",
                "body": (
                    f"Hi {name},\n\n"
                    f"Congrats on the Series A — saw the mobile beta is live. "
                    f"Two similar Series A SaaS teams asked us to ship Playwright + "
                    f"mobile coverage in 6 weeks; happy to share the playbook.\n\n"
                    "Open to a 15-min look next week?\n\n— Demo Founder"
                ),
            },
            {
                "subject": f"Async loom for {cname}?",
                "body": (
                    f"Hi {name},\n\n"
                    "Quick async loom of how we'd cut your E2E flake rate in half — "
                    "five minutes, no meeting. Reply 'yes' and it's in your inbox tomorrow.\n\n— Demo Founder"
                ),
            },
        ],
        "demo": True,
    }


# ---- Search (Tavily / Serper) ---------------------------------------------

DEMO_COMPANY_BANK: list[dict[str, Any]] = [
    {"name": "Linear", "domain": "linear.app",
     "snippet": "Issue tracking built for high-performance product teams."},
    {"name": "Vercel", "domain": "vercel.com",
     "snippet": "Frontend cloud for Next.js and React; hiring rapidly."},
    {"name": "Retool", "domain": "retool.com",
     "snippet": "Build internal tools fast; expanding mobile coverage."},
    {"name": "Census", "domain": "getcensus.com",
     "snippet": "Operational analytics platform — recently raised Series B."},
    {"name": "Sourcegraph", "domain": "sourcegraph.com",
     "snippet": "Code intelligence platform; hiring QA + SRE."},
    {"name": "Hex", "domain": "hex.tech",
     "snippet": "Modern data workspace — Series B 2026, hiring engineers."},
    {"name": "Mux", "domain": "mux.com",
     "snippet": "Video API for developers; new mobile SDK launch."},
    {"name": "Liveblocks", "domain": "liveblocks.app",
     "snippet": "Real-time collaboration infrastructure; expanding GTM team."},
    {"name": "Resend", "domain": "resend.com",
     "snippet": "Email API for developers; Series A 2026."},
    {"name": "Clerk Demo Tenant", "domain": "demo-clerk-tenant.com",
     "snippet": "Auth-as-a-service implementation reference."},
]


def demo_search(query: str, *, max_results: int = 10) -> list[dict[str, Any]]:
    rng = random.Random(_seed(query))
    pool = list(DEMO_COMPANY_BANK)
    rng.shuffle(pool)
    out = []
    for c in pool[:max_results]:
        out.append({
            "title": f"{c['name']} - {c['snippet']}",
            "url": f"https://{c['domain']}",
            "link": f"https://{c['domain']}",
            "content": c["snippet"],
            "snippet": c["snippet"],
            "score": 0.5,
            "demo": True,
        })
    return out


# ---- Email validation ------------------------------------------------------

def demo_email_validation(email: str) -> dict[str, Any]:
    rng = random.Random(_seed(email))
    pick = rng.choices(
        ["valid", "valid", "valid", "risky", "invalid"],  # weighted
        k=1,
    )[0]
    confidence = {"valid": rng.randint(80, 99), "risky": 50, "invalid": 0}[pick]
    return {"status": pick, "confidence": confidence, "provider": "demo"}


# ---- Embeddings ------------------------------------------------------------

def demo_embedding(text: str, dim: int) -> list[float]:
    """Stable, deterministic, ~unit-norm pseudo-embedding from text hash."""
    rng = random.Random(_seed(text))
    raw = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


# ---- helpers ---------------------------------------------------------------

def _seed(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:12], 16)
