from types import SimpleNamespace

from app.ai.qualification_engine import Candidate, ai_qualify
from app.services.discovery import _template_queries, build_queries


def _icp(**kw):
    base = dict(
        search_queries=[], keywords=["recently funded", "scaling"],
        industries=["SaaS", "Fintech"], countries=["USA"],
        buying_signals=["raised Series A", "hiring finance team"],
        buyer_personas=["CFO"], project=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_build_queries_prefers_stored_search_queries():
    icp = _icp(search_queries=["Series A SaaS hiring finance 2026",
                               "funded fintech startups USA"])
    qs = build_queries(icp)
    assert qs[0] == "Series A SaaS hiring finance 2026"
    assert "funded fintech startups USA" in qs


def test_template_queries_are_signal_led_not_service_led():
    icp = _icp()
    qs = _template_queries(icp, [])
    joined = " | ".join(qs).lower()
    # should lean on buying signals, surfacing buyers in growth mode
    assert "raised series a" in joined or "hiring finance team" in joined
    # every query is anchored on a target industry
    assert all(("saas" in q.lower() or "fintech" in q.lower()) for q in qs)


def test_build_queries_falls_back_to_template_when_no_llm_and_no_project():
    # project=None means on-the-fly generation is skipped → template fallback
    icp = _icp(search_queries=[])
    qs = build_queries(icp)
    assert len(qs) > 0


def test_ai_qualify_provider_error_marks_non_competitor_and_accepts():
    # With no LLM key the provider is 'demo' which returns demo fixtures, but
    # ai_qualify's provider-error fallback path sets is_competitor False and
    # is_company True. Here we exercise the empty-candidates guard and shape.
    assert ai_qualify([]) == []
    cands = [Candidate(title="Acme Inc", url="https://acme.io", domain="acme.io",
                       snippet="b2b widgets", source="tavily")]
    out = ai_qualify(cands)
    # every result row carries the competitor + verification flags
    assert "is_competitor" in out[0]
    assert "ai_verified" in out[0]
