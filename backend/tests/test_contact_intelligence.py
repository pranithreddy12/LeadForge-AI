from app.services.contact_intelligence import compute_influence
from app.services.contacts import _seniority_for


def test_seniority_for_word_boundaries():
    assert _seniority_for("Chief Technology Officer") == "cxo"
    assert _seniority_for("CFO") == "cxo"
    # 'chief' substring traps
    assert _seniority_for("Chief of Staff") == "manager"
    assert _seniority_for("Executive Assistant") == "manager"
    # 'lead' substring traps
    assert _seniority_for("Lead Generation Specialist") == "ic"
    assert _seniority_for("Tech Lead") == "manager"
    # real roles
    assert _seniority_for("VP of Sales") == "vp"
    assert _seniority_for("Software Engineer") == "ic"


def test_cxo_is_top_decision_maker():
    score, bp = compute_influence(title="Chief Technology Officer", seniority="cxo",
                                  department="engineering", buyer_personas=["CTO"])
    assert score >= 90
    assert bp == "decision_maker"


def test_founder_always_top():
    score, bp = compute_influence(title="Co-Founder & CEO", seniority="cxo",
                                  department="leadership", buyer_personas=[])
    assert score >= 95
    assert bp == "decision_maker"


def test_ic_is_end_user_low_influence():
    score, bp = compute_influence(title="Software Engineer", seniority="ic",
                                  department="engineering", buyer_personas=[])
    assert score < 40
    assert bp == "end_user"


def test_manager_is_evaluator():
    score, bp = compute_influence(title="Engineering Manager", seniority="manager",
                                  department="engineering", buyer_personas=["CTO"])
    assert bp == "evaluator"
    assert 40 <= score <= 65


def test_procurement_is_gatekeeper():
    _, bp = compute_influence(title="Procurement Manager", seniority="manager",
                              department="operations", buyer_personas=[])
    assert bp == "gatekeeper"


def test_persona_match_boosts_score():
    base, _ = compute_influence(title="VP of Engineering", seniority="vp",
                                department="engineering", buyer_personas=[])
    boosted, _ = compute_influence(title="VP of Engineering", seniority="vp",
                                   department="engineering", buyer_personas=["VP Engineering"])
    assert boosted > base


def test_score_always_bounded():
    for sev in ("cxo", "vp", "director", "manager", "ic", "unknown", None):
        s, bp = compute_influence(title="X", seniority=sev, department=None,
                                  buyer_personas=["X"])
        assert 0 <= s <= 100
        assert bp in {"decision_maker", "influencer", "gatekeeper", "evaluator", "end_user"}


# ---- regression guards from the adversarial review (false positives) --------

def test_vice_president_not_treated_as_founder():
    # 'president' inside 'Vice President' must NOT force founder 95/decision_maker
    s, bp = compute_influence(title="Vice President of Marketing", seniority="vp",
                              department="marketing", buyer_personas=[])
    assert s < 90
    assert bp == "influencer"


def test_product_owner_not_founder():
    s, bp = compute_influence(title="Product Owner", seniority="ic",
                              department="engineering", buyer_personas=[])
    assert s < 60
    assert bp == "end_user"


def test_executive_assistant_to_ceo_is_gatekeeper_not_decision_maker():
    s, bp = compute_influence(title="Executive Assistant to the CEO", seniority="manager",
                              department=None, buyer_personas=["CEO"])
    assert bp == "gatekeeper"
    assert s < 90  # not founder-elevated


def test_persona_boost_word_boundary_not_substring():
    # persona 'VP' must not bare-substring-match unrelated text, and 'CEO' must
    # not match inside 'CEO' fragments of an assistant title
    base, _ = compute_influence(title="Director of Operations", seniority="director",
                                department="operations", buyer_personas=["VP"])
    assert base < 70  # no spurious +12 from 'vp' substring

    # a true whole-word persona match still boosts
    boosted, _ = compute_influence(title="VP Sales", seniority="vp",
                                   department="sales", buyer_personas=["VP Sales"])
    plain, _ = compute_influence(title="VP Sales", seniority="vp",
                                 department="sales", buyer_personas=[])
    assert boosted > plain


def test_cxo_title_with_wrong_seniority_still_elevated():
    # CTO passed with a mistaken seniority='ic' must still score as exec
    s, bp = compute_influence(title="Chief Technology Officer", seniority="ic",
                              department="engineering", buyer_personas=[])
    assert s >= 90
    assert bp == "decision_maker"
