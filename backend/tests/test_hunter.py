"""Section 3 — Hunter.io domain search: key guards + parsing/sorting."""
import app.services.hunter as hunter


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


def test_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(hunter.settings, "hunter_api_key", "")
    assert hunter.find_email("acme.com", "Acme") == []


def test_placeholder_key_treated_as_unconfigured(monkeypatch):
    # The demo .env value "xxx" must NOT fire a (doomed) API call.
    called = {"hit": False}
    monkeypatch.setattr(hunter.httpx, "get",
                        lambda *a, **k: called.__setitem__("hit", True))
    assert hunter.find_email("acme.com", "Acme", api_key="xxx") == []
    assert called["hit"] is False


def test_parses_and_sorts_by_confidence(monkeypatch):
    payload = {"data": {"emails": [
        {"value": "low@acme.com", "first_name": "Lo", "last_name": "W",
         "position": "Manager", "confidence": 40},
        {"value": "ceo@acme.com", "first_name": "Ada", "last_name": "L< >",
         "position": "CEO", "confidence": 95},
    ]}}
    monkeypatch.setattr(hunter.httpx, "get", lambda *a, **k: _Resp(200, payload))
    out = hunter.find_email("acme.com", "Acme", api_key="a-real-looking-key-1234567890")
    assert [e["email"] for e in out] == ["ceo@acme.com", "low@acme.com"]  # sorted desc
    assert out[0]["confidence"] == 95
    assert out[0]["position"] == "CEO"


def test_429_returns_empty(monkeypatch):
    monkeypatch.setattr(hunter.httpx, "get", lambda *a, **k: _Resp(429, {"e": 1}))
    assert hunter.find_email("acme.com", api_key="a-real-looking-key-1234567890") == []


def test_api_error_returns_empty(monkeypatch):
    monkeypatch.setattr(hunter.httpx, "get", lambda *a, **k: _Resp(401, {"e": 1}))
    assert hunter.find_email("acme.com", api_key="a-real-looking-key-1234567890") == []


def test_request_exception_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(hunter.httpx, "get", boom)
    assert hunter.find_email("acme.com", api_key="a-real-looking-key-1234567890") == []
