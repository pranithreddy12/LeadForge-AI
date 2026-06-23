from app.services.discovery import _domain_from_url, _is_excluded, _normalize_name


def test_domain_from_url():
    assert _domain_from_url("https://www.acme.io/about") == "acme.io"
    assert _domain_from_url("acme.io") == "acme.io"
    assert _domain_from_url("") is None


def test_is_excluded():
    assert _is_excluded("linkedin.com")
    assert _is_excluded("uk.linkedin.com")
    assert not _is_excluded("acme.io")


def test_normalize_name():
    assert _normalize_name("Acme Corp - Leading widgets") == "Acme Corp"
    assert _normalize_name("Acme | Home") == "Acme"
    assert _normalize_name("  spaced   name  ") == "spaced name"
