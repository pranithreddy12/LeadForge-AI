"""Disambiguation tests for the owner-LinkedIn finder, built from the REAL Google SERP
results a user pasted (Renew Beauty Med Spa, Oasis Med Spa, American Aesthetic). The
point is precision: find the right owner, and refuse to attach a wrong-city namesake."""
from app.services.owner_linkedin import find_owner_linkedin_from_results


# --- Renew Beauty Med Spa (Dallas): owner Louisa Proulx is named in the company's own
#     result; the /in/ profiles that show up are the WRONG Renews (Georgetown, Minnesota)
#     or a manager. We must pick Louisa and reject the rest.
RENEW = [
    {"title": "Renew Beauty Med Spa",
     "url": "https://www.linkedin.com/company/renew-beauty-med-spa",
     "snippet": "8687 N Central Expy Suite 2220 Dallas, Texas 75204, Renew Beauty Med "
                "Spa owner, Louisa Proulx, Sign in to see who you already know."},
    {"title": "Kacey Pond - Owner at Renew Med Spa",
     "url": "https://www.linkedin.com/in/kacey-pond",
     "snippet": "Owner at Renew Med Spa. Georgetown, Texas, United States. Dec 2012 - Present."},
    {"title": "Kaylin Cardenas - Renew Beauty Med Spa",
     "url": "https://www.linkedin.com/in/kaylin-cardenas",
     "snippet": "Kaylin Cardenas. Medical Spa Manager at Renew Beauty Med Spa. Dallas-Fort "
                "Worth Metroplex. 215 followers 209 connections."},
    {"title": "Julie Davis - Founder & CEO of Renew MedSpa",
     "url": "https://www.linkedin.com/in/julie-davis",
     "snippet": "Julie Davis Founder & CEO of Renew MedSpa. Thomas St Paul, Minnesota, "
                "United States 150 followers."},
]

# --- Oasis Med Spa & Laser Center (Dallas): every owner in the results is a DIFFERENT
#     Oasis (Phoenix AZ, Woodinville WA). None is the Dallas one -> attach NOTHING.
OASIS = [
    {"title": "Mary Dahlhoff - co owner/manager at Oasis med spa",
     "url": "https://www.linkedin.com/in/mary-dahlhoff",
     "snippet": "Mary Dahlhoff - co owner/manager at Oasis med spa. Owner Self-employed "
                "Apr 2015 - Present."},
    {"title": "Danielle Beeny - Owner, Oasis Med Spa AZ",
     "url": "https://www.linkedin.com/in/danielle-beeny",
     "snippet": "Phoenix, Arizona, United States. Owner, Oasis Med Spa AZ. Experience: "
                "Oasis Med Spa AZ."},
    {"title": "Oasis Medspa & Salon",
     "url": "https://www.linkedin.com/company/oasis-medspa-salon",
     "snippet": "Primary 18600 Woodinville Snohomish Rd Suite 230 Woodinville, WA 98072, "
                "US. Owner at Oasis Spa & Salon."},
]

# --- American Aesthetic Medical Center (Dubai): the owner is stated in prose
#     ("the owner ... is Dr. Sana Sajan") with Dubai present.
AMERICAN = [
    {"title": "Dr. Sana Sajan | LinkedIn",
     "url": "https://www.linkedin.com/in/sana-sajan",
     "snippet": "The founder and owner of the American Aesthetic Medical Center (based in "
                "Dubai) is Dr. Sana Sajan. View her background and professional updates."},
]


def test_renew_picks_the_named_owner_not_the_wrong_renews():
    r = find_owner_linkedin_from_results(RENEW, company_name="Renew Beauty Med Spa",
                                         city="Dallas")
    assert r["found"] is True
    assert r["name"] == "Louisa Proulx"      # from the company page, Dallas + owner
    # the Georgetown / Minnesota / manager profiles must NOT win
    assert "Kacey" not in r["name"] and "Julie" not in r["name"] and "Kaylin" not in r["name"]


def test_oasis_refuses_wrong_city_namesakes():
    # All candidates are Phoenix / Woodinville Oasis businesses, none in Dallas.
    r = find_owner_linkedin_from_results(OASIS, company_name="Oasis Med Spa & Laser Center",
                                         city="Dallas")
    assert r["found"] is False


def test_american_extracts_owner_from_prose():
    r = find_owner_linkedin_from_results(AMERICAN,
                                         company_name="American Aesthetic Medical Center",
                                         city="Dubai")
    assert r["found"] is True
    assert "Sana Sajan" in r["name"]      # "Dr. Sana Sajan" (title kept) is fine
    assert r["linkedin_url"] == "https://www.linkedin.com/in/sana-sajan"


def test_no_city_never_attaches():
    # Without a city we can't disambiguate a common name -> stay safe, attach nothing.
    r = find_owner_linkedin_from_results(RENEW, company_name="Renew Beauty Med Spa", city=None)
    assert r["found"] is False
