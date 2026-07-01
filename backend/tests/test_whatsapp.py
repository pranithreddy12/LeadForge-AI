"""Section 1 — WhatsApp outreach: phone normalization + problem-aware message
generation (LLM path, deterministic fallback, char cap, buzzword guard)."""
import app.ai.outreach_engine as oe
from app.ai.outreach_engine import (WHATSAPP_MAX_CHARS, generate_whatsapp_message,
                                    humanize)
from app.services.whatsapp_sender import normalize_phone


# ---- AI-tell punctuation (em/en dashes) stripping ----

def test_humanize_strips_em_dash():
    assert "—" not in humanize("Got it—missed calls are costing you.")
    assert humanize("Got it — missed calls hurt.") == "Got it, missed calls hurt."
    assert humanize("answers calls 24/7—no extra software") == "answers calls 24/7, no extra software"


def test_humanize_en_dash_to_hyphen():
    assert humanize("Cost is $200–300/mo") == "Cost is $200-300/mo"


def test_humanize_noop_on_clean_text():
    assert humanize("Plain human text, no dashes.") == "Plain human text, no dashes."


def test_generated_message_has_no_em_dash(monkeypatch):
    monkeypatch.setattr(oe, "complete_json",
                        lambda **k: {"message": "Hi Glow Med Spa—we saw missed calls. Quick call? - Sam"})
    out = generate_whatsapp_message(_COMPANY, _SIGNALS, {"sender_name": "Sam"})
    assert "—" not in out["message"] and "–" not in out["message"]


# ---- phone normalization (E.164) ----

def test_us_10_digit_gets_plus1():
    assert normalize_phone("214-555-9876") == "+12145559876"
    assert normalize_phone("(214) 555 9876") == "+12145559876"


def test_us_11_digit_leading_one():
    assert normalize_phone("1-214-555-9876") == "+12145559876"


def test_already_international_kept():
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"


def test_international_without_plus_meta_wa_id():
    # Meta sends the inbound `from`/wa_id as bare digits (no '+'); must still match.
    assert normalize_phone("919014150785") == "+919014150785"   # India
    assert normalize_phone("442079460958") == "+442079460958"   # UK


def test_invalid_numbers_skipped():
    assert normalize_phone("555-1234") is None        # too short, no country code
    assert normalize_phone("not a phone") is None     # non-numeric
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


# ---- message generation ----

_COMPANY = {
    "name": "Glow Med Spa",
    "raw": {"places": {"address": "1880 Oak Lawn Ave, Dallas, TX 75207",
                       "rating": 3.7, "review_count": 48}},
}
_SIGNALS = [
    {"kind": "missed_calls_complaint", "label": "6 reviews mention missed calls", "severity": 0.85},
    {"kind": "low_rating", "label": "Google rating 3.7 (below 4.0)", "severity": 0.4},
]


def test_llm_message_used_when_valid(monkeypatch):
    monkeypatch.setattr(oe, "complete_json",
                        lambda **k: {"message": "Hi Glow Med Spa in Dallas, "
                                     "we saw missed calls. Quick call? - Sam"})
    out = generate_whatsapp_message(_COMPANY, _SIGNALS, {"sender_name": "Sam"})
    assert out["source"] == "llm"
    assert "Glow Med Spa" in out["message"]


def test_fallback_on_provider_error_is_real_data(monkeypatch):
    monkeypatch.setattr(oe, "complete_json", lambda **k: {"_provider_error": True})
    out = generate_whatsapp_message(_COMPANY, _SIGNALS, {"sender_name": "Sam"})
    assert out["source"] == "template"
    # Most-severe-first: missed-calls phrasing, never invented data.
    assert "reach you by phone" in out["message"]
    assert "Glow Med Spa" in out["message"]
    assert len(out["message"]) <= WHATSAPP_MAX_CHARS


def test_buzzword_draft_rejected_for_template(monkeypatch):
    monkeypatch.setattr(oe, "complete_json",
                        lambda **k: {"message": "Our revolutionary game-changing AI!"})
    out = generate_whatsapp_message(_COMPANY, _SIGNALS, {"sender_name": "Sam"})
    assert out["source"] == "template"   # buzzword draft rejected


def test_over_limit_draft_rejected_for_template(monkeypatch):
    monkeypatch.setattr(oe, "complete_json", lambda **k: {"message": "x" * 600})
    out = generate_whatsapp_message(_COMPANY, _SIGNALS, {"sender_name": "Sam"})
    assert out["source"] == "template"
    assert len(out["message"]) <= WHATSAPP_MAX_CHARS


def test_low_rating_only_cites_real_rating(monkeypatch):
    monkeypatch.setattr(oe, "complete_json", lambda **k: {"_provider_error": True})
    company = {"name": "Tooth Co", "raw": {"places": {"address": "5 Main St, Austin, TX 70000",
                                                      "rating": 3.5}}}
    out = generate_whatsapp_message(company, [{"kind": "low_rating", "severity": 0.4}],
                                    {"sender_name": "Sam"})
    assert "3.5 stars" in out["message"]
