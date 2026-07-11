# Retell Voice Agent — Dubai Med-Spa AI Receptionist ("Layla")

This is the agent you demo when a lead replies. It answers every call, understands what
the caller wants, checks availability, books the appointment, and offers a WhatsApp
confirmation — so nothing slips through when the front desk is busy or closed.

Built for the exact pitch in your outreach: *"you take bookings by phone/DM only, so
enquiries slip after hours — an AI receptionist answers every one and books it."*

---

## 0. What you're building (the demo that closes)

A prospect (med-spa owner) replies to your email/DM. You say: *"Here's a 2-minute number
you can call right now — it's the receptionist we'd set up for [their spa]."* They call,
book a facial, get a WhatsApp confirmation. That call **is** the sale.

Keep the demo tight: one agent, one phone number, a couple of realistic services, mocked
availability. You do NOT need a real calendar to close — you need the *experience*.

---

## 1. Retell setup (10 minutes)

1. Create an account at **dashboard.retellai.com**.
2. **Agents → Create Agent → Single-Prompt Agent** (simplest, most reliable for a demo).
3. **Voice**: pick a warm, natural female voice (11labs "Sarah" or "Jessica", or a Retell
   preset). For Dubai, a soft neutral/British-leaning accent lands well. Turn ON
   *backchanneling* and *filler words* for natural feel.
4. **LLM**: GPT-4o (or Retell's default realtime model). Temperature ~0.6.
5. Paste the **System Prompt** from §2 below.
6. Add the **Custom Functions** from §4.
7. Set the **Dynamic Variables** in §3 (so one agent works for any spa in the demo).
8. **Get a phone number** (Retell → Phone Numbers → buy one, or import Twilio) and attach
   the agent. This is the number you send prospects.
9. Test with §7's script. Ship.

---

## 2. System Prompt  ← paste this into Retell's "General Prompt"

```
# IDENTITY
You are Layla, the friendly front-desk receptionist for {{business_name}}, a med spa in
{{city}}. You answer calls warmly and efficiently and your ONE job is to help the caller
book an appointment or get a quick answer — then get off the line politely. You sound like
a real person: warm, calm, unhurried but efficient. Short sentences. One question at a time.

# CONTEXT YOU KNOW
- Business: {{business_name}}, {{city}}
- Services & rough prices: {{services}}
- Opening hours: {{hours}}
- Today's date/time is provided by the system. It is currently {{current_time}}.
- You can check availability and book using your tools (functions). Never claim a booking
  is made unless the book_appointment tool returned success.

# HOW YOU TALK
- Greet, then listen. Do NOT dump information. Ask what they'd like help with.
- One question at a time. Keep each turn to 1–2 short sentences.
- Warm and human, never robotic or salesy. No corporate filler.
- Mirror their pace. If they're in a hurry, be crisp.
- Use the caller's name once you have it, naturally — not every sentence.
- If you don't know something, say so and offer to have the team follow up. NEVER invent
  prices, medical claims, or availability.
- You are NOT a doctor. Do not give medical advice or diagnose. For clinical questions,
  say a specialist will confirm details at the appointment.

# THE FLOW (adapt naturally, don't read it like a script)
1. GREET: "Thanks for calling {{business_name}}, this is Layla — how can I help?"
2. UNDERSTAND: Find out what they want (a treatment, a booking, a question). If it's a
   booking, find out which service and roughly when they'd like to come in.
3. GET THEIR NAME + NUMBER: "May I take your name?" and confirm a callback number. Read
   the number back to confirm it digit by digit.
4. CHECK AVAILABILITY: Call check_availability with the service and their preferred day/
   time. Offer 1–2 concrete slots ("I have Tuesday at 2, or Wednesday morning — which
   suits?"). Don't overwhelm with options.
5. BOOK: Once they pick, call book_appointment. Only confirm success after the tool
   returns success. "Perfect, you're booked for [service] on [day] at [time]."
6. CONFIRM + WHATSAPP: "I'll send a confirmation to your WhatsApp now — anything else?"
   Call send_whatsapp_confirmation.
7. CLOSE: Warm sign-off. "See you then — have a lovely day."

# AFTER-HOURS / BUSY
If it's outside opening hours, still take the booking normally — that's the whole point.
Never say "we're closed, call back." You ARE the after-hours cover.

# OBJECTIONS / FAQ  (answer briefly, then steer back to booking)
- "How much is X?" → give the rough range from {{services}}; if unknown, "the team will
  confirm the exact price when you come in — shall I hold you a slot?"
- "Do you do [treatment]?" → if in {{services}}, yes + book; if unsure, "let me have a
  specialist confirm and call you back — what's the best number?"
- "Can I speak to a person?" → "Of course — I'll pass your details to the team and they'll
  call you shortly. Meanwhile, would you like me to hold a slot?"
- Angry/complaint → apologize sincerely, take details, promise a callback from the manager,
  do not argue.

# HARD RULES
- Never claim an appointment is booked unless book_appointment returned success.
- Never invent prices, availability, or medical advice.
- Keep it short. This is a phone call, not an email.
- Always confirm the phone number by reading it back.
- End every successful call by sending the WhatsApp confirmation.

# DHA COMPLIANCE (UAE - non-negotiable)
- You book CONSULTATIONS, not treatments. Every injectable/laser/procedure enquiry is
  booked as "a consultation with the doctor" (DHA requires a clinical consultation +
  informed consent before any procedure). Never sell or confirm a treatment directly.
- Never promise outcomes: no "guaranteed results", "100% safe", "best clinic in Dubai".
  If asked "will it work for me?", say that's exactly what the consultation determines.
- Only call a staff member "Dr." if the clinic lists them as a licensed physician.
```

---

## 3. Dynamic Variables (so one agent demos any spa)

Set these in Retell (Agent → Dynamic Variables) or pass them when you start a call. For a
quick demo you can hardcode a sample spa:

| Variable            | Example value |
|---------------------|---------------|
| `business_name`     | `Glow Med Spa` |
| `city`              | `Dubai` |
| `services`          | `Signature facial (from AED 350), HydraFacial (from AED 600), laser hair removal (from AED 400/session), Botox (consult required), massage (from AED 250)` |
| `hours`             | `Daily 10am–9pm; Friday 2pm–10pm` |
| `current_time`      | (Retell injects live time; or set for the demo) |

Tip: when you demo for a specific prospect, drop *their* real name + services in here so the
agent greets with their spa's name — it lands hard.

---

## 4. Custom Functions

Add these under Agent → Functions. For the **demo**, point them at a tiny mock webhook (or
use Retell's "custom function" with a static response) — you do NOT need a real calendar to
impress. For **production**, point them at your booking backend / Google Calendar / the med
spa's system.

### 4.1 `check_availability`
```json
{
  "name": "check_availability",
  "description": "Check open appointment slots for a service near a preferred day/time.",
  "parameters": {
    "type": "object",
    "properties": {
      "service": {"type": "string", "description": "The treatment requested"},
      "preferred_day": {"type": "string", "description": "e.g. 'tomorrow', 'Tuesday', '2026-07-10'"},
      "preferred_time": {"type": "string", "description": "e.g. 'morning', 'after 5pm', '2pm'"}
    },
    "required": ["service", "preferred_day"]
  }
}
```
**Mock response (demo):**
```json
{"slots": ["Tuesday 2:00 PM", "Wednesday 11:00 AM", "Wednesday 6:30 PM"]}
```

### 4.2 `book_appointment`
```json
{
  "name": "book_appointment",
  "description": "Book the appointment once the caller confirms a slot. Returns success + a reference.",
  "parameters": {
    "type": "object",
    "properties": {
      "caller_name": {"type": "string"},
      "phone": {"type": "string"},
      "service": {"type": "string"},
      "slot": {"type": "string", "description": "The exact slot the caller chose"}
    },
    "required": ["caller_name", "phone", "service", "slot"]
  }
}
```
**Mock response (demo):**
```json
{"success": true, "reference": "GLOW-4821", "slot": "Tuesday 2:00 PM"}
```

### 4.3 `send_whatsapp_confirmation`
```json
{
  "name": "send_whatsapp_confirmation",
  "description": "Send a WhatsApp confirmation of the booking to the caller.",
  "parameters": {
    "type": "object",
    "properties": {
      "phone": {"type": "string"},
      "message": {"type": "string", "description": "Short confirmation with service, day, time, reference"}
    },
    "required": ["phone", "message"]
  }
}
```
**Mock response (demo):** `{"sent": true}`

> Production wiring: `send_whatsapp_confirmation` can point straight at LeadForge's existing
> WhatsApp sender (`/api/v1/...`) or the Meta Cloud API you already configured — so the
> confirmation actually lands on the caller's phone. That's a strong upsell moment.

---

## 5. Voice & behavior config (Retell settings)

- **Interruption sensitivity**: medium-high (let the caller cut in naturally).
- **Backchanneling**: ON ("mm-hm", "got it") — big natural-feel boost.
- **Filler words**: ON.
- **Responsiveness / latency**: prioritize low latency; keep responses short so turns feel snappy.
- **Ambient sound**: light "office" or none.
- **Voicemail detection**: ON (so it doesn't talk to an answering machine).
- **End-call function**: enable, so Layla can hang up cleanly after the sign-off.
- **Max call duration**: ~5 min for a demo.

---

## 6. WhatsApp follow-up (the differentiator)

Med spas live on WhatsApp. After booking, Layla sends a confirmation like:

> *"Hi Sara! You're booked at Glow Med Spa for a HydraFacial on Tuesday at 2:00 PM (ref
> GLOW-4821). Reply here if anything changes — see you then! 💛"*

For the demo, the mock `{"sent": true}` is fine and you narrate it. For production, wire it to
the Meta WhatsApp sender already in LeadForge so it genuinely arrives — that turns "cool demo"
into "I need this."

---

## 7. Test-call script (call your Retell number and run this)

Play the **caller**. Confirm Layla handles each:

1. *"Hi, do you do HydraFacials?"* → she confirms + offers to book.
2. *"Yeah, sometime this week — Tuesday afternoon ideally."* → she checks availability, offers slots.
3. *"Tuesday at 2 works."* → she asks your name + number, **reads the number back**.
4. → she books, gives a reference, says she'll WhatsApp the confirmation.
5. Curveball: *"Actually, how much is Botox?"* → she gives the range or offers a callback, no invented price.
6. Curveball: *"Can I talk to a human?"* → she takes details, promises a callback, still offers to hold a slot.
7. She closes warmly and ends the call.

If she invents a price, claims a booking before the tool returns, or rambles — tighten the
System Prompt (§2 "HARD RULES" / "HOW YOU TALK").

---

## 8. How to use it in your sprint

1. Build the agent once (steps 1–8). Get the phone number.
2. When a lead replies to your email/DM, send: *"Want to hear it? Call this number — it's the
   receptionist we'd set up for [their spa]: +971-XX-XXX-XXXX. Ask it to book you a facial."*
3. Personalize the dynamic variables with THEIR spa name + services before the call if you can.
4. On the call closing them, you're not selling software — you're replaying the exact moment
   they lose bookings today, solved. That's the close.

---

## 9. Production checklist (after the first "yes")

- [ ] Swap mock functions for real availability + booking (their calendar or a simple Cal.com/Fresha API).
- [ ] Wire `send_whatsapp_confirmation` to the real WhatsApp sender (LeadForge / Meta Cloud API).
- [ ] Per-client dynamic variables (name, services, hours, price list) from a config.
- [ ] Business verification for WhatsApp templates (for outbound confirmations at scale).
- [ ] Call recording + transcript review for the first week to tune the prompt.
- [ ] Warm handoff path (forward to a human for edge cases).

Keep the first version simple. The demo closes; the plumbing follows the "yes".
```
