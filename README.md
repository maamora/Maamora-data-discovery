# Supplier Discovery Service

A backend service that **discovers potential suppliers online**, enriches them with useful details, scores them, and exposes the results through a clean REST API. A human reviews the ranked output and sends outreach — the service never contacts anyone automatically.

> **Team:** Data / Backend Engineering — Adam (lead) & Abdelhamid
> **Duration:** ~6 weeks · **Status:** Kickoff
> **Scope:** This is a **pure backend project.** No frontend. You build the API, the database, the workers, and the pipeline. The "UI" is the auto-generated API docs and a CSV export.

---

## What you're building

A pipeline exposed as a service. Data comes in messy from public sources and comes out clean, enriched, ranked, and queryable over an API.

```
  Collect  ─▶  Enrich  ─▶  Score  ─▶  Serve / Export
 (scraper)   (services)   (rules)    (REST API + CSV)
```

Each stage is a **service module** triggered by an **API endpoint** and run in a **background worker** so long scrapes don't block requests. Build the stages one at a time — get Collect fully working and stored in the database before touching Enrich.

---

## Tech stack

This is a standard, industry-normal backend stack. Learning it well is half the point of the project.

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** | Team is comfortable here |
| API framework | **FastAPI** | Async, typed, auto OpenAPI docs at `/docs` |
| Database | **PostgreSQL** | Real relational DB, not a CSV |
| ORM | **SQLAlchemy 2.x** | Models, queries, relationships |
| Migrations | **Alembic** | Version-controlled schema changes |
| Validation | **Pydantic v2** | Request/response schemas |
| Scraping | **httpx + BeautifulSoup** | Fetch + parse public pages |
| Background jobs | **Celery + Redis** | Run scrapes/enrichment off the request thread |
| Local dev | **Docker Compose** | One command spins up API + DB + Redis + worker |
| Tests | **pytest** | Test services and endpoints |
| Deps | **uv** (or pip + venv) | Fast, reproducible installs |

> Rule of thumb: pick the simplest thing that works and get it running end to end before making it clever. A working scrape stored in Postgres beats a perfect scraper that never ships.

---

## Architecture

Keep the layers separated. The **API layer never scrapes or scores directly** — it calls services. Services hold the business logic. Workers run the slow ones.

```
app/
├── main.py                # FastAPI app entrypoint
├── core/
│   ├── config.py          # Settings loaded from env vars
│   └── logging.py
├── db/
│   ├── session.py         # SQLAlchemy engine + session
│   └── base.py
├── models/                # SQLAlchemy ORM models (DB tables)
│   ├── supplier.py
│   └── scrape_job.py
├── schemas/               # Pydantic schemas (API in/out)
│   ├── supplier.py
│   └── scrape_job.py
├── api/
│   └── routes/
│       ├── suppliers.py   # /suppliers endpoints
│       └── scrape_jobs.py # /scrape-jobs endpoints
├── services/              # Business logic — the core of the project
│   ├── scraper.py         # Collect: fetch + parse public sources
│   ├── enrichment.py      # Enrich: fill in missing fields
│   ├── scoring.py         # Rank: apply scoring rules
│   └── outreach.py        # Draft (never send) outreach messages
├── workers/
│   ├── celery_app.py
│   └── tasks.py           # Celery tasks wrapping the services
└── tests/
alembic/                   # Migrations
docker-compose.yml
pyproject.toml
.env.example
```

---

## Data model

Two core tables. Every supplier is one row; every scrape run is tracked so you can see what produced what.

**`suppliers`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID / int PK | |
| `name` | text | Supplier / company name |
| `category` | text, nullable | electronics, home, beauty… |
| `website` | text, nullable | Store or site URL |
| `contact` | text, nullable | Public phone / email / WhatsApp |
| `location` | text, nullable | City / region |
| `price_signal` | enum, nullable | `low` / `mid` / `high` |
| `source` | text | Which site it came from |
| `score` | float, nullable | Set by the scoring service |
| `status` | enum | `raw` → `enriched` → `scored` |
| `raw_data` | JSONB | Whatever was scraped, kept for debugging |
| `created_at` / `updated_at` | timestamptz | |

**`scrape_jobs`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID / int PK | |
| `source` | text | Site being scraped |
| `status` | enum | `pending` / `running` / `done` / `failed` |
| `suppliers_found` | int | |
| `started_at` / `finished_at` | timestamptz | |
| `error` | text, nullable | If it failed, why |

> Any change to these tables goes through an **Alembic migration** — never edit the DB by hand.

---

## API endpoints

The whole pipeline is driven through the API. FastAPI auto-generates interactive docs at `/docs`.

| Method | Path | Does |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/scrape-jobs` | Start a scrape of a source (async → returns job id) |
| `GET` | `/scrape-jobs/{id}` | Check a scrape job's status |
| `GET` | `/scrape-jobs` | List scrape jobs |
| `GET` | `/suppliers` | List suppliers — filter by `category`, `min_score`, `status`; paginated |
| `GET` | `/suppliers/{id}` | One supplier's full detail |
| `POST` | `/suppliers/enrich` | Kick off enrichment for `raw` suppliers (async) |
| `POST` | `/suppliers/score` | Run scoring across all enriched suppliers |
| `GET` | `/suppliers/{id}/outreach` | Get the drafted outreach message (draft only) |
| `GET` | `/suppliers/export` | Export ranked suppliers as CSV |

**Typical flow:** `POST /scrape-jobs` → poll `GET /scrape-jobs/{id}` → `POST /suppliers/enrich` → `POST /suppliers/score` → `GET /suppliers?min_score=...` or `GET /suppliers/export`.

---

## Getting started

**Prerequisites:** Docker + Docker Compose installed. That's it — the DB, Redis, and worker all run in containers.

```bash
# 1. Clone and enter
git clone <repo-url> && cd supplier-discovery-service

# 2. Copy env template and fill it in
cp .env.example .env

# 3. Bring up API + Postgres + Redis + Celery worker
docker compose up --build

# 4. Apply database migrations
docker compose exec api alembic upgrade head

# 5. Open the interactive API docs
# → http://localhost:8000/docs
```

Run without Docker (if you prefer local):

```bash
uv sync                       # or: python -m venv .venv && pip install -e .
alembic upgrade head
uvicorn app.main:app --reload         # API
celery -A app.workers.celery_app worker --loglevel=info   # worker (separate terminal)
```

---

## Environment variables

Everything configurable lives in `.env` — **never hardcode secrets or commit `.env`.** See `.env.example`.

```
DATABASE_URL=postgresql+psycopg://user:pass@db:5432/suppliers
REDIS_URL=redis://redis:6379/0
SCRAPE_DELAY_SECONDS=2          # politeness delay between requests
SCRAPE_USER_AGENT=SupplierDiscoveryBot/1.0
LOG_LEVEL=INFO
```

---

## Background jobs

Slow work (scraping, enrichment) runs as Celery tasks so the API stays responsive.

- `tasks.scrape_source(source)` — fetch + parse a source, write `raw` suppliers
- `tasks.enrich_supplier(supplier_id)` — fill missing fields, set status `enriched`
- `tasks.score_all()` — apply scoring rules, set status `scored`

An endpoint enqueues the task and returns immediately with a job/id; the client polls for status. Keep tasks **idempotent** — running one twice shouldn't create duplicates.

---

## Testing

```bash
docker compose exec api pytest
```

Aim for: unit tests on each service (scraper parsing, scoring rules, enrichment logic) and a couple of endpoint tests hitting a test database. You don't need 100% coverage — cover the logic that would silently break.

---

## Roadmap (6 weeks, 2 devs)

| Week | Goal |
|---|---|
| **1** | Foundations: repo, Docker Compose (API + Postgres + Redis + worker), FastAPI skeleton, SQLAlchemy models, first Alembic migration, `/health` green. |
| **2** | **Collect.** Scraper service + `POST /scrape-jobs` + Celery task that scrapes one source and stores ~50 `raw` suppliers. `GET /suppliers` lists them. |
| **3** | **Enrich (part 1).** Enrichment service + task; fill `category`, `location`, `website`. Add filtering + pagination to `GET /suppliers`. |
| **4** | **Enrich (part 2) + robustness.** Fill `contact`, `price_signal`. Add retries, rate limiting (`SCRAPE_DELAY_SECONDS`), and error handling on failed pages. |
| **5** | **Score.** Scoring service + `POST /suppliers/score`. Ranking reflected in `GET /suppliers?min_score=...`. |
| **6** | **Serve / Output.** `GET /suppliers/export` (CSV), outreach-draft service + endpoint, tests, polish, finalize this README + `/docs`. |

---

## Definition of done

- [ ] `docker compose up` brings the whole service up; migrations apply cleanly.
- [ ] Hitting the endpoints runs the full pipeline: scrape → enrich → score.
- [ ] `GET /suppliers` returns filtered, paginated, ranked results.
- [ ] `GET /suppliers/export` returns a clean CSV of ranked suppliers.
- [ ] Each supplier has a drafted outreach message available (draft only, never sent).
- [ ] At least **50 real suppliers** in the database, enriched and scored.
- [ ] Core services have tests; API docs render at `/docs`.
- [ ] This README lets a new dev run the project from scratch.

---

## Suggested split (2 backend devs)

Decide between yourselves, but a clean division:

- **Adam (lead)** — API layer + database: FastAPI routes, SQLAlchemy models, Alembic migrations, query/filtering/pagination, scoring service. Owns the service's shape and coordinates.
- **Abdelhamid** — Pipeline internals: scraper + enrichment services, Celery tasks, rate limiting, retries, robustness. Owns the part that touches the messy outside world.

You meet in the middle where endpoints enqueue tasks and tasks write to the DB.

---

## Ground rules

- **Public data only.** Respect each site's `robots.txt` and terms of use.
- **Be polite.** Honor `SCRAPE_DELAY_SECONDS`; don't hammer any site.
- **Drafts only.** The service drafts outreach; it never sends. A human always sends.
- **Migrations for every schema change.** Never edit the database by hand.
- **No secrets in git.** Config comes from `.env`; commit `.env.example` only.
- **Services stay decoupled from the API.** An endpoint calls a service; it doesn't scrape inline.

## When you get stuck

This project is yours to own. Read the FastAPI / SQLAlchemy / Celery docs — they're excellent — search the error, and try a smaller reproduction first. Talk to each other before escalating; two backend devs means someone probably already hit it. The goal is for you to solve it. That's the whole point of owning it.
