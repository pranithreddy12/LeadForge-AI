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

### The #1 open lever — discovery precision
Scoring/filtering quality is now solid. The weakest remaining link is **discovery**: broad
"automation" keywords surface adjacent-but-wrong candidates (VC firms, giants). The highest-value
next work is sharpening `query_engine`/`discovery` to find **buyers showing automation intent**
(hiring RevOps/ops, recent HubSpot/Salesforce rollout, "reduce manual work" language) rather than
anything containing the word "automation." This moves leads from C into A/B at the *source*.

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
