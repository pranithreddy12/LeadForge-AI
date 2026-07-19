"""Local-fit scoring for SMBs (med spas, clinics, salons...) discovered via Places.

The B2B scorer grades on employee band / funding / hiring, which local businesses don't
have -> everything came out F. This grades against the ICP the user defined:

  ICP FIT  - does the lead match the ICP?  target VERTICAL (industries/keywords) +
             target GEOGRAPHY (countries / locations)
  NEED FIT - do they need the offer?  no online booking (core), reachable, demand
             (review count vs Settings.min_reviews)
  PAIN     - do they show the problem?  missed-call / slow-response / low-rating signals

Every point cites a real, checkable fact.
"""
from __future__ import annotations

import re


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _is_mobile(phone: str | None) -> bool:
    """True ONLY when the number is provably a mobile line (the precondition for
    WhatsApp). Unknown country / landline / undeterminable -> False, because asserting
    reachability we haven't checked is what made the old 'WhatsApp-reachable' bullet
    false on landlines. Note: many countries (US/CA) do not encode mobile in the
    number at all, so we correctly return False there rather than guess."""
    if not phone:
        return False
    d = re.sub(r"\D", "", str(phone))
    if not d:
        return False
    rules = (
        ("971", lambda n: n.startswith("5")),          # UAE mobiles: +971 5x
        ("966", lambda n: n.startswith("5")),          # KSA
        ("974", lambda n: n[:1] in "3567"),            # Qatar
        ("973", lambda n: n[:1] in "36"),              # Bahrain
        ("968", lambda n: n[:1] in "79"),              # Oman
        ("965", lambda n: n[:1] in "569"),             # Kuwait
        ("91",  lambda n: n[:1] in "6789"),            # India
        ("44",  lambda n: n.startswith("7")),          # UK
        ("61",  lambda n: n.startswith("4")),          # Australia
    )
    for cc, is_mob in rules:
        if d.startswith(cc):
            return bool(is_mob(d[len(cc):]))
    return False   # unknown plan (incl. US/CA) -> do not claim


def suggest_local_opportunity(signal_kinds: list[str] | None,
                              services: str | None = None,
                              *, decision_maker: str | None = None) -> dict:
    """Who to reach + what to offer, for a local business. Grounded, not invented:
    the target is the owner/manager (they decide, not the front desk), and the offer is
    the seller's REAL primary service tied to the specific problem signal we detected.
    Returns {"suggested_contact_title": str, "suggested_offer": str}."""
    kinds = set(signal_kinds or [])

    # Who: the buyer is the owner/manager. If we know the doctor/owner name, name them.
    title = "Owner / Clinic Manager"
    if decision_maker:
        title = f"{decision_maker} (owner/decision-maker)"

    # What: our real primary service (first configured), phrased to the problem we saw.
    items = [s.strip() for s in (services or "").replace(";", ",").split(",") if s.strip()]
    primary = items[0] if items else "AI receptionist"
    if "no_online_booking" in kinds:
        angle = "no online booking yet, so enquiries rely on calls/WhatsApp - capture and book those automatically"
    elif "missed_calls_complaint" in kinds:
        angle = "reviews mention missed calls - answer and book them so none slip"
    elif "slow_response_complaint" in kinds:
        angle = "reviews mention slow responses - reply instantly and book, 24/7"
    elif "limited_hours" in kinds:
        angle = "closed part of the week - catch after-hours WhatsApp enquiries and book them"
    elif "low_rating" in kinds:
        angle = "recover missed enquiries and nudge happy clients for reviews"
    else:
        angle = "answer WhatsApp and missed calls 24/7 and book consultations automatically"
    offer = f"Free 7-day pilot of {primary}: {angle}."
    return {"suggested_contact_title": title, "suggested_offer": offer}


def _grade(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def score_local_fit(*, company_name: str | None = None, industry: str | None = None,
                    places: dict | None = None, signal_kinds: list[str] | None = None,
                    icp_terms: list[str] | None = None, icp_geos: list[str] | None = None,
                    min_reviews: int = 10) -> dict:
    """Return {score, grade, fit_score, pain_score, probability, reasoning[]}.

    icp_terms = the ICP's target vertical terms (industries + keywords).
    icp_geos  = the ICP's target geography (countries + target_locations).
    """
    kinds = set(signal_kinds or [])
    places = places or {}
    reasons: list[str] = []

    # ---- ICP FIT (does this lead match the ICP the user configured?) --------
    # Match on the ICP's distinctive VERTICAL KEYWORDS (spa, clinic, aesthetic, skin,
    # laser, dental...), not the exact multi-word phrase -- so "Armonia Spa" matches a
    # "med spa" ICP. Generic filler words are dropped.
    _STOP = {"and", "the", "for", "med", "of", "in", "business", "service", "services",
             "center", "centre", "co", "llc"}
    icp_fit = 0
    kw: set[str] = set()
    for t in (icp_terms or []):
        for w in _norm(t).split():
            if len(w) >= 3 and w not in _STOP:
                kw.add(w)
    haystack = _norm(f"{company_name or ''} {industry or ''} {places.get('type') or ''}")
    if kw:
        if any(w in haystack for w in kw):
            icp_fit += 20
            reasons.append("Matches your ICP vertical")
        else:
            reasons.append("Outside your ICP vertical (no vertical match)")
    else:
        icp_fit += 12  # no vertical configured -> neutral benefit of the doubt

    geos = [_norm(g) for g in (icp_geos or []) if _norm(g)]
    addr = _norm(f"{places.get('address') or ''} {places.get('formatted_address') or ''}")
    if geos:
        if any(g in addr for g in geos):
            icp_fit += 10
            reasons.append("In your target geography")
        else:
            reasons.append("Outside your target geography")
    else:
        icp_fit += 6

    # ---- NEED FIT (do they need the AI receptionist?) -----------------------
    need = 0
    if "no_online_booking" in kinds:
        need += 25
        reasons.append("No online booking, enquiries rely on calls/DMs (core fit)")
    phone = places.get("phone") or places.get("phone_intl")
    if phone:
        need += 8
        reasons.append("Has a phone line to reach")
    # AUDIT C5: the old bullet claimed "WhatsApp-reachable" purely because Google
    # returns an international-format number for EVERY business — zero WhatsApp
    # verification. That is false for landlines (a Dubai 04 / a US 512 line is almost
    # never on WhatsApp). We can't verify WhatsApp registration without the Business
    # API, so we only note a MOBILE number (the necessary precondition) and say so.
    if _is_mobile(places.get("phone_intl") or places.get("phone")):
        need += 4
        reasons.append("Mobile number listed (may be WhatsApp-reachable — unverified)")

    rc = int(places.get("review_count") or 0)
    base = max(1, int(min_reviews or 10))
    # AUDIT C6: the review COUNT is a real Places fact; "more reviews => more missed
    # enquiries" is a HYPOTHESIS, not a measured fact. Phrase it as one.
    if rc >= base * 10:
        need += 15
        reasons.append(f"High demand ({rc} reviews) — likely more enquiries than staff can catch")
    elif rc >= base * 3:
        need += 10
        reasons.append(f"Solid demand ({rc} reviews)")
    elif rc >= base:
        need += 5
        reasons.append(f"Established ({rc} reviews)")

    # ---- PAIN (do they visibly have the problem?) ---------------------------
    pain = 0
    if "missed_calls_complaint" in kinds:
        pain += 12
        reasons.append("Reviews mention missed/unanswered calls")
    if "slow_response_complaint" in kinds:
        pain += 6
        reasons.append("Reviews mention slow response / wait times")
    if "low_rating" in kinds:
        pain += 4
        reasons.append("Below-4.0 rating suggests service gaps")
    if "limited_hours" in kinds:
        pain += 6
        # AUDIT C7: stated as the observation it is, not a claimed outcome.
        reasons.append("Closed days / early close in their Google hours — enquiries then have nowhere to go")

    score = min(100, icp_fit + need + pain)
    if not reasons:
        reasons.append("Local business; limited signal data")
    return {
        "score": score,
        "grade": _grade(score),
        "fit_score": min(100, icp_fit + need),
        "pain_score": min(100, pain),
        "probability": round(score / 100, 2),
        "reasoning": reasons,
    }
