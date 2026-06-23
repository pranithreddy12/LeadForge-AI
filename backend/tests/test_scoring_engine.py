from app.ai.scoring_engine import (
    DEFAULT_WEIGHTS,
    ScoreInput,
    _heuristic_subscores,
    _weighted_total,
    grade_for,
)


def test_grade_for_bands():
    assert grade_for(95) == "A+"
    assert grade_for(85) == "A"
    assert grade_for(72) == "B"
    assert grade_for(60) == "C"
    assert grade_for(45) == "D"
    assert grade_for(10) == "F"


def test_heuristic_subscores_basic():
    icp = {
        "industries": ["SaaS"],
        "employee_min": 50, "employee_max": 500,
        "countries": ["USA"],
        "tech_stack_required": ["Salesforce"],
        "tech_stack_excluded": ["Oracle"],
    }
    company = {
        "industry": "SaaS", "employee_count": 100, "country": "USA",
        "tech_stack": ["Salesforce", "AWS"],
    }
    signals = [
        {"kind": "hiring", "severity": 0.8, "confidence": 0.9},
        {"kind": "funding", "severity": 0.9, "confidence": 0.95},
    ]
    contacts = [{"email_status": "valid"}]
    sub = _heuristic_subscores(ScoreInput(icp=icp, company=company,
                                          signals=signals, contacts=contacts))
    assert sub["fit_score"] >= 90
    assert sub["funding_score"] > 0
    assert sub["hiring_score"] > 0
    assert sub["tech_match_score"] >= 60


def test_weighted_total_bounded():
    sub = {
        "fit_score": 100, "funding_score": 100, "hiring_score": 100,
        "growth_score": 100, "tech_match_score": 100, "email_score": 100,
        "activity_score": 100,
    }
    assert _weighted_total(sub, None) == 100
    assert _weighted_total({k: 0 for k in sub}, DEFAULT_WEIGHTS) == 0
