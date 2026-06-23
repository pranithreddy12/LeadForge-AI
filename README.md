# LeadForge AI

**AI-powered lead discovery, validation, and opportunity intelligence platform.**

Finding leads is easy. Knowing *who is likely to buy right now* is hard. LeadForge AI solves
that problem with an AI-native pipeline that turns a one-sentence business description into
an ICP, a ranked list of accounts, validated contacts, buying signals, and personalized
outreach.

## Architecture

```
┌──────────────────┐      ┌──────────────────┐      ┌────────────────────┐
│  Next.js 15 UI   │◀────▶│   FastAPI API    │◀────▶│  PostgreSQL + pgv  │
│  (Clerk auth)    │      │  (Stripe / Clerk)│      │  Redis (cache+bus) │
└──────────────────┘      └────────┬─────────┘      └────────────────────┘
                                   │
                          ┌────────▼─────────┐
                          │   Celery workers │──── OpenAI / Tavily / Serper
                          │   (AI pipeline)  │──── Hunter / NeverBounce
                          └──────────────────┘──── Playwright scraper
```

## Modules

1. **AI ICP Generator** — turn business description into ideal customer profile
2. **Lead Discovery Engine** — multi-source company search (Tavily, Serper, scraping)
3. **Contact Discovery** — find decision makers per account
4. **Buying Signal Detector** — hiring, funding, growth, launches, tech installs
5. **Lead Validation Engine** — weighted scoring with explainable reasoning
6. **AI Opportunity Analyzer** — why-they-buy + best-offer reasoning
7. **Email Validation** — Hunter + NeverBounce
8. **AI Personalized Outreach** — cold email / LinkedIn / follow-ups
9. **CRM** — pipeline, notes, tasks, activities
10. **Dashboard** — KPIs, charts, lead source breakdown
11. **AI Chat Assistant** — natural-language lead search (RAG over your DB + web)
12. **Automation Workflows** — Clay/Zapier-style daily pipelines

## Stack

- **Frontend:** Next.js 15, React 19, TypeScript, TailwindCSS, ShadCN, Framer Motion, Recharts
- **Backend:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2
- **Database:** PostgreSQL 16 + `pgvector` for embeddings
- **Cache/Queue:** Redis 7, Celery
- **Auth:** Clerk
- **Payments:** Stripe
- **AI:** OpenAI (GPT-4o, text-embedding-3-large)
- **Search:** Tavily, Serper
- **Scraping:** Playwright
- **Storage:** AWS S3
- **Deploy:** Docker Compose locally; Railway/AWS in prod

## Quick start

```bash
cp .env.example .env       # fill in your keys
docker compose up -d       # postgres, redis, api, worker, beat, web
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli seed   # optional demo data
open http://localhost:3001
```

API docs: http://localhost:8001/docs

## Repository layout

```
backend/                  FastAPI service + Celery workers
  app/
    api/                  HTTP routes (versioned under /api/v1)
    core/                 config, db, security, celery
    models/               SQLAlchemy ORM
    schemas/              Pydantic models
    services/             business logic (per module)
    ai/                   AI engine: ICP, scoring, opportunity, outreach, RAG
    workers/              Celery tasks
    main.py
  alembic/                migrations
  tests/

frontend/                 Next.js 15 app router
  app/                    routes
  components/             UI components + ShadCN primitives
  lib/                    api client, hooks, utils

infra/
  docker-compose.yml
  Dockerfile.api
  Dockerfile.web

.github/workflows/        CI/CD
```

## License

Proprietary. Built by the LeadForge AI team.
