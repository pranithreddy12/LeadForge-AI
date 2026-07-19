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

import math
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


def _demand_points(review_count: int) -> int:
    """Map Google review_count -> 0..38 on a smooth log curve. Reviews are the one fact
    with real spread across local leads (15 .. ~4000), so this is our main separator:
    more reviews = more enquiry volume = more that a busy front desk can miss.
      ~15 -> ~3   ~100 -> ~16   ~500 -> ~27   ~1000 -> ~32   3000+ -> 38
    """
    if review_count <= 0:
        return 0
    return max(0, min(38, round((math.log10(review_count) - 1.0) * 16)))


def score_local_fit(*, company_name: str | None = None, industry: str | None = None,
                    places: dict | None = None, signal_kinds: list[str] | None = None,
                    icp_terms: list[str] | None = None, icp_geos: list[str] | None = None,
                    min_reviews: int = 10,
                    has_website: bool = False, has_instagram: bool = False) -> dict:
    """Score a local business 0-100 on how much it needs (and can be reached about) an AI
    receptionist. Built ONLY on facts we can actually observe for every lead, so scores
    spread into a real ranking instead of clustering:

      FIT (0-25)    - matches the ICP vertical + geography you configured
      DEMAND (0-38) - Google review_count on a log curve (our main separator)
      NEED (0-28)   - no online booking (+20) / limited opening hours (+8)
      REACH (0-23)  - Instagram (owner-run, reachable), no website, mobile line
      QUALITY (0-10)- rating position INSIDE the 4-5 band (lower = more service gaps)

    We deliberately do NOT score review-text pain signals (missed/slow-response) or a
    sub-4.0 rating: Google gates review text behind a paid SKU we don't call, and curated
    med-spas never fall below 4.0, so those dimensions were dead weight that flattened
    every score. icp_terms/icp_geos come from the ICP; has_website/has_instagram from the
    company's scraped socials.
    """
    kinds = set(signal_kinds or [])
    places = places or {}
    reasons: list[str] = []

    # ---- FIT: matches the ICP the user configured? (kept small so it separates, not
    #      dominates -- nearly every discovered lead is a target spa in the target city) -
    _STOP = {"and", "the", "for", "med", "of", "in", "business", "service", "services",
             "center", "centre", "co", "llc"}
    fit = 0
    kw: set[str] = set()
    for t in (icp_terms or []):
        for w in _norm(t).split():
            if len(w) >= 3 and w not in _STOP:
                kw.add(w)
    haystack = _norm(f"{company_name or ''} {industry or ''} {places.get('type') or ''}")
    if kw:
        if any(w in haystack for w in kw):
            fit += 15
            reasons.append("Matches your ICP vertical")
        else:
            reasons.append("Outside your ICP vertical (no vertical match)")
    else:
        fit += 9  # no vertical configured -> neutral benefit of the doubt

    geos = [_norm(g) for g in (icp_geos or []) if _norm(g)]
    addr = _norm(f"{places.get('address') or ''} {places.get('formatted_address') or ''}")
    if geos:
        if any(g in addr for g in geos):
            fit += 10
            reasons.append("In your target geography")
        else:
            reasons.append("Outside your target geography")
    else:
        fit += 5

    # ---- DEMAND: review_count (real, wide-spread) on a log curve --------------
    rc = int(places.get("review_count") or 0)
    demand = _demand_points(rc)
    if rc:
        tier = ("very high" if demand >= 24 else "high" if demand >= 18
                else "solid" if demand >= 10 else "modest")
        reasons.append(f"{tier.capitalize()} demand ({rc} Google reviews) — more enquiries to field")

    # ---- NEED: the clearest buy signals we can scrape -------------------------
    need = 0
    if "no_online_booking" in kinds:
        need += 20
        reasons.append("No online booking — enquiries rely on calls/DMs (core fit)")
    if "limited_hours" in kinds:
        need += 8
        reasons.append("Closed days / early close in their Google hours — after-hours enquiries have nowhere to go")

    # ---- REACH: can we get to the owner, and how big is the digital gap? -------
    reach = 0
    if has_instagram:
        reach += 12
        reasons.append("Active on Instagram — owner-run and reachable by DM")
    if not has_website:
        reach += 6
        reasons.append("No website — books entirely via calls/DMs (bigger front-desk gap)")
    if _is_mobile(places.get("phone_intl") or places.get("phone")):
        reach += 5
        reasons.append("Mobile number listed (may be WhatsApp-reachable — unverified)")

    # ---- QUALITY: within the tight 4-5 band, a LOWER rating = more service gaps
    #      we can help close. This is the only honest use of the rating we do have. -----
    rating = places.get("rating")
    quality = 0
    if isinstance(rating, (int, float)):
        if rating < 4.5:
            quality = 10
            reasons.append(f"Rating {rating} (softer end of 4-5) — more service gaps to close")
        elif rating < 4.8:
            quality = 5
            reasons.append(f"Rating {rating} — some room to tighten response")

    raw_total = fit + demand + need + reach + quality
    score = min(100, raw_total)
    if not reasons:
        reasons.append("Local business; limited signal data")
    return {
        "score": score,
        "grade": _grade(score),
        "fit_score": min(100, fit + demand + need),
        "pain_score": min(100, need + quality),
        "probability": round(score / 100, 2),
        "reasoning": reasons,
    }
