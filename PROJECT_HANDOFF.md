# LeadForge AI — Project Handoff & Operating Brief

> Paste this whole document to any AI model before it works on this repo. It explains
> what the product is, how it's built, the non-negotiable principles, exactly where we
> are right now, and how you (the AI) should make decisions going forward.

---

## 1. What this product is

**LeadForge AI** is a production-oriented, AI-native B2B lead-intelligence platform. It is
**NOT** another Apollo/ZoomInfo contact database. Its wedge — the one thing it must do
better than anything else — is:

> **"Know who is likely to buy *right now*, and act on it automatically."**

The core loop the product delivers:
1. **Discover** companies that match an Ideal Customer Profile (ICP).
2. **Enrich** them with real firmographics (size, revenue, funding, HQ, tech stack).
3. **Detect buying signals** (hiring, funding, leadership change, product launch, growth).
4. **Score & grade** each lead (0–100 + A+…F) on fit × intent, with human-readable reasoning.
5. **Rank opportunities** ("why this lead matters right now").
6. **Draft + send outreach**, then **detect replies** and **notify** the user.
7. Run all of this **automatically on a daily schedule**.

If a change makes the product better at *"who will buy now,"* it's aligned. If it just adds
more contact records, it's off-strategy.

---

## 2. Tech stack & topology

**Backend** — FastAPI (Python), SQLAlchemy + Alembic, PostgreSQL + **pgvector**, Redis,
**Celery** workers + **Celery Beat** scheduler. Runs in Docker Compose.
- API service (observed at `http://localhost:8001`), `worker`, `beat`, `postgres`, `redis`.
**Frontend** — Next.js 15 / React / TypeScript / Tailwind / ShadCN UI (observed at `:3001`).
**Auth** — Clerk (with a demo-bypass, see §6). **Billing** — Stripe. **Storage** — S3.
**LLM** — OpenAI SDK pointed at any OpenAI-compatible endpoint (provider abstraction).
**Search/scrape** — Tavily + Serper for search; Playwright for scraping.

Key backend layout:
- `backend/app/ai/` — engines: `icp_engine`, `query_engine`, `qualification_engine`,
  `enrichment_engine`, `signal_engine`, `scoring_engine`, `opportunity_engine`,
  `outreach_engine`, `research_engine`, `chat_engine`, `rag`, plus `openai_client` (provider
  abstraction + circuit breaker), `prompts`, `schemas`, `demo_data`.
- `backend/app/services/` — orchestration over the engines (`discovery`, `enrichment`,
  `scoring`, `telegram`, `email_sender`, …).
- `backend/app/workers/` — Celery tasks: `discovery`, `enrichment`, `signals`, `scoring`,
  `validation`, `outreach`, `research`, `embeddings`, `inbox` (reply poller), and the
  **`workflows`** DAG engine.
- `backend/app/core/` — `config` (pydantic settings), `database`, `security`, `celery_app`.
- `backend/app/cli.py` — `python -m app.cli {seed|keys|daily-workflow}`.

---

## 3. The four non-negotiable principles

These are hard requirements the user has repeatedly enforced. Violating them is a defect.

1. **NOTHING STATIC.** On a *real-provider failure* the system must persist **nothing**
   (engines return `{"_provider_error": True}` and callers skip the write). Demo/canned
   fixtures are allowed **only** when **no API key is configured at all** — never as a
   silent fallback when a configured provider errors out. Mislabeling demo data as a real
   source is a critical bug (it has happened and been fixed before).

2. **FIND BUYERS, NOT COMPETITORS / NOT VENDORS.** Discovery must target companies that
   would *buy* the seller's service, and the qualification engine explicitly excludes direct
   competitors. (See §7 for the size/vendor nuance still open.)

3. **QUALITY OVER VOLUME.** It is better to surface 5 A-grade buyers than 50 noisy rows.
   Junk (listicles, job boards, directories, explainers), off-size, and off-ICP companies
   must be filtered or graded down — not drafted/emailed.

4. **REAL, VERIFIABLE REASONING.** Every score/opportunity must cite concrete, checkable
   facts ("$300M Series D at $3B", "new CRO hire"), not vague filler.

---

## 4. The LLM provider abstraction (important operational detail)

`backend/app/ai/openai_client.py` routes all completions through one OpenAI-compatible client.
- **Priority: OpenAI → Mistral → Gemini → demo.**
- `_JSON_OBJECT_PROVIDERS = {"gemini", "mistral"}` use `response_format={"type":"json_object"}`
  + schema-in-prompt; OpenAI uses strict `json_schema`.
- **Circuit breaker**: opens after 3 consecutive failures, 120s cooldown, fast-fails to avoid
  retry storms under quota exhaustion.
- **Embeddings**: Mistral embeddings are 1024-dim but the pgvector column is 1536-dim, so
  Mistral routes to a local deterministic embedding. Keep this in mind before changing providers.

**Current provider reality (as of this handoff):**
- **Mistral is the active primary** (`mistral-small-latest`). Per-minute limits that recover
  in seconds — chosen specifically because Gemini's free tier kept hitting daily caps.
- **Gemini key is configured but its daily free quota is exhausted** — do not rely on it.
- **Tavily + Serper** keys are live (search works).
- Live keys live in `.env` (gitignored). `.env.example` documents every variable.

---

## 5. The daily automation loop (most recent build — the current focus area)

The user's latest goal: **"This should be an ongoing daily process: find leads daily, draft
messages, and if anyone replies I get a Telegram notification."**

Built on the existing **workflow DAG engine** (`backend/app/workers/workflows.py`). A workflow
is a JSON list of steps, each `{id, type, config, next:[...]}`, executed in topological order
with a shared `ctx` (notably `ctx["company_ids"]`). **Celery Beat** runs `run_due_workflows`
every 5 min and dispatches workflows whose `schedule` is `"daily"`/`"hourly"` when due.

**Step handlers** (`HANDLERS` map): `discover_companies`, `enrich`, `detect_signals`,
`find_contacts`, `validate_emails`, `score_leads`, `filter`, `generate_outreach`,
`send_emails`, `add_to_crm`, `notify_telegram`, `webhook`, `wait`.

**The seeded daily workflow** ("Daily lead engine", created via `python -m app.cli daily-workflow`,
wired to the user's "AI Automation Agency" ICP):
```
discover (10) → enrich → detect_signals → score_leads
  → filter (min_score 65, enforce_icp_size) → generate_outreach (draft)
  → send_emails (Gmail) → add_to_crm (contacted) → notify_telegram (summary)
```

**New integrations added for this loop:**
- `app/services/telegram.py` — Bot API notifications (daily summary + reply alerts). Best-effort:
  never raises; no-ops cleanly if unconfigured.
- `app/services/email_sender.py` — Gmail SMTP send; stamps a unique `Message-ID` into
  `EmailMessage.meta` so replies can be matched. Marks rows `sent`/`bounced`.
- `app/workers/inbox.py` — **reply detection**. Celery Beat task `poll_replies` runs every 5 min,
  reads the Gmail inbox via IMAP, matches an inbound sender to a `sent` EmailMessage's recipient,
  then marks it `replied`, advances the company to CRM stage `replied`, logs a `CRMActivity`,
  and fires a Telegram alert.
- Config added in `core/config.py` + `.env(.example)`: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`,
  `GMAIL_FROM_NAME`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

---

## 6. Demo / local-dev conveniences (don't mistake these for prod behavior)

- **Auth bypass**: when Clerk is unconfigured, the backend (`core/security.py`) seats requests
  as a seeded demo user/org (slug `demo`); the frontend (`lib/clerk-config.ts` → `clerkConfigured`)
  renders "Enter LeadForge" cards instead of Clerk sign-in/up. This is intentional for local testing.
- **Windows/PowerShell environment**: the dev runs on Windows. Avoid non-ASCII characters in
  inline console output (cp1252 `UnicodeEncodeError`). Use the Bash tool for POSIX scripts.

---

## 7. EXACTLY where we are right now (state at handoff)

**The user's directive for this phase (verbatim intent):**
> *"First proceed with lead generation and quality of the application's main point. Then we
> can test the mails and notifications."*

So: **lead-gen quality first; mail/Telegram testing second (blocked on credentials).**

### Just completed — lead-gen quality work
The DB had leads that exposed real quality bugs (industrial-automation false positives + grossly
off-size firms scoring B/C and passing filters). Root cause: scoring only gave a **+15 bonus** for
in-band employee size but **no penalty** for being wildly out of range, so a 26,935-employee
giant (Rockwell) and a 9-person job board (Automate America) scored 66–69. Fixes shipped:

1. **Size-fit penalty** in `scoring_engine._heuristic_subscores`: graduated `log2` penalty (up to
   −60) for companies outside the ICP's employee band; unknown size stays neutral. Result: clean
   separation — true buyers (Synctera/Mercury/Notable) → A/80+; off-size firms → C.
2. **New `enrich` workflow step** inserted before scoring so `employee_count` is known at score time
   (discovery/`persist_candidates` does **not** enrich).
3. **`filter` step hardened**: now uses the **latest** score per company (fixed a duplicate-row
   fan-out from an unordered outerjoin), and supports `enforce_icp_size` (+ explicit
   `employee_min/max`) to **hard-drop** off-band companies regardless of score.
4. Daily workflow filter tightened to `min_score 65 + enforce_icp_size`.
5. Tests green (`tests/test_qualification.py` 8 passed). Daily engine ran **live end-to-end**:
   discovered 3 new → enriched → 22 signals → scored (all C) → filter passed 0 → 0 drafts. The
   3 (Automattic 1,479-emp over cap; LvlUp Ventures = a VC firm; OroCommerce borderline) were
   **correctly graded C and filtered out** — the system refused to email low-fit leads. Reasoning
   cited real facts ($710M ARR, $300M Series D, new CRO hire) — confirming "nothing static" holds.

### Phase 1 DONE — measurable discovery quality (paste-prompt plan 1A–1D)
Full arc complete: 1A baseline → 1B gate (precision 50%→100%) → 1C intent queries → 1D two-track SERP
(buyer-share 0%→~20%) + scoring calibration. Status detail:

- **1A DONE — the measuring stick exists.** Golden set at
  `backend/tests/fixtures/golden_companies.json` (30 hand-labeled rows, archetypes:
  buyer / competitor / vendor / investor_vc / job_board_or_directory / listicle_or_content /
  too_large). `backend/app/ai/eval.py` + `python -m app.cli eval` print: buyer precision/recall,
  false-positives-by-archetype, and grade-band accuracy with the off-size spotlight. Competitor
  anchors are **VoltixIO** and **JOROPI** (owner-picked). Buyer rule encoded: *a buyer CONSUMES
  automation; a vendor/competitor SELLS automation/RevOps/AI-workflow.* The seller's service framing
  is **voice agents, chatbots, RAG, AEO, speed-to-lead** — confirmed by owner.
  - **BASELINE (must be beaten by 1B–1D):** qualification **buyer precision ~50–53% / recall 100%**.
    Recall is stable (all 10 buyers, conf=100 every run); precision drifts ~50–53% across runs because
    the Mistral classifier is non-deterministic even at temp 0 (e.g. UiPath flips buyer↔competitor).
    Treat precision as a ±3% NOISE BAND — 1B must beat it DECISIVELY (a one-run 54% is noise, not a
    win). Leaks through as "buyer": `vendor` 4/5, `too_large` 3–4/4, `investor_vc` 2/3 — exactly the
    IN-BAND classes where size/domain heuristics fail. Competitors 2/2, job boards 4/4, listicles 2/2
    already caught. To dampen the noise when judging 1B, run `eval` 2–3× and compare the mean.
- **Scoring calibration FIX DONE (interjected before 1B).** A latent flooring bug: scoring runs
  *before* contacts are found, so `email_score` floored at 20 and dragged fit-strong buyers down.
  Fix in `scoring_engine.py`: an axis carries weight only when informative — `email_score` excluded
  when no contacts searched; `tech_match` excluded when the ICP sets no stack; absent *intent* axes
  (funding/hiring/growth) excluded when the lead shows SOME signal (a zero-signal lead keeps them all
  and stays cold); a saturating-exponential `sig_score` so one solid signal reads as real intent; and
  a **hard size ceiling** so a grossly off-size firm can't reach B/A no matter how strong its signals
  (the blend alone let strong intent outvote the fit penalty — caught by the live production proof,
  not the fixtures). **Important framing:** this does NOT by itself "fix the all-C daily run" — that
  was a DISCOVERY problem (1B/1C address it). This fix removes a flooring bug that would otherwise
  suppress genuine buyers *once discovery starts surfacing them*, and ensures good-fit buyers aren't
  held at C by contactability absence.
  - **Verification (honest, deterministic):** the scoring eval is heuristic-only (repeatable; the
    LLM's ±15 made sparse-signal fixtures jitter). Assertions are separation-based, NOT post-hoc
    letter-matching: **buyer separation** (every buyer outranks every off-size firm) + **off-size
    guard** (every too_large below B AND below the lowest buyer). Letter-band match is reported
    informational only. `test_qualification.py` 8 passed. **Live production proof** (LLM path, real
    DB rows): in-band buyers grade A/B with `email_score` excluded; off-size firms (Rockwell 27k→D40,
    Automattic 1.5k→C62) capped below the 65 filter. NOTE: an earlier write-up cited "92.9% grade-band
    accuracy" — that number was earned by relaxing two ground-truth bands post-hoc and was DISCARDED;
    do not carry it forward.

### Phase 1 prompt-by-prompt record (all DONE — next is Phase 2/2A, see below)
The arc that closed the discovery-precision gap (50% baseline → 100% gate, buyer-share 0%→~20%):
- **1B DONE** — 8-way classifier (`classify_candidates`/`ai_classify` in `qualification_engine.py`):
  heuristic-first (free/deterministic), then a Mistral `json_object` call for the rest; only `buyer`
  proceeds, `unknown` is held. **Result (stable across 3 runs):** buyer **precision 50%→100%**, **recall
  100%** — every in-band leak closed (vendor 5/5, investor_vc 3/3, competitor 2/2, too_large 4/4, all
  caught). Reasons cite facts ("Zapier sells an automation platform"; "Vanta sells compliance, not
  automation"). Key sharpening that saved recall: vendor = product **IS** automation tooling; a SaaS
  selling something else (compliance/content/planning) is a **buyer** — ignore the "automated" adjective.
  **Heuristic-only floor = 43.5% precision; LLM lift = +56.5pp ⇒ the Mistral call is ESSENTIAL**
  (heuristics can't catch in-band vendor/VC/competitor by what-they-do — do NOT make it optional).
  `unknown`-on-error implemented (hold, never buyer, never drop; logged with candidate ids). Discovery
  wired: buyers proceed, held unknowns are logged and withheld from scoring/outreach. Scoring guards
  (separation 10/10, off-size 4/4) and `test_qualification.py` (8) still green.
  - **1B FOLLOW-UP (not yet built):** persist held `unknown` candidates + a re-classify-on-next-run
    pass so a transient error truly retries rather than just being withheld for the run.
  - **1B SUCCESS BAR (hard gate):** 1B succeeds ONLY IF buyer **precision rises above ~53%** (decisively,
    past the ±3% noise band) AND buyer **recall stays ≥ 95%**. BOTH numbers must be reported every turn.
    Precision without recall is just a gate that rejects real buyers — a classifier that nukes recall to
    win precision has failed. Baseline to beat: precision ~50–53% / recall 100%.
  - **`unknown`-on-provider-error semantics (PIN — do not let "skip" stay ambiguous):** on a provider
    error the classifier labels the candidate **`unknown`** — NOT `buyer`, and NOT dropped. `unknown`
    means "can't classify right now, hold and retry," not "we don't know so let it through." Route
    `unknown` to a holding state (persist flagged → enrichment + re-classify on the next run), NEVER to
    draft/send. So: never proceed to outreach on a provider error, and never silently discard a
    candidate that might be a real buyer. Log the error + candidate id. A transient Mistral rate-limit
    must not permanently suppress a legitimate lead.
  - **Heuristic-vs-LLM eval breakdown (PIN):** the heuristic layer runs FIRST and is reported
    SEPARATELY. `eval` must print two rows: (a) **heuristic-only** precision/recall (the deterministic,
    free, LLM-free floor) and (b) **heuristic + LLM** precision/recall (the ceiling). If the LLM adds
    < ~10pp precision over heuristics alone, heuristics are doing the work and the LLM call can become
    optional (only for `unknown` after heuristics) — faster and immune to the ±3% Mistral noise.
- **1C DONE (with an honest caveat)** — `query_engine.py` now generates INTENT-ANGLE queries
  (`generate_intent_queries`): funding (recent Series A–C) / hiring (RevOps/Ops roles) / pain ("reduce
  manual work", "scaling operations") / tech (HubSpot/Salesforce rollout), each with the ICP's
  industry + employee band + geography baked in, and zero seller-service topic terms. Current year is
  injected so queries target recency (was emitting "2025"). Measured via `python -m app.cli
  discovery-eval` (real Tavily/Serper + gate, pools held ~equal at 12, no volume-chasing):
  **buyer-share 0% → 8%**, LLM-classifications-per-buyer 3.0 → 3.0. **CAVEAT:** the lift is modest
  because the SERP for intent phrases is dominated by **listicles + job boards** (content *about*
  buyers, not buyer homepages) — they crowd the candidate pool and the gate correctly rejects them.
  This is exactly the bottleneck **1D (SERP source filtering)** clears: drop listicles/job-boards at
  collection so the same 12 slots fill with real companies. 1C and 1D are coupled — expect the real
  buyer-share jump after 1D. Forward insight: a bigger unlock later is MINING signal sources (job
  boards, funding news) for company names rather than searching for homepages directly. Provider error
  → `[]`, no demo fallback (nothing-static preserved).
- **1D DONE** — two-track SERP processing in `app/services/serp_filter.py` (`process_hit`):
  (1) DEFENSIVE drop — pure-junk domains + the gate's content/URL heuristics drop listicles/
  directories/aggregate job-search pages at collection so they don't consume candidate slots;
  (2) OFFENSIVE extract — funding-news titles ("Acme raises $20M Series B") and, crucially, a
  company's OWN careers/jobs page (the DOMAIN is the company, the page proves it's hiring) become
  pre-signaled candidates with `Candidate.signal={type,detail}`. Wired into production
  `discover_via_search` and the 3-row `python -m app.cli discovery-eval`.
  - **Result (real run):** topic-keyword baseline = **0% buyer-share (consistently 0 buyers)**;
    intent-angle + two-track = **~17–25% buyer-share (2–3 buyers)**, with careers-page extraction
    firing (3 pre-signaled). That 0→~20% lift is the real Phase-1 discovery win.
  - **Honest caveat:** the precise drop-vs-extract ordering and the "fewer LLM-calls-per-buyer" claim
    sit WITHIN live-SERP + Mistral noise on 12-candidate pools (buyer counts are small integers; SERP
    results vary per call). A single run can't cleanly separate them — run `discovery-eval` 2–3× for a
    mean. The DIRECTIONAL win (baseline 0 vs intent+processing 2–3 buyers) is robust across runs.
  - **Key grounded insight:** the SERP for intent phrases returns listicles/salary-reports + aggregate
    job-search pages, NOT homepages — but real buyers (e.g. Molina Healthcare, BD) appear as their own
    careers postings. Extracting those (clean domain + hiring signal) is what moved the needle; the
    earlier content-path drop was discarding them.
  - **1D FOLLOW-UPS:** (a) ✅ DONE — extracted `signal` now persists as a real `Signal` row in
    `persist_candidates` (kind=hiring/funding, source="discovery_extract"), verified end-to-end, so
    scoring + the UI see the intent and a re-discovery tomorrow isn't cold. (b) Still open — the bigger
    future unlock: deep-read the listicles to extract the MANY companies they name, or query structured
    signal APIs (job-board / funding-data) directly, rather than relying on homepage SERPs.
Re-run `python -m app.cli eval` and `discovery-eval` after each and show before/after.

### Phase 2 — outreach safety + reply loop (NEXT: 2A needs NO credentials)
Phase 1 (discovery quality) is DONE: gate precision 50%→100% (recall 100%), scoring honest +
deterministic, discovery buyer-share 0%→~20%, extracted signals persisted. Phase 2 hardens the
SEND path BEFORE any real email goes out.

- **2A DONE — outreach guardrails (no creds; dry-run verified).** Shipped:
  `classification_status` column on `Company` (migration `0006_classification_status`, applied);
  held-`unknown` candidates now PERSIST with that status and are kept OUT of the scoring pipeline
  (`_step_discover` filters them) — the open 1B follow-up is RESOLVED. `suppression_reason()` in
  `email_sender.py` checks all three conditions independently and is wired into BOTH the draft worker
  and the send path. Send caps (`max_emails_per_run`=25, `max_emails_per_day`=50) enforced before send
  in `_step_send_emails`. Message-ID stamping extracted to `stamp_message_id()` (shared by send + dry-run);
  uniqueness verified (2000/2000). Reply idempotency verified — re-poll fires 0 alerts (guards:
  status=="replied" check + sent_message_index excludes replied + IMAP `\Seen`). **Dry-run
  (`python -m app.cli outreach-dryrun`, no send) showed all three suppression reasons firing
  concretely, decreasing cap headroom, and per buyer the real subject / first line / stamped
  Message-ID** (and a live Mistral 429 → "NO DRAFT, nothing persisted" = nothing-static holding). No
  regressions: gate 100%/100%, separation 10/10, off-size 4/4, tests 8 passed.
  - Spec retained below for reference. NEXT IS 2B (needs the 4 creds).

- **2A spec (reference).** In `app/services/email_sender.py` + `app/workers/outreach.py` +
  the outreach path:
  - **Suppression — check ALL THREE independently (any one suppresses):**
    1. a `sent` (or later) `EmailMessage` row already exists for the company/contact;
    2. the company's CRM `pipeline_stage` is `contacted`/`replied`/beyond, EVEN IF no `EmailMessage`
       row exists (email sent outside LeadForge, or a stage advanced manually);
    3. the candidate is a held `unknown` (classification not yet confirmed) — must NOT be drafted
       until a successful re-classification. **VERIFIED FACT: there is NO `classification_status`
       column on `Company` today** (columns are name/domain/industry/.../`pipeline_stage`/`enriched`/
       `source`/`raw`(JSONB); held candidates are currently withheld from a run but never persisted).
       So held-unknown suppression requires a `classification_status` column (or a `raw`/`pipeline_stage`
       marker) that does not yet exist — **2A must EITHER create it (the open 1B follow-up) OR explicitly
       mark this condition "N/A-until-built" in the dry-run output.** Do not query a field that doesn't
       exist (it will throw or silently skip, and the dry-run won't catch it).
  - Per-run send cap (config) + global daily cap, with Gmail's ~500/day reality in mind.
  - Verify Message-ID uniqueness + that `inbox.py`'s reply matcher (sender→recipient) flips CRM to
    `replied`, logs a `CRMActivity`, and fires Telegram EXACTLY once (no dup alerts on re-poll).
  - **Dry-run only — no live send.** 
  - **2A DONE means the dry-run output shows, FOR EACH company in the qualified pool:** its
    suppression status (and WHY it was skipped if suppressed, incl. held-unknown); its send-cap
    headroom; and the exact email that WOULD be sent — subject, first line, and the **Message-ID that
    would be stamped**. If any field is missing or fabricated, 2A is NOT done. (Requiring the real
    Message-ID forces the actual stamping logic to run, not a mock.)
- **2B — live smoke test (only once the 4 creds are in `.env`).** FORWARD WARNING: smoke-test against
  a test address YOU control BEFORE any real prospect. `inbox.py` matches replies by sender-email →
  sent-recipient-email; if the test mailbox replies from a DIFFERENT From than it received on (some
  clients rewrite the From header), the match silently fails. Verify the round-trip with your own
  address first.

> **FIRST ACTION for the 2B session:** bring Docker up, run
> `docker compose exec api python -m app.cli eval` to confirm green (gate 100%/100%, separation 10/10,
> off-size 4/4, tests 8 passed) AND `docker compose exec api alembic upgrade head` (should report
> already at `0006_classification_status`). Phases 1A–1D and 2A are DONE — do NOT redo them.
>
> **2B is a LIVE smoke test — needs the 4 creds in `.env`:** `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`
> (16-char App Password, 2FA on), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Then: `app.cli keys` to
> confirm live → restart worker+beat → send ONE email to a test address YOU control (NOT a prospect)
> → confirm it lands + the daily Telegram summary arrives → reply from that address → confirm
> `poll_replies` matches within one cycle, flips stage to `replied`, logs a CRMActivity, fires exactly
> one Telegram alert. WARNING (still applies): `inbox.py` matches sender-email → sent-recipient-email;
> if the test mailbox replies from a DIFFERENT From than it received on, the match silently fails —
> verify the round-trip with your own address first.

### Blocked, pending the user
- **Mail + Telegram testing** needs four still-empty `.env` values: `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (Gmail App Password, 2FA required).
  Until then `send_emails`/`notify_telegram`/`poll_replies` no-op gracefully.
- **Caveat to surface**: Gmail SMTP is fine for piloting but caps ~500/day and can flag bulk cold
  mail; real volume would move to SendGrid/Postmark (the sender is swappable by design).

---

## 8. How you (the AI) should operate on this project

1. **Be guided by the wedge (§1) and the four principles (§3).** Especially: never persist on a
   real-provider error; never silently swap in demo data; never optimize for row count.
2. **Quality of leads is "the main point."** When in doubt, improve precision/grading/reasoning
   over adding surface area.
3. **Respect the current phase order**: finish lead-gen quality before mail/notification work,
   unless the user redirects.
4. **Prefer the existing workflow engine** for any "automate this" request — add a step type, don't
   build a parallel scheduler.
5. **Verify with real runs.** This project is tested by running the live pipeline and inspecting
   actual leads/scores/reasoning, not just unit tests. Show concrete before/after evidence.
6. **Watch the provider reality (§4):** Mistral is primary; Gemini is quota-dead; mind the
   embedding-dimension constraint before changing providers.
7. **Don't claim done without evidence.** If a run produced 0 qualified leads, say so and explain
   why (that can be correct behavior, not a failure).
8. **Windows/ASCII-safe output; use Docker Compose** to run/restart `api`/`worker`/`beat`; keys
   visible via `python -m app.cli keys`.

---

## 9. Quick start for a fresh AI session
```bash
docker compose up -d                       # api(:8001), worker, beat, postgres, redis, frontend(:3001)
docker compose exec api python -m app.cli keys           # which providers are LIVE vs demo
docker compose exec api python -m app.cli daily-workflow # (re)create the daily lead engine
# Trigger a run:  POST /api/v1/workflows/{id}/run   then GET /api/v1/workflows/{id}/runs
```
Immediate next action when work resumes: **either** sharpen discovery precision (recommended, the
main quality lever) **or**, once the user supplies the four creds, run the live mail + Telegram test.
