"""Deterministic tech-stack fingerprinting from raw page HTML.

No LLM — pure pattern matching against known SaaS markers (script srcs, cookie
names, DOM hooks). This is both an enrichment field (company.tech_stack) AND a
buying-signal source: detecting Salesforce / HubSpot / Intercom / Zendesk says
"budget exists and they buy tooling", which the user called out explicitly.
"""
from __future__ import annotations

import re

# marker substrings (lowercased) -> canonical product name + category
# Keep markers specific enough to avoid false positives.
_MARKERS: dict[str, tuple[str, str]] = {
    # CRM / MAP
    "js.hs-scripts.com": ("HubSpot", "crm"),
    "js.hsforms.net": ("HubSpot", "crm"),
    "_hsq": ("HubSpot", "crm"),
    "salesforce.com/analytics": ("Salesforce", "crm"),
    "pardot.com": ("Salesforce Pardot", "marketing"),
    "force.com": ("Salesforce", "crm"),
    "marketo.com": ("Marketo", "marketing"),
    "munchkin.js": ("Marketo", "marketing"),
    # Support / chat
    "intercom.io": ("Intercom", "support"),
    "widget.intercom.io": ("Intercom", "support"),
    "static.zdassets.com": ("Zendesk", "support"),
    "zendesk.com": ("Zendesk", "support"),
    "drift.com": ("Drift", "support"),
    "crisp.chat": ("Crisp", "support"),
    "tawk.to": ("Tawk.to", "support"),
    "front.com": ("Front", "support"),
    # Analytics
    "googletagmanager.com": ("Google Tag Manager", "analytics"),
    "google-analytics.com": ("Google Analytics", "analytics"),
    "segment.com/analytics.js": ("Segment", "analytics"),
    "cdn.segment.com": ("Segment", "analytics"),
    "mixpanel": ("Mixpanel", "analytics"),
    "amplitude.com": ("Amplitude", "analytics"),
    "fullstory.com": ("FullStory", "analytics"),
    "hotjar.com": ("Hotjar", "analytics"),
    "heap.io": ("Heap", "analytics"),
    "posthog.com": ("PostHog", "analytics"),
    # Email / lifecycle
    "klaviyo.com": ("Klaviyo", "email"),
    "mailchimp.com": ("Mailchimp", "email"),
    "customer.io": ("Customer.io", "email"),
    "braze.com": ("Braze", "email"),
    # Commerce / CMS / infra
    "cdn.shopify.com": ("Shopify", "ecommerce"),
    "myshopify.com": ("Shopify", "ecommerce"),
    "wp-content": ("WordPress", "cms"),
    "webflow.com": ("Webflow", "cms"),
    "wix.com": ("Wix", "cms"),
    "hubspotusercontent": ("HubSpot CMS", "cms"),
    "cdn.contentful.com": ("Contentful", "cms"),
    "vercel.app": ("Vercel", "infra"),
    "netlify.app": ("Netlify", "infra"),
    "cloudfront.net": ("AWS CloudFront", "infra"),
    "stripe.com/v3": ("Stripe", "payments"),
    "js.stripe.com": ("Stripe", "payments"),
    # Auth
    "clerk.accounts.dev": ("Clerk", "auth"),
    "auth0.com": ("Auth0", "auth"),
    "okta.com": ("Okta", "auth"),
}

# Products that indicate budget / active buying for B2B vendors -> signal worthy.
_BUYING_SIGNAL_PRODUCTS = {
    "Salesforce", "HubSpot", "Salesforce Pardot", "Marketo", "Intercom",
    "Zendesk", "Drift", "Segment", "Braze", "Klaviyo", "Okta", "Auth0",
}


def detect_tech(raw_html: str) -> list[dict]:
    """Return [{"product","category"}] detected in the HTML, deduped."""
    if not raw_html:
        return []
    hay = raw_html.lower()
    found: dict[str, str] = {}
    for marker, (product, category) in _MARKERS.items():
        if marker in hay:
            found[product] = category
    return [{"product": p, "category": c} for p, c in sorted(found.items())]


def tech_to_signals(tech: list[dict]) -> list[dict]:
    """Turn budget-indicating installs into tech_install buying signals."""
    out = []
    for t in tech:
        if t["product"] in _BUYING_SIGNAL_PRODUCTS:
            out.append({
                "kind": "tech_install",
                "label": f"{t['product']} installed",
                "description": f"Detected {t['product']} ({t['category']}) — indicates "
                               f"active tooling budget.",
                "severity": 0.55,
                "confidence": 0.9,
                "source": "techstack",
            })
    return out


def product_names(tech: list[dict]) -> list[str]:
    return [t["product"] for t in tech]
