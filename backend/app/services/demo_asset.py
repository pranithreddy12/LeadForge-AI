"""Per-lead demo asset — a shareable WhatsApp-style mockup showing THAT clinic's AI
receptionist catching an after-hours enquiry and booking a consultation.

GoHighLevel sells its AI Employee by SHOWING it. A one-line pitch ("we set up an AI
receptionist") loses to a screenshot of the thing working, with the prospect's own
name on it. This builds that screenshot-able page from the lead's real facts.

HONESTY BOUNDARY: this is a clearly-labelled SIMULATION the sender shows a prospect,
not a claim that the clinic runs this system and not a copy of their real WhatsApp. It
carries a visible "Demo · simulated · not affiliated" disclaimer, uses only real facts
we hold about the business, and books a CONSULTATION (DHA-compliant — never a treatment
or an outcome promise). It must never be presented as the clinic's genuine record.
"""
from __future__ import annotations

import html as _html

from app.models.company import Company


def _city(company: Company) -> str:
    p = (company.raw or {}).get("places") or {}
    addr = p.get("city") or ""
    if not addr:
        full = p.get("address") or p.get("formatted_address") or ""
        for token in ("Dubai", "Abu Dhabi", "Sharjah", "Ajman"):
            if token.lower() in full.lower():
                return token
    return addr or "Dubai"


def _scenario(signal_kinds: set[str]) -> dict:
    """Pick the after-hours framing from the lead's strongest real signal, so the demo
    dramatises THEIR gap, not a generic one."""
    if "limited_hours" in signal_kinds:
        return {"when": "Friday, 9:47 PM", "closed_line": "we're closed right now",
                "hook": "outside opening hours"}
    if "no_online_booking" in signal_kinds:
        return {"when": "Tuesday, 10:52 PM", "closed_line": "our team's offline right now",
                "hook": "with no online booking, this would normally wait for morning"}
    if "missed_calls_complaint" in signal_kinds:
        return {"when": "Saturday, 8:15 PM", "closed_line": "our line's busy right now",
                "hook": "the call that would've gone to voicemail"}
    return {"when": "Wednesday, 10:20 PM", "closed_line": "we're closed right now",
            "hook": "after hours"}


def build_demo_html(company: Company, signal_kinds: set[str], *,
                    sender_name: str = "LeadForge", doctor: str | None = None) -> str:
    name = company.name
    city = _city(company)
    sc = _scenario(signal_kinds)
    dr = doctor or "our specialist"
    e = _html.escape
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "AI"

    # A scripted, DHA-safe conversation: enquiry after hours -> instant reply -> books a
    # CONSULTATION (never a treatment / never an outcome promise).
    msgs = [
        ("in", f"Hi, do you have any availability this week? Saw your page 🙂", sc["when"]),
        ("out", f"Hi! Thanks for reaching out to {name} 💙 {sc['closed_line'].capitalize()}, "
                f"but I can help you book a consultation. Is there a treatment you're "
                f"considering, or would you like general advice first?", "9:47 PM"),
        ("in", "Considering something for my skin, but not sure what suits me.", "9:48 PM"),
        ("out", f"Totally understandable — a consultation with {dr} is the best first step "
                f"so it's tailored to you. Next available: Saturday 11:00 AM or Sunday "
                f"4:30 PM. Which works better?", "9:48 PM"),
        ("in", "Sunday 4:30 works", "9:49 PM"),
        ("out", f"Booked ✅ You're set for a consultation on Sunday at 4:30 PM with {name}. "
                f"I'll send a reminder the day before. Anything else I can help with?", "9:49 PM"),
        ("in", "That's great, thank you!", "9:50 PM"),
    ]

    bubbles = []
    for side, text, ts in msgs:
        cls = "out" if side == "out" else "in"
        bubbles.append(
            f'<div class="row {cls}"><div class="bubble {cls}">{e(text)}'
            f'<span class="ts">{e(ts)}</span></div></div>')
    chat = "\n".join(bubbles)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(name)} — AI receptionist demo</title>
<style>
  :root {{ --wa:#e5ddd5; --out:#dcf8c6; --in:#ffffff; --head:#075e54; --ink:#111b21;
    --muted:#667781; --accent:#25d366; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:#0b141a; color:var(--ink); display:flex; flex-direction:column;
    align-items:center; padding:26px 14px 40px; min-height:100vh; }}
  .tag {{ color:#8aa0ad; font-size:12px; letter-spacing:.14em; text-transform:uppercase;
    margin-bottom:14px; }}
  .phone {{ width:100%; max-width:390px; border-radius:30px; overflow:hidden;
    box-shadow:0 24px 60px rgba(0,0,0,.5); border:1px solid #22303a; background:var(--wa); }}
  .head {{ background:var(--head); color:#fff; display:flex; align-items:center; gap:11px;
    padding:13px 14px; }}
  .av {{ width:40px; height:40px; border-radius:50%; background:#128c7e; display:grid;
    place-items:center; font-weight:700; font-size:15px; }}
  .who {{ line-height:1.25; }}
  .who b {{ font-size:15.5px; display:block; }}
  .who span {{ font-size:12px; color:#bfe6df; }}
  .demo-pill {{ margin-left:auto; background:#ffd54a; color:#3a2c00; font-size:10px;
    font-weight:800; letter-spacing:.08em; padding:3px 8px; border-radius:999px; }}
  .chat {{ padding:16px 12px 8px; display:flex; flex-direction:column; gap:8px;
    background-image:linear-gradient(rgba(229,221,213,.6),rgba(229,221,213,.6)); }}
  .daysep {{ align-self:center; background:#d9e7d3; color:#5b6b60; font-size:11px;
    padding:3px 10px; border-radius:8px; margin:2px 0 6px; }}
  .row {{ display:flex; }}
  .row.out {{ justify-content:flex-end; }}
  .bubble {{ max-width:82%; padding:7px 10px 18px; border-radius:9px; font-size:14px;
    line-height:1.42; position:relative; box-shadow:0 1px .5px rgba(0,0,0,.13); }}
  .bubble.in {{ background:var(--in); border-top-left-radius:2px; }}
  .bubble.out {{ background:var(--out); border-top-right-radius:2px; }}
  .ts {{ position:absolute; right:9px; bottom:4px; font-size:10px; color:var(--muted); }}
  .cap {{ background:#0b141a; color:#9fb0bb; font-size:12.5px; text-align:center;
    padding:14px 18px; line-height:1.5; }}
  .cap b {{ color:#d7e2e8; }}
  .foot {{ max-width:390px; color:#5c6b74; font-size:11px; text-align:center;
    margin-top:16px; line-height:1.55; }}
</style></head>
<body>
  <div class="tag">Preview · how it would sound</div>
  <div class="phone">
    <div class="head">
      <div class="av">{e(initials)}</div>
      <div class="who"><b>{e(name)}</b><span>AI receptionist · online</span></div>
      <div class="demo-pill">DEMO</div>
    </div>
    <div class="chat">
      <div class="daysep">{e(sc['when'])} — {e(sc['hook'])}</div>
      {chat}
    </div>
    <div class="cap">↑ This enquiry came in at <b>9:47 PM</b>, while {e(name)} was closed.
      Answered in seconds. Consultation booked. Nothing lost to the morning.</div>
  </div>
  <div class="foot">
    Demo preview created by {e(sender_name)} to show how an AI receptionist could handle
    after-hours enquiries for {e(name)} in {e(city)}. Simulated conversation for
    illustration — not affiliated with, operated by, or endorsed by {e(name)}.
  </div>
</body></html>"""
