from app.ai.enrichment_engine import employee_range_for, revenue_range_for
from app.services.techstack import detect_tech, product_names, tech_to_signals


def test_detect_tech_from_html():
    html = """
    <script src="https://js.hs-scripts.com/1.js"></script>
    <script src="https://static.zdassets.com/w.js"></script>
    <script src="https://js.stripe.com/v3/"></script>
    <link href="https://cdn.shopify.com/x.css">
    """
    tech = detect_tech(html)
    names = product_names(tech)
    assert "HubSpot" in names
    assert "Zendesk" in names
    assert "Stripe" in names
    assert "Shopify" in names


def test_detect_tech_empty():
    assert detect_tech("") == []
    assert detect_tech("<html><body>nothing</body></html>") == []


def test_tech_to_signals_only_budget_products():
    tech = [{"product": "HubSpot", "category": "crm"},
            {"product": "Google Tag Manager", "category": "analytics"}]
    sigs = tech_to_signals(tech)
    labels = [s["label"] for s in sigs]
    assert "HubSpot installed" in labels
    # GTM is not a budget-signal product
    assert not any("Google Tag Manager" in label for label in labels)
    for s in sigs:
        assert s["kind"] == "tech_install"
        assert s["source"] == "techstack"


def test_employee_range_bands():
    assert employee_range_for(5) == "1-10"
    assert employee_range_for(120) == "51-200"
    assert employee_range_for(450) == "201-500"
    assert employee_range_for(None) is None


def test_revenue_range_bands():
    assert revenue_range_for(500_000) == "<$1M"
    assert revenue_range_for(5_000_000) == "$1M-$10M"
    assert revenue_range_for(250_000_000) == "$100M-$500M"
    assert revenue_range_for(None) is None
