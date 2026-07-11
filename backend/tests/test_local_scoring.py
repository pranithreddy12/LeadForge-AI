"""Local-fit scoring: SMBs graded AGAINST the ICP (vertical + geography) plus
need-fit (no online booking, demand) and pain signals."""
from app.services.local_scoring import score_local_fit

_ICP_TERMS = ["med spa", "medical spa", "aesthetic clinic", "spa"]
_ICP_GEOS = ["United Arab Emirates", "Dubai"]


def _score(**kw):
    kw.setdefault("icp_terms", _ICP_TERMS)
    kw.setdefault("icp_geos", _ICP_GEOS)
    return score_local_fit(**kw)


def test_on_icp_great_fit_scores_high():
    r = _score(
        company_name="Glow Med Spa", industry="Medical Spa",
        places={"phone_intl": "+9714 1", "address": "Dubai Marina, Dubai, UAE",
                "review_count": 900, "type": "spa"},
        signal_kinds=["no_online_booking", "missed_calls_complaint"], min_reviews=10)
    assert r["score"] >= 80 and r["grade"] in ("A", "A+")


def test_off_icp_vertical_scores_lower():
    # Same offer-fit, but NOT the ICP vertical (a restaurant) -> loses the vertical points.
    on = _score(company_name="Glow Med Spa", industry="Medical Spa",
                places={"phone_intl": "+9714 1", "address": "Dubai, UAE", "review_count": 900,
                        "type": "spa"},
                signal_kinds=["no_online_booking"], min_reviews=10)
    off = _score(company_name="Mario's Pizzeria", industry="Restaurant",
                 places={"phone_intl": "+9714 1", "address": "Dubai, UAE", "review_count": 900,
                         "type": "restaurant"},
                 signal_kinds=["no_online_booking"], min_reviews=10)
    assert off["score"] < on["score"]


def test_off_geography_scores_lower():
    on = _score(company_name="Glow Med Spa", industry="Medical Spa",
                places={"address": "Dubai, UAE", "review_count": 500, "type": "spa"},
                signal_kinds=["no_online_booking"], min_reviews=10)
    off = _score(company_name="Glow Med Spa", industry="Medical Spa",
                 places={"address": "London, UK", "review_count": 500, "type": "spa"},
                 signal_kinds=["no_online_booking"], min_reviews=10)
    assert off["score"] < on["score"]


def test_already_has_booking_scores_lower():
    booking = _score(company_name="Glow Med Spa", industry="Medical Spa",
                     places={"address": "Dubai, UAE", "review_count": 40, "type": "spa"},
                     signal_kinds=[], min_reviews=10)
    no_booking = _score(company_name="Glow Med Spa", industry="Medical Spa",
                        places={"address": "Dubai, UAE", "review_count": 40, "type": "spa"},
                        signal_kinds=["no_online_booking"], min_reviews=10)
    assert booking["score"] < no_booking["score"]


def test_reasons_cite_icp_and_offer():
    r = _score(company_name="Glow Med Spa", industry="Medical Spa",
               places={"address": "Dubai, UAE", "review_count": 500, "type": "spa"},
               signal_kinds=["no_online_booking"], min_reviews=10)
    joined = " ".join(r["reasoning"]).lower()
    assert "icp vertical" in joined and "online booking" in joined
