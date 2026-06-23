"""JSON schemas passed to OpenAI `response_format=json_schema`.

These are the *strict* schemas — every property is required and additionalProperties=false.
For optional fields we use {"type": ["string", "null"]} rather than omitting them.
"""
from __future__ import annotations

ICP_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "summary": {"type": "string"},
        "industries": {"type": "array", "items": {"type": "string"}},
        "sub_industries": {"type": "array", "items": {"type": "string"}},
        "countries": {"type": "array", "items": {"type": "string"}},
        "regions": {"type": "array", "items": {"type": "string"}},
        "employee_min": {"type": ["integer", "null"]},
        "employee_max": {"type": ["integer", "null"]},
        "revenue_min_usd": {"type": ["integer", "null"]},
        "revenue_max_usd": {"type": ["integer", "null"]},
        "buyer_personas": {"type": "array", "items": {"type": "string"}},
        "buying_signals": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "excluded_keywords": {"type": "array", "items": {"type": "string"}},
        "tech_stack_required": {"type": "array", "items": {"type": "string"}},
        "tech_stack_excluded": {"type": "array", "items": {"type": "string"}},
        "weights": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "hiring": {"type": "number"},
                "funding": {"type": "number"},
                "growth": {"type": "number"},
                "product_launch": {"type": "number"},
                "tech_install": {"type": "number"},
                "leadership_change": {"type": "number"},
                "partnership": {"type": "number"},
                "news": {"type": "number"},
                "traffic_growth": {"type": "number"},
                "office_expansion": {"type": "number"},
            },
            "required": [
                "hiring", "funding", "growth", "product_launch", "tech_install",
                "leadership_change", "partnership", "news", "traffic_growth",
                "office_expansion",
            ],
        },
    },
    "required": [
        "name", "summary", "industries", "sub_industries", "countries", "regions",
        "employee_min", "employee_max", "revenue_min_usd", "revenue_max_usd",
        "buyer_personas", "buying_signals", "keywords", "excluded_keywords",
        "tech_stack_required", "tech_stack_excluded", "weights",
    ],
}


SIGNALS_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "hiring", "funding", "growth", "product_launch", "tech_install",
                            "leadership_change", "partnership", "news", "traffic_growth",
                            "office_expansion",
                        ],
                    },
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "number"},
                    "confidence": {"type": "number"},
                    "observed_at": {"type": ["string", "null"]},
                    "url": {"type": ["string", "null"]},
                },
                "required": [
                    "kind", "label", "description", "severity", "confidence",
                    "observed_at", "url",
                ],
            },
        }
    },
    "required": ["signals"],
}


OPPORTUNITY_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "probability": {"type": "number"},
        "why_now": {"type": "array", "items": {"type": "string"}},
        "pain_points": {"type": "array", "items": {"type": "string"}},
        "suggested_contact_title": {"type": "string"},
        "suggested_offer": {"type": "string"},
        "talking_points": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "probability", "why_now", "pain_points", "suggested_contact_title",
        "suggested_offer", "talking_points", "risks",
    ],
}


SCORING_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fit_score": {"type": "integer"},
        "funding_score": {"type": "integer"},
        "hiring_score": {"type": "integer"},
        "growth_score": {"type": "integer"},
        "tech_match_score": {"type": "integer"},
        "email_score": {"type": "integer"},
        "activity_score": {"type": "integer"},
        "reasoning": {"type": "array", "items": {"type": "string"}},
        "probability": {"type": "number"},
    },
    "required": [
        "fit_score", "funding_score", "hiring_score", "growth_score",
        "tech_match_score", "email_score", "activity_score", "reasoning",
        "probability",
    ],
}


OUTREACH_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["subject", "body"],
            },
        }
    },
    "required": ["variants"],
}
