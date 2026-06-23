import pytest
from pydantic import ValidationError

from app.schemas.company import CompanyCreate
from app.services.scraper import url_is_safe


# ---- SSRF guard ----------------------------------------------------------

def test_url_is_safe_rejects_internal_and_metadata():
    assert not url_is_safe("http://localhost/")
    assert not url_is_safe("http://127.0.0.1/")
    assert not url_is_safe("http://169.254.169.254/latest/meta-data/")
    assert not url_is_safe("http://10.0.0.5/")
    assert not url_is_safe("http://192.168.1.1/")
    assert not url_is_safe("http://[::1]/")
    assert not url_is_safe("http://redis:6379/")
    assert not url_is_safe("http://metadata.google.internal/")


def test_url_is_safe_rejects_bad_schemes():
    assert not url_is_safe("file:///etc/passwd")
    assert not url_is_safe("gopher://internal/")
    assert not url_is_safe("ftp://x/")


def test_url_is_safe_allows_public_domains():
    # These resolve to public IPs.
    assert url_is_safe("https://example.com/")
    assert url_is_safe("https://www.google.com/")


# ---- domain input validation --------------------------------------------

def test_company_create_rejects_ip_and_internal_domains():
    for bad in ["127.0.0.1", "localhost", "10.0.0.1", "redis", "192.168.0.5"]:
        with pytest.raises(ValidationError):
            CompanyCreate(name="X", domain=bad)


def test_company_create_accepts_real_domain():
    c = CompanyCreate(name="Acme", domain="https://www.acme.io/about")
    assert c.domain == "acme.io"  # normalized: scheme + path stripped
    c2 = CompanyCreate(name="Acme", domain="Acme.IO")
    assert c2.domain == "acme.io"
