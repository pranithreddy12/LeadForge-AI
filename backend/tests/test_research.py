from app.ai.openai_client import _demo_for_schema
from app.services.research import _safe_http_url


def test_demo_research_signals_unavailable_not_empty_brief():
    """Nothing-static: in demo mode the research schema must signal provider
    unavailable so the caller persists NOTHING (not a hollow row)."""
    out = _demo_for_schema("AccountResearch", "irrelevant")
    assert out.get("_provider_error") is True
    # and it must NOT look like a usable brief
    assert "summary" not in out


def test_demo_known_schemas_still_return_fixtures():
    assert "industries" in _demo_for_schema("ICP", "we sell QA services")
    assert "signals" in _demo_for_schema("Signals", "Company: Acme")
    assert "variants" in _demo_for_schema("Outreach", "x")


def test_safe_http_url():
    assert _safe_http_url("https://example.com/news/1")
    assert _safe_http_url("http://acme.io")
    assert not _safe_http_url("javascript:alert(1)")
    assert not _safe_http_url("data:text/html,x")
    assert not _safe_http_url("file:///etc/passwd")
    assert not _safe_http_url(None)
    assert not _safe_http_url("")
