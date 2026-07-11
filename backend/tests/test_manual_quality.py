"""Quality fixes: signal attribution, booking-link CTA, spam flags, decision-maker
name cleaning."""
import types

from app.ai.outreach_engine import cta_instruction, humanize
from app.services.presend import spam_flags
from app.services.signals import signal_attribution_ok
from app.services.scraper import scrape_decision_makers  # noqa: F401 (import smoke)


def _company(domain, name):
    return types.SimpleNamespace(domain=domain, name=name)


# ---- F1: signal attribution (source URL, never the LLM description) ----

def test_attribution_domain_match():
    c = _company("myaustindds.com", "38th Street Dental")
    assert signal_attribution_ok(c, url="https://myaustindds.com/services") is True


def test_attribution_rejects_other_entity_even_if_named_in_description():
    c = _company("myaustindds.com", "38th Street Dental")
    # ada.org article that mentions "practices like 38th Street Dental" -> still dropped,
    # because attribution is judged on the SOURCE url, not the LLM description.
    assert signal_attribution_ok(
        c, url="https://adanews.ada.org/federal-funding",
        description="...may create opportunities for practices like 38th Street Dental.") is False


def test_attribution_rejects_competitor_funding():
    c = _company("austindentalworks.com", "Austin Dental Works")
    assert signal_attribution_ok(c, url="https://techcrunch.com/archy-raises-20m",
                                 label="Archy raises $20M Series B") is False


# ---- F2: booking-link CTA ----

def test_cta_with_link():
    out = cta_instruction("https://cal.com/me/15min")
    assert "cal.com/me/15min" in out and "book" in out.lower()


def test_cta_without_link_forbids_booking():
    out = cta_instruction(None)
    assert "reply" in out.lower() and "book a slot" in out.lower()  # instruction forbids it


# ---- F5: spam-phrase flags ----

def test_spam_flags_detects_phrases_and_caps():
    flags = spam_flags("ACT NOW!!! You will NEVER miss again. Guaranteed FREE results!")
    joined = " ".join(flags).lower()
    assert "exclamation" in joined
    assert "never miss again" in joined
    assert "guarantee" in joined
    assert "all-caps" in joined


def test_spam_flags_clean_draft():
    assert spam_flags("Hi Dr. Smith, we noticed a few missed calls in your reviews. "
                      "Worth a quick chat? Reply anytime.") == []


# ---- humanize still strips em-dashes (regression) ----

def test_humanize_regression():
    assert "—" not in humanize("Great—let's talk")
