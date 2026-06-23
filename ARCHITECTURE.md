# Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            User (browser)                                 │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │  Clerk session
                ┌──────────────▼──────────────┐
                │   Next.js 15 (app router)   │  app/(app)/* protected by middleware
                │   ShadCN · Framer · Recharts│
                └──────────────┬──────────────┘
                               │  /api/backend/* ──rewrite──▶ FastAPI /api/v1/*
                ┌──────────────▼──────────────┐
                │      FastAPI service        │
                │  ───────────────────────    │
                │  api/v1/routes/*            │
                │  services/* (business)      │
                │  ai/* (LLM engines)         │
                │  workers/* (Celery tasks)   │
                └──┬───────────────┬──────────┘
                   │               │
        ┌──────────▼──┐         ┌──▼─────────────┐
        │ PostgreSQL  │         │     Redis      │
        │ + pgvector  │         │ broker+cache   │
        └─────────────┘         └────┬───────────┘
                                     │
                              ┌──────▼──────┐    ┌──────────────────┐
                              │ Celery work │───▶│  OpenAI / Tavily │
                              │ + beat      │───▶│  Serper / Hunter │
                              └──────┬──────┘    │  NeverBounce     │
                                     │           └──────────────────┘
                              ┌──────▼──────┐
                              │  Playwright │
                              │  Chromium   │
                              └─────────────┘
```

## Module → file map

| Module                         | Backend                                              | Frontend                                  |
|--------------------------------|------------------------------------------------------|-------------------------------------------|
| **1. AI ICP Generator**        | `app/ai/icp_engine.py`, `routes/icps.py`             | `app/(app)/icp/page.tsx`                  |
| **2. Lead Discovery**          | `services/discovery.py`, `services/search.py`        | `app/(app)/leads/page.tsx`                |
| **3. Contact Discovery**       | `services/contacts.py`                               | lead detail → "Find contacts"             |
| **4. Buying Signal Detector**  | `ai/signal_engine.py`, `services/signals.py`         | `app/(app)/signals/page.tsx`              |
| **5. Lead Validation Engine**  | `ai/scoring_engine.py`, `services/scoring.py`        | lead detail → "Score"                     |
| **6. Opportunity Analyzer**    | `ai/opportunity_engine.py`                           | lead detail → "Why this account, now"     |
| **7. Email Validation**        | `services/email_validation.py`                       | contacts page · validate buttons          |
| **8. AI Personalized Outreach**| `ai/outreach_engine.py`, `workers/outreach.py`       | lead detail → Outreach tab                |
| **9. CRM**                     | `services/crm.py`, `routes/crm.py`                   | `app/(app)/crm/page.tsx`                  |
| **10. Dashboard**              | `services/dashboard.py`, `routes/dashboard.py`       | `app/(app)/dashboard/page.tsx`            |
| **11. AI Chat Assistant**      | `ai/chat_engine.py`, `routes/chat.py`                | `app/(app)/chat/page.tsx`                 |
| **12. Workflows**              | `workers/workflows.py`, `routes/workflows.py`        | `app/(app)/workflows/page.tsx`            |

## Data flow — single example (Module 2 → 4 → 5)

1. User clicks **Discover** in `/leads`.
2. `POST /api/v1/companies/discover` enqueues `discover_companies_task`.
3. Worker calls Tavily + Serper, dedupes by domain, inserts `Company` rows.
4. For each new company it fans out `detect_signals_task`.
5. `detect_signals_task` collects jobs / funding / news / careers content,
   passes raw text to `ai/signal_engine.py` (GPT-4o, `response_format=json_schema`),
   and writes `Signal` rows.
6. UI polls `/companies` and `/signals` via React Query; the lead detail
   page surfaces signals immediately.
7. The user (or workflow) calls `POST /scoring/score/:c/:icp`:
   `scoring_engine` blends heuristics + LLM-adjusted subscores into the
   final 0–100 score and persists a `LeadScore`. The opportunity analyzer
   layers the `why-now / suggested offer / suggested contact` reasoning.

## Multi-tenancy

Every row carries `organization_id`. Clerk's active org id (`org_id` claim
on the session JWT) is resolved on each request to the local
`Organization` row by `services/tenant.ensure_user`. Every query is
scoped through `current_org` so cross-org access is impossible.

## Embeddings & semantic search

- `Company.embedding` is a `vector(3072)` column (pgvector).
- `workers/embeddings.embed_pending_rows` (beat: every 10 min) backfills
  any row marked `embedding_pending=true`.
- `ai/rag.semantic_company_search` does cosine search via the IVFFLAT
  index `ix_companies_embedding_ivf`.

## Workflow engine

`workers/workflows.py` interprets a JSON DAG of step nodes
(`{id, type, config, next}`). Step types map to handler functions:
`discover_companies`, `detect_signals`, `find_contacts`,
`validate_emails`, `score_leads`, `generate_outreach`, `filter`,
`add_to_crm`, `webhook`, `wait`. A context object carries
`company_ids` / `contact_ids` / `icp_id` between steps. Beat
(`run_due_workflows`) wakes every 5 minutes and dispatches due workflows
based on their `schedule` field.

## Reliability

- All Celery tasks are idempotent on dedupe keys (domain, signal label).
- All external HTTP calls have explicit timeouts and `try/except` logging.
- Errors return a structured `{code, message, ...}` envelope via
  `core/errors.register_error_handlers`.
- Rate limits live in `core/rate_limit` (Redis fixed-window counters).
