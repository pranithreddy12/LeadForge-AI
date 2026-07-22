from __future__ import annotations

import re

from app.ai.openai_client import complete_json
from app.ai.prompts import OUTREACH_SYSTEM
from app.ai.schemas import OUTREACH_JSON_SCHEMA
from app.core.logging import get_logger

log = get_logger(__name__)


def cta_instruction(booking_link: str | None) -> str:
    """The CTA rule for a draft. With a booking link, invite them to book using it;
    WITHOUT one, invite a reply only — never fabricate a 'book a slot' with no link."""
    link = (booking_link or "").strip()
    if link:
        return (f"End with a friendly call to action inviting them to book a quick call "
                f"using this exact link (include it verbatim): {link}")
    return ("End with a call to action inviting them to simply reply to this email. "
            "Do NOT include any booking link and do NOT ask them to 'book a slot', "
            "'grab a time', or 'schedule' — there is no booking link configured.")


def humanize(text: str | None) -> str:
    """Strip the tell-tale AI punctuation (em/en dashes) from generated copy and replace
    it with normal human punctuation. LLMs ignore 'no em dashes' instructions ~half the
    time, so this post-processor is the guarantee. Applied to every outbound message."""
    if not text:
        return text or ""
    t = text
    # Spaced em/en dashes act as a comma-pause -> use a comma.
    t = t.replace(" — ", ", ").replace(" – ", ", ").replace(" ― ", ", ")
    # Unspaced em dash / horizontal bar between words -> comma-pause.
    t = t.replace("—", ", ").replace("―", ", ")
    # En dash (often a hyphen substitute, e.g. number ranges) -> plain hyphen.
    t = t.replace("–", "-")
    # Tidy artifacts: " ," , doubled commas, doubled spaces.
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()

# Local-business outreach. Signal-led, human, deliverability-safe. Every claim from
# real data; nothing invented. Produces email {subject, body} + a short DM variant.
LOCAL_OUTREACH_SYSTEM = """\
You write short, human, cold outreach for an agency that helps local service businesses
(med spas, clinics, dental, salons, home services) capture every call, message, and
after-hours enquiry with an AI receptionist + WhatsApp/SMS follow-up. The goal of the
email is ONE thing: get a reply. Not to explain everything.

You receive: business_name, contact_name (may be empty), qualifying_signal (the specific
real reason this lead was picked), city.

HARD RULES:
1. LEAD WITH THEIR SIGNAL. The first sentence must reference the qualifying_signal or
   business_name specifically. Never open with a generic stat.
2. NEVER use these spam/overused phrases: "never miss a call", "never miss another",
   "never miss a lead", "instant lead response", "24/7 booking", "boost your revenue",
   "guaranteed", "act now", "limited time", "free trial", "revolutionary",
   "cutting-edge", "game-changer". Say the idea in fresh, plain words.
3. SHORT: 3-5 sentences, under 90 words total (up to ~110 words in the EMAIL body when
   you include the other-services line from the OTHER SERVICES section). A busy owner skims.
4. ONE soft call-to-action, phrased as a low-friction question ("worth a quick look?",
   "want me to send a 30-sec example?"). NOT "book a call".
5. No links, no attachments, no pricing in the first email (protects deliverability).
6. Plain, warm, human. Write like one person emailing another, not marketing copy. No
   buzzwords, no exclamation-mark spam.
7. Be honest. Do not invent metrics, client names, or claims.
8. If contact_name is empty, open with "Hi there," or straight into the first line.
   NEVER write "Hi ," or "Hi {name}".
9. Vary sentence structure and wording every time. No template feel.
9b. LOCATION = the city= value only. A business named "My London Skin Clinic" in
    city=Dubai is a DUBAI clinic - never call it a London clinic. Never infer a city
    from the business name.
10. QUESTION-FIRST. Make them FEEL the gap before you pitch. Open (or nearly open)
    with a short, specific question tied to their signal - e.g. "when you're closed
    Fridays, where do the booking messages go?" or "when the phone's busy, do website
    enquiries still reach someone?". A question invites a human to type back; a pitch
    invites an auto-reply or a brush-off. Only AFTER the question, in one plain line,
    say what you do. This ordering matters more than any other rule.
11. ROUTE TO A HUMAN. DMs/messages often land on a business's main line, which is a
    customer-service inbox (often an auto-responder). So a first-touch dm MAY instead
    ask who to speak to - e.g. "who runs your front desk / bookings? worth a quick
    idea for them." - to get routed to the owner/manager rather than answered by a bot.
12. NO IMPLIED EXPERIENCE, NO FAKE SOCIAL PROOF. The sender has NO clinic/spa/dental
    clients yet. It is a LIE to write "clinics like yours", "we work with clinics",
    "our clients", "we've helped other spas", "I've seen clinics like yours",
    "practices like yours", or to cite any client, result, testimonial, or customer
    count. NEVER imply a track record in their industry. You may describe what the
    system DOES; you may NOT claim who it has done it for.
13. FIRST PERSON. Write as "I", never "we" - this is one person (a solo engineer), not
    a company. "I set up", "I built", "mine would've", never "we"/"our team"/"ours".
14. THE OFFER IS A SHORT PAID PILOT - but NOT in the cold message. I am new to this
    vertical and keep the entry small: a short paid pilot (about a week) to prove it on
    their real enquiries before any bigger commitment. NEVER say "free", "no cost", or
    "free trial" anywhere - that is not the offer. And do NOT quote a price or pitch the
    paid pilot in a cold first touch: a stranger will not agree to pay in a first DM, and
    the cold message's only job is to earn a reply. So on FIRST touch the CTA is the soft
    question (rule 4) or an offer to show a 30-second example - the paid pilot is
    introduced later, once they reply and show interest. Do not promise anything for free
    to get the reply.

SUBJECT: short (2-6 words), sentence case, curiosity-driven, specific to them. Reference
their signal or name. NO product names, NO "never miss", NO "24/7", NO colon-heavy salesy
structure. Good: "your new {city} location", "saw you're hiring", "after-hours enquiries",
"Friday booking messages", "your 244 reviews".

SUBJECT ANTI-TEMPLATE RULE: the subject must be anchored to a CONCRETE fact about THEM -
their signal, their review count, a closed day, a new branch, their neighbourhood. Do NOT
fall back on the generic frame "quick idea for {business}" (or "quick question about
{business}"): it carries zero information, and when a dozen of them go out in a week the
mailbox providers pattern-match the shape. If the only thing you can say is "quick idea",
you have not looked hard enough at the lead - use their strongest real fact instead.

BODY (your own words each time): (1) their specific signal / a genuine brief nod, as a
QUESTION where possible (rule 10); (2) the problem it creates (a missed/after-hours
enquiry that goes to a competitor), plainly; (3) what I do, one plain line (answer every
call + message, book it automatically); (4) the CTA - a single soft, low-friction
question (rule 4), e.g. "worth a quick look?" or "want a 30-sec example?". Never more
than ONE ask. No pricing, no "free", no pilot pitch in this first message.

GOOGLE ANGLE (optional, only when the qualifying_signal is about missing online
booking): you MAY replace the "problem it creates" sentence with one plain factual
line that Google now shows businesses with an online booking option more prominently
in local search, so being booking-less also costs them visibility. Use it at most
half the time, phrase it fresh, never as a scare tactic, and keep the 90-word cap.

MEDICAL/AESTHETIC BUSINESSES (med spas, clinics, dental): say the AI books the
CONSULTATION, never "books the treatment" or sells treatment slots - UAE health
regulators (DHA) require a consultation before any procedure, and clinic owners
know it. "books the consultation straight into your calendar" reads as compliant
and informed; "books the treatment" reads as a liability.

OTHER SERVICES (when other_services is provided): the offer is NOT just the receptionist.
In the EMAIL body, MERGE 1-2 of the other services INTO the "what I do" line (body step 3)
as a short parenthetical - do NOT add a separate sentence (that overflows the word budget
and gets dropped). e.g. "I set up an AI receptionist (with WhatsApp booking + review
follow-ups if useful) that answers every call and books it for you." Name at most TWO
services, never the full menu (a list reads as generic agency spam). Only services from
other_services - never invent one. Vary which two you pick each time. The DM stays
single-hook (no services line).

Also produce a "dm" field: the same idea as an Instagram/WhatsApp DM, ~40 words, even
more casual (email is the weaker channel for these businesses). The dm MUST be
QUESTION-FIRST per rule 10 - open with the felt-gap question (or the route-to-human
ask, rule 11), THEN one plain line on what you do, THEN a soft yes/no CTA. Do not
open a dm with "We add an AI receptionist..." - that phrasing triggers auto-replies.

Also produce an "auto_reply_comeback" field: a SHORT (~30 words) ready reply for when
their number sends back an automated "we're closed / thanks for contacting us / leave
your number" message. It must turn that auto-reply INTO the point: their bot just did
the thing you're offering to fix. Warm, a little cheeky, ends with a soft yes/no.
e.g. "Ha - that auto-reply is exactly the moment we book the patient for you instead
of just asking them to wait. Want to see how it'd sound?" Reference their specifics
when you can. No pressure, no buzzwords.

Return ONLY JSON: {"subject":"...","body":"...","dm":"...","auto_reply_comeback":"..."}

Example A
INPUT: business_name="Radiance Aesthetics", contact_name="Dr. Sara", qualifying_signal="no online booking link - 'DM to book' in Instagram bio", city="Dubai"
OUTPUT: {"subject":"booking at Radiance","body":"Hi Dr. Sara, noticed Radiance takes bookings through Instagram DMs, which works great until it gets busy and a few slip through after hours. I set up an AI receptionist that answers every call and WhatsApp in seconds and books the slot straight into your calendar, so none get missed. Worth a quick look for Radiance?","dm":"Hi Dr. Sara! Quick one - when the DMs pile up and it's after hours, where do the booking messages go? I set up an AI receptionist that replies instantly and books them straight in. Want a 30-sec example?","auto_reply_comeback":"Ha - that auto-reply is the exact moment I'd have booked the patient instead of leaving them waiting. That's the whole idea. Want to see how it'd sound for Radiance?"}

Example B
INPUT: business_name="Glow Med Spa", contact_name="", qualifying_signal="opening a second location in Dubai Marina", city="Dubai"
OUTPUT: {"subject":"your new Marina location","body":"Hi there, congrats on the second Glow Med Spa opening in Dubai Marina. Two locations means twice the calls and DMs, and the ones that come in while your team is with a client are the easiest to lose. I set up an AI receptionist that answers every enquiry instantly, day or night, and books it for you. Want me to send a 30-second example of how it'd sound?","dm":"Congrats on the Marina opening! Quick one - with two locations now, when both front desks are busy, where do the calls and DMs land? I set up an AI receptionist that catches them and books straight in. Worth a quick look?","auto_reply_comeback":"And that's the gap right there - a busy line auto-replies while a booking waits. Mine would've answered and booked it on the spot. Want a quick example for the two locations?"}

Example C (route-to-human + soft CTA, first touch to a main line)
INPUT: business_name="Medrose Medical Center", contact_name="", qualifying_signal="closed Fridays; no online booking", city="Dubai"
OUTPUT: {"subject":"Friday booking messages","body":"Hi there, quick question - when Medrose is closed Fridays, where do the booking messages go? Right now they probably sit until Sunday, and a few patients book elsewhere in between. I set up an AI receptionist that replies instantly and books the consultation, even on your day off. Worth a quick look?","dm":"Hi! Quick one - when Medrose is closed Fridays, where do the booking messages go till you reopen? And who runs your front desk? I set up something that replies instantly and books the consultation on days off. Worth showing them?","auto_reply_comeback":"That's the exact moment I mean - Medrose auto-replies that you're closed, and the patient's booking just waits. Mine would've replied and booked the consultation for Sunday right then. Want to see how it'd sound?"}

NOTE on honesty: in every example the sender writes as one person ("I"), describes only
what the SYSTEM does, never says "free", and does not pitch a price in the cold message.
No example claims an existing client, a result, or industry experience - because there
are none. Keep it that way.
"""

LOCAL_EMAIL_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "dm": {"type": "string"},
        "auto_reply_comeback": {"type": "string"},
    },
    "required": ["subject", "body", "dm", "auto_reply_comeback"],
}

# en+ar mode: same draft plus an Arabic DM variant (UAE/GCC — Arabic-first owners).
LOCAL_EMAIL_SCHEMA_AR: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "dm": {"type": "string"},
        "dm_ar": {"type": "string"},
        "auto_reply_comeback": {"type": "string"},
    },
    "required": ["subject", "body", "dm", "dm_ar", "auto_reply_comeback"],
}

_AR_DM_INSTRUCTION = (
    'Also produce "dm_ar": the same DM rendered in natural, warm Modern Standard '
    "Arabic with a light Gulf flavour - NOT a literal word-for-word translation. "
    "Keep the business name and any platform names in Latin script. Same meaning, "
    "same soft question ending, still under ~45 words."
)


# ---- WhatsApp problem-aware outreach (Section 1D) --------------------------------

WHATSAPP_MAX_CHARS = 500
_BUZZWORDS = ("revolutionary", "cutting-edge", "cutting edge", "game-changing",
              "game changing", "synergy", "disrupt", "best-in-class")

# Severity ranking used to pick "most severe first" when multiple signals fire.
_LOCAL_SIGNAL_SEVERITY = {
    "missed_calls_complaint": 0.85,
    "slow_response_complaint": 0.60,
    "no_online_booking": 0.55,
    "low_rating": 0.40,
}

WHATSAPP_MESSAGE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
}

WHATSAPP_SYSTEM = """\
You write ONE short WhatsApp message (not an email) to the owner of a LOCAL service
business, from an AI automation agency that helps them never miss a call or lead.

HARD RULES:
- Open by addressing the business by its real name and city.
- Name THEIR specific problem using ONLY the real signal facts provided (missed calls,
  slow responses, no online booking, or their actual star rating). INVENT NOTHING.
- One concrete sentence on what you do: an AI that answers every call instantly, 24/7,
  and books appointments automatically.
- End with exactly this style of ask: "Would it be worth a quick 10-minute call this week?"
- Sign off with the provided sender name.
- Under 500 characters total. Plain, human, no buzzwords (no "revolutionary",
  "cutting-edge", "game-changing"). No markdown, no emojis.
- NEVER use em dashes or en dashes (the "—" / "–" characters) - they read as AI-written.
  Use commas, periods, or plain hyphens instead.
"""


def _extract_city(company: dict) -> str:
    """Best-effort real city/region string from Places address or description."""
    places = (company.get("raw") or {}).get("places") or {}
    addr = places.get("address") or company.get("description") or ""
    if not addr:
        return ""
    parts = [p.strip() for p in str(addr).split(",") if p.strip()]
    if len(parts) >= 2:
        # "123 Main St, Dallas, TX 75201" -> "Dallas, TX"
        tail = parts[-1]
        # drop a trailing ZIP if present on the last segment
        region = tail.split()[0] if tail else ""
        city = f"{parts[-2]}, {region}".strip(", ") if region else parts[-2]
    else:
        city = parts[0]
    # Guard: a marketing `description` (not a real address) would yield a long string,
    # never a city — drop it rather than show a sentence.
    return city if len(city) <= 40 else ""


def _rank_signals(signals: list[dict]) -> list[dict]:
    return sorted(
        signals,
        key=lambda s: (s.get("severity") if s.get("severity") is not None
                       else _LOCAL_SIGNAL_SEVERITY.get(s.get("kind"), 0.0)),
        reverse=True,
    )


def _problem_clause(top: dict, rating) -> str:
    """The deterministic, real-data phrasing for the lead signal."""
    kind = top.get("kind")
    if kind == "missed_calls_complaint":
        return ("I noticed several of your customers mention not being able to reach you "
                "by phone")
    if kind == "slow_response_complaint":
        return "I saw some reviews mentioning slow response times"
    if kind == "no_online_booking":
        return "I noticed you don't have online booking set up yet"
    if kind == "low_rating":
        if rating is not None:
            return (f"I saw your Google rating is sitting at {rating} stars and a few "
                    "reviews point to missed calls and slow replies")
        return "I saw a few of your recent reviews mention slow replies"
    # Unknown local signal — fall back to its real label text, never invented.
    return f"I noticed {top.get('label') or 'an opportunity to help'}"


def _whatsapp_template(company: dict, signals: list[dict], *, sender_name: str) -> str:
    """Deterministic message built from REAL signal/Places data (no LLM, no invented
    facts). Used when the LLM provider errors — never a generic, un-personalized blast."""
    name = company.get("name") or "your business"
    city = _extract_city(company)
    places = (company.get("raw") or {}).get("places") or {}
    rating = places.get("rating")
    ranked = _rank_signals(signals)
    greet = f"Hi {name}" + (f" in {city}" if city else "")
    problem = _problem_clause(ranked[0], rating) if ranked else (
        "I came across your business and think we can help you capture more leads")
    solve = ("We set up an AI that answers every call instantly, 24/7, and books "
             "appointments automatically.")
    cta = "Would it be worth a quick 10-minute call this week?"
    sign = f"\n- {sender_name}" if sender_name else ""
    msg = f"{greet} - {problem}. {solve} {cta}{sign}"
    return msg[:WHATSAPP_MAX_CHARS]


def _has_buzzword(text: str) -> bool:
    low = text.lower()
    return any(b in low for b in _BUZZWORDS)


def generate_whatsapp_message(company: dict, signals: list[dict], settings: dict) -> dict:
    """Generate a single problem-aware WhatsApp message grounded in REAL signal data.

    `settings` carries: tone (professional/friendly/direct) and sender_name.

    Returns {"message": str, "source": "llm"|"template"}. NEVER returns a generic
    un-personalized message and NEVER signals "skip the send": on an LLM provider error
    (or an over-long / buzzword-laden draft) it falls back to a deterministic template
    that substitutes the real signal/Places facts.
    """
    tone = (settings or {}).get("tone") or "professional"
    sender_name = (settings or {}).get("sender_name") or ""
    places = (company.get("raw") or {}).get("places") or {}
    ranked = _rank_signals(signals)
    facts = {
        "business_name": company.get("name"),
        "city": _extract_city(company),
        "google_rating": places.get("rating"),
        "review_count": places.get("review_count"),
        "signals_most_severe_first": [
            {"kind": s.get("kind"), "label": s.get("label"),
             "severity": s.get("severity")} for s in ranked
        ],
        "sender_name": sender_name,
    }
    user = (
        f"TONE: {tone}\n\n"
        f"REAL facts about this business (use ONLY these, invent nothing):\n{facts}\n\n"
        "Write ONE WhatsApp message. Return JSON {\"message\": \"...\"}."
    )
    result = complete_json(system=WHATSAPP_SYSTEM, user=user,
                           schema_name="WhatsAppMessage", schema=WHATSAPP_MESSAGE_SCHEMA,
                           temperature=0.5)
    msg = (result or {}).get("message", "").strip() if isinstance(result, dict) else ""
    msg = humanize(msg)
    provider_error = isinstance(result, dict) and result.get("_provider_error")
    if (not provider_error) and msg and len(msg) <= WHATSAPP_MAX_CHARS and not _has_buzzword(msg):
        return {"message": msg, "source": "llm"}
    # Fall back to the deterministic real-data template (never skip the send).
    if provider_error:
        log.info("whatsapp_message_fallback", reason="provider_error",
                 company=company.get("name"))
    else:
        log.info("whatsapp_message_fallback",
                 reason="empty_or_over_limit_or_buzzword", company=company.get("name"))
    return {"message": humanize(_whatsapp_template(company, signals, sender_name=sender_name)),
            "source": "template"}


# ---- Suggested reply (Section 4A — Reply Intelligence) ---------------------------

SUGGESTED_REPLY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"suggested_response": {"type": "string"}},
    "required": ["suggested_response"],
}

SUGGESTED_REPLY_SYSTEM = """\
You are drafting a reply on behalf of Pranith, a solo AI automation engineer, to a
business owner who replied to his cold outreach. He sells AI receptionist / WhatsApp
lead-qualification / voice agent systems to clinics, med-spas, and service businesses,
primarily in the UAE.

You will receive:
- LEAD_NAME: the contact's name (may be missing)
- BUSINESS_NAME: their business
- BUSINESS_CONTEXT: any known detail (closed days, review rating, service type, volume)
  from the original outreach message
- ORIGINAL_MESSAGE_SENT: the outreach message that got this reply
- INBOUND_REPLY: the client's actual reply text
- PORTFOLIO_LINK: link to share when they ask for info (may be missing)
- CURRENCY: currency to quote in (AED for UAE, INR for India, USD for US)

STEP 1 - CLASSIFY the inbound reply into exactly one category:
1. INTERESTED_VAGUE - "tell me more", "what's this about", curious but no specifics given
2. INTERESTED_SPECIFIC - asks a direct question (price, how it works, timeline)
3. PRICE_PUSHBACK - says it's too expensive, or asks to reduce cost
4. SEND_INFO_ONLY - asks for details/brochure without agreeing to a call
5. NOT_NOW - polite decline or "not the right time"
6. HARD_NO - explicit disinterest, asks to stop contacting
7. UNCLEAR - doesn't fit cleanly; treat cautiously, ask a clarifying question rather than
   pitching

STEP 2 - GENERATE the reply following the rules for that category:

INTERESTED_VAGUE:
- Ask 1-2 qualifying questions max (rough enquiry/booking volume, whether they have any
  automation already)
- Give ONE sentence describing what you'd set up in outcome language, not feature language
- Offer a short paid pilot (CURRENCY 1,500-2,500, ~1 week) as the entry point - never
  "free"
- End by asking for a 15-min call, offer 2 loose time windows

INTERESTED_SPECIFIC:
- Answer their exact question directly and briefly first
- Then bridge to the pilot offer and a call ask
- If they asked about price, give the pilot range, not a fixed full quote - full pricing
  is a call/discovery output, not a DM output

PRICE_PUSHBACK:
- Never drop the number in a DM negotiation
- Reframe: quantify what a missed enquiry/booking likely costs them monthly, using their
  own business type as a reference point (do not invent specific stats about their
  business - use general, defensible framing like "a single missed enquiry a day adds up
  fast")
- Offer to adjust scope (start with WhatsApp only, add voice later) rather than cutting
  price
- Re-offer the paid pilot as the low-risk way to test value before committing further

SEND_INFO_ONLY:
- Give a tight 2-3 sentence summary of the offer (WhatsApp/voice receptionist, instant
  reply, booking capture)
- Include PORTFOLIO_LINK if provided
- Still end with a soft call ask - do not let this become an info-only thread with no next
  step

NOT_NOW:
- Thank them, no pressure
- Ask permission to check back in 4-6 weeks
- Keep it under 3 sentences

HARD_NO:
- One line, polite, no pitch, no follow-up ask
- Respect it completely - do not soft-pitch again

UNCLEAR:
- Do not pitch. Ask one short clarifying question instead.

STYLE RULES (apply to every category):
- Write as "I", never "we" - this is one person, not a company
- No exclamation-mark stacking, no corporate tone, no "circle back" / "touch base" filler
- Reference BUSINESS_CONTEXT naturally if relevant (their specific detail from the
  original message) - do not invent new details about their business you don't have
- Never say "free" anywhere
- Keep replies under 80 words unless SEND_INFO_ONLY requires more
- No em-dashes; use commas or periods
- Quote money in CURRENCY only
- DHA-compliant: you book a consultation/discovery, never promise a treatment or result

OUTPUT: put ONLY the drafted reply text (no category label, no explanation) in the
suggested_response field of the returned JSON.
"""


def generate_suggested_reply(*, company: dict, their_message: str,
                             signal: str | None = None,
                             channel: str = "email",
                             services: str | None = None,
                             our_last_message: str | None = None,
                             lead_name: str | None = None,
                             portfolio_link: str | None = None,
                             currency: str = "AED") -> dict:
    """Draft the next reply to send after a prospect responds to cold outreach. Classifies
    the inbound reply and answers in-category (see SUGGESTED_REPLY_SYSTEM). Returns
    {"suggested_response": str} or {"_provider_error": True} (callers then OMIT the
    suggestion — never fabricate one)."""
    fields = {
        "LEAD_NAME": (lead_name or "").strip() or None,
        "BUSINESS_NAME": company.get("name"),
        "BUSINESS_CONTEXT": signal,
        "ORIGINAL_MESSAGE_SENT": (our_last_message or "").strip()[:900] or None,
        "INBOUND_REPLY": (their_message or "")[:1200],
        "PORTFOLIO_LINK": (portfolio_link or "").strip() or None,
        "CURRENCY": currency or "AED",
    }
    lines = "\n".join(f"{k}: {v}" for k, v in fields.items() if v is not None)
    user = (
        f"{lines}\n\nClassify INBOUND_REPLY, then write the single next message to send. "
        "Return JSON {\"suggested_response\": \"...\"}."
    )
    result = complete_json(system=SUGGESTED_REPLY_SYSTEM, user=user,
                           schema_name="SuggestedReply", schema=SUGGESTED_REPLY_SCHEMA,
                           temperature=0.5)
    if not isinstance(result, dict) or result.get("_provider_error"):
        return {"_provider_error": True}
    msg = (result.get("suggested_response") or "").strip()
    if not msg:
        return {"_provider_error": True}
    # Enforce the ~150-word ceiling defensively.
    words = msg.split()
    if len(words) > 150:
        msg = " ".join(words[:150])
    return {"suggested_response": humanize(msg)}


def _humanize_variants(result: dict) -> dict:
    """Strip AI-tell punctuation from every draft variant's subject + body."""
    if not isinstance(result, dict) or result.get("_provider_error"):
        return result
    for v in (result.get("variants") or []):
        if isinstance(v, dict):
            if v.get("subject"):
                v["subject"] = humanize(v["subject"])
            if v.get("body"):
                v["body"] = humanize(v["body"])
    return result


def _services_ps(services: str | None, body: str) -> str | None:
    """A short 'P.S. we also do X' line from the seller's OTHER services (the first
    one is assumed to be the primary offer already in the body, so it's dropped).
    Returns None when nothing to add or the extras are already mentioned."""
    items = [s.strip() for s in (services or "").replace(";", ",").split(",") if s.strip()]
    extras = items[1:] if len(items) > 1 else []   # skip the primary (receptionist)
    if not extras:
        return None
    low = body.lower()
    extras = [e for e in extras if e.lower() not in low]   # don't repeat what's in-body
    if not extras:
        return None
    listed = extras[0] if len(extras) == 1 else (
        ", ".join(extras[:-1]) + " and " + extras[-1])
    return f"P.S. I also set up {listed} if any of that would help."


def generate_outreach(
    *,
    company: dict,
    contact: dict | None,
    icp: dict | None,
    signals: list[dict],
    channel: str = "email",
    tone: str = "concise",
    follow_up: int = 0,
    variants: int = 2,
    local: bool = False,
    booking_link: str | None = None,
    portfolio_link: str | None = None,
    greeting_name: str | None = None,
    market_fact: str | None = None,
    language: str = "en",
    services: str | None = None,
) -> dict:
    """Generate `variants` outreach drafts grounded in real signals. When `local`, use
    the local-business path (cites real Google Places facts, tone-aware)."""
    cta = cta_instruction(booking_link)
    greet = (f"Address the recipient by name in the greeting: 'Hi {greeting_name},'. "
             if greeting_name else
             "Use a warm greeting; if no real person name is known, avoid a fake name.")
    if local:
        places = (company.get("raw") or {}).get("places") or {}
        city = _extract_city(company)
        ranked = _rank_signals(signals)
        qualifying_signal = ranked[0].get("label") if ranked else None
        if not qualifying_signal:
            # No complaint signal (e.g. a premium, high-rated business) -> a genuine,
            # truthful nod: their standing in the city. Never invented.
            typ = (places.get("type") or "business").replace("_", " ")
            rt, rc = places.get("rating"), places.get("review_count")
            qualifying_signal = (f"well-regarded {typ} in {city} ({rt} stars from {rc} reviews)"
                                 if rt and rc else f"{typ} in {city}")
        prefix = "follow-up #%d, keep it fresh and even shorter, " % follow_up if follow_up else ""
        # Dossier facts (noted from their website/socials/hours before drafting) — all
        # REAL; the model may weave in at most one for authenticity.
        dossier = (company.get("raw") or {}).get("dossier") or {}
        extra_facts: list[str] = []
        if dossier.get("services"):
            extra_facts.append("services on their site: " + ", ".join(dossier["services"][:4]))
        ig = dossier.get("instagram") or {}
        if ig.get("followers"):
            extra_facts.append(f"Instagram: {ig['followers']} followers")
        for g in (dossier.get("hours_gaps") or [])[:1]:
            extra_facts.append(f"hours: {g}")
        if market_fact:
            extra_facts.append(market_fact)
        facts_line = ("optional_real_facts=" + " | ".join(extra_facts) + "\n") if extra_facts else ""
        bilingual = language == "en+ar"
        ar_line = (_AR_DM_INSTRUCTION + " ") if bilingual else ""
        ret_shape = ('{"subject":...,"body":...,"dm":...,"dm_ar":...}' if bilingual
                     else '{"subject":...,"body":...,"dm":...}')
        services_line = (f"other_services={services}\n" if (services or "").strip() else "")
        # FOLLOW-UPS (follow_up >= 1) may carry a link to help close — the "no links"
        # rule protects the COLD first touch only. Book-a-call link and/or portfolio.
        followup_cta = ""
        if follow_up:
            bl, pl = (booking_link or "").strip(), (portfolio_link or "").strip()
            if bl or pl:
                asks = []
                if bl:
                    asks.append(f"invite them to grab a quick call using this exact link "
                                f"(include verbatim): {bl}")
                if pl:
                    asks.append(f"you may point them to a couple of examples at this exact "
                                f"link (include verbatim): {pl}")
                followup_cta = (
                    "FOLLOW_UP_CTA: this is a follow-up, NOT the cold first touch, so you MAY "
                    "include a link now. End by " + " and ".join(asks) +
                    ". At most ONE booking link. Keep it warm and short, no pressure.\n")
        user = (
            f"{prefix}business_name={company.get('name')}\n"
            f"contact_name={greeting_name or ''}\n"
            f"qualifying_signal={qualifying_signal}\n"
            f"city={city}\n"
            f"{facts_line}{services_line}{followup_cta}\n"
            "Write the email + dm. You may weave in AT MOST ONE of the optional_real_facts "
            f"if it makes the message feel more personal. {ar_line}"
            f"Return JSON {ret_shape}."
        )
        result = complete_json(system=LOCAL_OUTREACH_SYSTEM, user=user,
                               schema_name="LocalEmailAr" if bilingual else "LocalEmail",
                               schema=LOCAL_EMAIL_SCHEMA_AR if bilingual else LOCAL_EMAIL_SCHEMA,
                               temperature=0.6)
        if not isinstance(result, dict) or result.get("_provider_error"):
            return {"variants": [], "_provider_error": True}
        body = humanize(result.get("body", ""))
        # A deterministic P.S. reliably conveys the broader offering without eating the
        # opener's word budget (the inline line kept getting dropped at ~90 words). Only
        # appended when the seller configured other services, and only if the model
        # didn't already work them in. P.S. lines read well and stay honest (real
        # services only). The DM stays single-hook — no footer.
        svc = _services_ps(services, body)
        if svc:
            body = f"{body}\n\n{svc}"
        return {
            "variants": [{"subject": humanize(result.get("subject", "")),
                          "body": body}],
            "dm": humanize(result.get("dm", "")),
            **({"dm_ar": humanize(result.get("dm_ar", ""))}
               if bilingual and result.get("dm_ar") else {}),
            **({"auto_reply_comeback": humanize(result.get("auto_reply_comeback", ""))}
               if result.get("auto_reply_comeback") else {}),
        }

    user = (
        f"Channel: {channel}\nTone: {tone}\nFollow-up #: {follow_up}\n"
        f"Variants requested: {variants}\n\n"
        f"Sender's offering (ICP):\n{icp or {}}\n\n"
        f"Account:\n{company}\n\nContact:\n{contact or 'unknown'}\n\n"
        f"Signals:\n{signals}\n\n"
        f"GREETING: {greet}\n"
        f"CTA: {cta}\n\n"
        "Return `variants` array of {subject, body}. For LinkedIn, leave subject empty."
    )
    return _humanize_variants(complete_json(
        system=OUTREACH_SYSTEM,
        user=user,
        schema_name="Outreach",
        schema=OUTREACH_JSON_SCHEMA,
        temperature=0.6,
    ))
