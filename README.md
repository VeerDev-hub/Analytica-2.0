# Analytica Studio 2.0

Analytica Studio is a web app for getting tabular data ready for machine learning. You upload a CSV, Excel or Parquet file, explore it, clean it, engineer features, check it is ready to train on, and export the prepared data along with the code that reproduces it. A built-in assistant answers questions about the data. Every number it gives comes from a SQL query you can open and check.

Version 2.0 rewrites the original single-user Streamlit app (kept in [`legacy/`](legacy/)) as a multi-user platform: a FastAPI API, Celery workers, PostgreSQL, S3 object storage, a React frontend and Terraform for AWS.

![Architecture](docs/System%20Design/architecture-full.png)

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Running tests and linters](#running-tests-and-linters)
- [How it works](#how-it-works)
- [API overview](#api-overview)
- [Deploying to AWS](#deploying-to-aws)
- [Design documents](#design-documents)

---

## Features

Each project follows the same workflow, and each step has its own page in the sidebar:

| Section | What it does |
|---|---|
| **Data** | Browse every row of the current dataset version. Inspect any column from its type badge. |
| **Explore** | Summary statistics, data-quality alerts with one-click fixes, column profiles, correlations and a chart builder. |
| **Clean** | Fix types, text, missing values, duplicates, outliers, rows and columns. Each step can be previewed on a sample before it runs. |
| **Features** | Split into train/validation/test, then encode, scale, transform, select features, reduce dimensions (PCA) and rebalance classes. |
| **Validate** | Readiness checks (leakage, missing values, types, class balance and more) and quick baseline model scores. |
| **Export** | Download the prepared data plus the code that reproduces it. |
| **Assistant** | Ask questions in plain language. Answers are grounded in read-only SQL queries, which are shown alongside each answer. |

Also included:

- **Versioned datasets.** Every pipeline step produces an immutable Parquet version. You can undo, redo, reorder, reset, or switch back to any earlier version.
- **Recipes.** Save a pipeline and apply it to another project.
- **Background jobs.** Ingest, pipeline runs, baselines and exports run in Celery. Progress is streamed to the UI.
- **Accounts.** Email/password sign-in plus optional Google and GitHub OAuth, per-user storage quotas, and account deletion.
- **Admin console.** Usage statistics, user management, app settings, and an estimate of LLM cost.

### Pipeline steps

| Phase | Steps |
|---|---|
| Cleaning (row-wise, stateless) | `drop_columns`, `keep_columns`, `rename_columns`, `change_type`, `trim_text`, `replace_values`, `drop_duplicates`, `drop_missing_rows`, `filter_rows`, `formula`, `datetime_features` |
| Split | `split` (train / validation / test) |
| Fitted on train only | `impute`, `outliers`, `rare_group`, `one_hot`, `ordinal`, `label_encode`, `target_encode`, `frequency_encode`, `hash_encode`, `scale`, `numeric_transform`, `binning`, `text_features`, `feature_select`, `pca` |
| Resampling | `random_under`, `random_over`, `smote`, `adasyn`, `tomek` |

Steps that learn statistics are fitted on the training partition only, which prevents leakage into validation and test data.

### Exports

| Kind | Formats |
|---|---|
| `dataset` | `csv`, `parquet`, `xlsx`, `npy` |
| `script` | `py`: standalone pandas/sklearn script that reproduces the pipeline |
| `notebook` | `ipynb` |
| `pipeline` | `json` |
| `pytorch` / `tensorflow` | `py`: model starter templates |
| `report` | `html` |

Generated scripts embed the values learned during fitting (fill values, bounds, category lists, scaler parameters). Running a script on the original file therefore reproduces the exported data exactly, without refitting.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 7, Tailwind CSS 4, TanStack Query and Table, Zustand, React Router 7, Plotly.js |
| API | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Workers | Celery 5 (worker and beat) on Redis |
| Data engine | pandas, NumPy, PyArrow, DuckDB, SciPy, scikit-learn, imbalanced-learn |
| Database | PostgreSQL 16 with pgvector |
| Object storage | S3 (SeaweedFS locally, AWS S3 when deployed) |
| Assistant | Google Gemini API (free tier works), with function calling and a sandboxed DuckDB SQL tool |
| Auth | JWT access and refresh tokens, Argon2 password hashing, Google and GitHub OAuth |
| Infrastructure | Docker Compose (local); Terraform on AWS: ECS Fargate, RDS, ElastiCache, S3, CloudFront, CloudWatch |

---

## Repository layout

```
.
├── backend/                 FastAPI app, Celery tasks, data engine, tests
│   ├── alembic/             Database migrations
│   ├── app/
│   │   ├── api/v1/          HTTP routes (auth, projects, datasets, pipeline, eda, validate, chat, jobs, admin)
│   │   ├── chat/            Assistant orchestrator, retriever, read-only SQL sandbox
│   │   ├── core/            Settings, DB session, security, errors, logging
│   │   ├── engine/          Pure data logic, independent of web and DB code
│   │   │   ├── loaders/     CSV/Excel/Parquet loading with encoding/delimiter detection
│   │   │   ├── profiling/   Column profiles and semantic types
│   │   │   ├── transforms/  Transform contract, registry, cleaning and ML steps
│   │   │   ├── pipeline/    Runs steps in order, respecting the split boundary
│   │   │   ├── readiness/   Readiness checks and baseline models
│   │   │   ├── charts/      Chart specs → Plotly figures
│   │   │   └── codegen/     Generates the exported script and notebook
│   │   ├── models/          SQLAlchemy models
│   │   ├── repositories/    Access-control queries
│   │   ├── schemas/         Pydantic schemas
│   │   ├── services/        Business logic (datasets, versions, pipeline, exports, quota, OAuth…)
│   │   ├── storage/         S3 and local storage backends, Parquet cache
│   │   └── tasks/           Celery app and tasks (ingest, pipeline, exports, maintenance)
│   └── tests/               unit/ and integration/
├── frontend/                React single-page app
│   └── src/
│       ├── api/             API client and React Query hooks
│       ├── app/             Router, shell, auth gate, providers
│       ├── components/      Shared UI
│       ├── features/        One folder per page/feature
│       └── store/           Zustand stores (auth, theme, workspace)
├── infra/
│   ├── local/               SeaweedFS S3 credentials for Docker Compose
│   └── terraform/           AWS modules, stack and dev/prod environments
├── docs/System Design/      Architecture, ER, class, flow and deployment diagrams
├── legacy/                  Original Streamlit app (v1), kept for reference
├── docker-compose.yml
└── .env.example
```

---

## Getting started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2
- [Node.js](https://nodejs.org/) 20 or later, for the frontend
- Optional: a free [Gemini API key](https://aistudio.google.com/apikey), needed only for the Assistant

### 1. Configure the environment

```bash
cp .env.example .env
```

The defaults work for local development. To enable the Assistant, set `GEMINI_API_KEY`. To make your account an admin, add your email to `ADMIN_EMAILS`.

### 2. Start the backend stack

```bash
docker compose up --build
```

This starts:

| Service | Purpose | Host port |
|---|---|---|
| `api` | FastAPI. Runs `alembic upgrade head` first and hot-reloads on code changes. | `8000` |
| `worker` | Celery worker | – |
| `beat` | Celery beat: hourly purge of deleted projects and expired exports | – |
| `postgres` | PostgreSQL 16 + pgvector | `5432` |
| `redis` | Celery broker and cache | `6380` |
| `s3` | SeaweedFS S3-compatible object store | `8333` |
| `storage-init` | One-shot job that creates the data bucket | – |

If any of these host ports is already in use, change the matching `*_HOST_PORT` value in `.env`.

- API docs (Swagger): <http://localhost:8000/api/docs>
- Health check: <http://localhost:8000/api/v1/health>

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> and register an account. In development, Vite proxies `/api` to `http://localhost:8000`. You can change the target with `VITE_API_PROXY_TARGET`.

### Database migrations

Migrations run automatically when the `api` container starts. To create a new one:

```bash
docker compose exec api alembic revision --autogenerate -m "describe the change"
docker compose exec api alembic upgrade head
```

---

## Configuration

Settings are read from environment variables (see [`backend/app/core/config.py`](backend/app/core/config.py)). The most important ones:

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `local` | `local`, `dev`, `prod` or `test` |
| `JWT_SECRET` | dev placeholder | **Required** outside `local`/`test`. The app refuses to start with the default value. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list |
| `DATABASE_URL` | local Postgres | On AWS it is assembled from `DB_HOST` / `DB_PASSWORD` instead |
| `S3_BUCKET`, `S3_ENDPOINT_URL` | `analytica-data`, SeaweedFS | Leave the endpoint empty on AWS to use the default endpoint and the IAM role |
| `GEMINI_API_KEY` | empty | Chat endpoints return `503` until this is set |
| `CHAT_MODEL` | `gemini-2.5-flash` | Model used by the Assistant |
| `ADMIN_EMAILS` | empty | These users become admins when they sign in |
| `PUBLIC_APP_URL` | `http://localhost:5173` | Base URL for OAuth redirects |
| `GOOGLE_CLIENT_ID` / `_SECRET` | empty | Google sign-in appears only when both are set |
| `GITHUB_CLIENT_ID` / `_SECRET` | empty | GitHub sign-in appears only when both are set |
| `MAX_UPLOAD_MB` | `200` | Upload size limit |
| `MAX_ROWS` | `2000000` | Row limit per dataset |

OAuth callback URLs to register with each provider:

```
<PUBLIC_APP_URL>/api/v1/auth/oauth/google/callback
<PUBLIC_APP_URL>/api/v1/auth/oauth/github/callback
```

---

## Running tests and linters

### Backend

The tests use a separate `<db>_test` database (created and migrated automatically), local file storage instead of S3, and Celery tasks that run inline. Postgres must be running.

```bash
docker compose exec api pytest                 # all tests
docker compose exec api pytest tests/unit      # engine only, no DB needed
docker compose exec api ruff check .
docker compose exec api ruff format --check .
```

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

---

## How it works

### Datasets and versions

1. An upload is stored in S3 and a Celery **ingest** job is queued (`202 Accepted` + job id).
2. The loader detects the encoding and delimiter, converts types only when no values would be lost, and de-duplicates column names. The result is saved as **version 1**, an immutable Parquet file. Each column is then profiled.
3. Each pipeline step produces a new version. Versions are cached locally (that cache is safe to delete at any time) and can be selected as current.

### The transform contract

Every pipeline step is a `Transform` subclass ([`engine/transforms/base.py`](backend/app/engine/transforms/base.py)):

```python
validate(params, ctx) -> list[Issue]         # checked before running
fit(train_df, params, ctx) -> dict           # learned state (empty if stateless)
transform(df, params, state, ctx) -> DataFrame
describe(params) -> str                      # human-readable label in the pipeline panel
code(params) -> str                          # snippet for the exported script
```

Each step belongs to a phase: `pre_split` (row-wise, stateless), `split` (the single split step) or `post_split` (fitted on train rows only). The engine package has no dependency on web or database code, and `tests/unit/test_engine_purity.py` enforces this.

### Jobs

Long-running work goes through Celery. Clients follow a job with `GET /api/v1/jobs/{id}` or the server-sent event stream at `/jobs/{id}/events`, and can cancel it with `POST /jobs/{id}/cancel`.

### Assistant safety

- The model sees only the schema, column descriptions, a small masked sample, and tool results. It never sees the whole file.
- Numbers must come from the `run_sql` tool. Each executed query is stored as a citation and shown in the UI with its rows.
- SQL runs in an in-memory DuckDB sandbox. Columns marked private are never loaded, file, network and extension access is disabled, and only a single `SELECT`/`WITH` statement is accepted. Results are capped at 200 rows and a 10-second timeout.
- Actions that change data (such as adding a pipeline step) require the user's explicit approval.

---

## API overview

All routes are prefixed with `/api/v1`. The full interactive reference is at `/api/docs`.

| Area | Endpoints |
|---|---|
| Health | `GET /health`, `GET /meta` |
| Auth | `POST /auth/register`, `/login`, `/refresh`, `/logout`; `GET/PATCH/DELETE /auth/me`; `GET /auth/me/storage`; OAuth start/callback |
| Projects | `GET/POST /projects`; `GET/PATCH/DELETE /projects/{id}`; `POST /projects/{id}/free-space` |
| Datasets | `POST /projects/{id}/datasets`; versions, rows, columns, overview |
| EDA | Column detail, chart builder, correlations |
| Pipeline | Step catalog; add/preview/edit/delete/reorder steps; undo/redo/reset; split; recipes |
| Validate | Readiness, baseline models, exports and downloads |
| Chat | Sessions, messages (streamed), action approval |
| Jobs | Status, cancel, event stream |
| Admin | Stats, users, settings |

---

## Deploying to AWS

Infrastructure is defined in [`infra/terraform`](infra/terraform):

- `modules/network`: VPC, subnets, routing
- `modules/data`: RDS PostgreSQL, ElastiCache Redis, encrypted S3 data bucket, KMS, Secrets Manager
- `modules/compute`: ECR, ECS Fargate services (api, worker, beat), ALB, autoscaling
- `modules/edge`: CloudFront and the S3 bucket for the SPA. `/api/*` is routed to the ALB, so the app is served from a single origin.
- `modules/observability`: CloudWatch logs, alarms and dashboards
- `stack/`: wires the modules into one environment
- `envs/dev`, `envs/prod`: per-environment roots

```bash
cd infra/terraform/envs/dev
cp backend.hcl.example backend.hcl     # fill in your state bucket/table
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Then build the backend image, push it to the ECR repository, build the frontend (`npm run build`) and upload `frontend/dist` to the web bucket. The CI/CD flow is described in `docs/System Design/05-aws-deployment_5.4-ci-cd.png`.

---

## Design documents

Diagrams are in [`docs/System Design`](docs/System%20Design):

| # | Topic |
|---|---|
| 01 | System context |
| 02 | Container view, database ER diagram |
| 03 | Class diagrams: layering, domain models, transform framework, pipeline/profiling/readiness, services, storage/tasks, chat/RAG, frontend |
| 04 | API and flows: upload & profile, apply step, split/readiness/export, chat question, job state machine |
| 05 | AWS deployment topology and CI/CD |
| 06 | Architecture decisions |

---

## Legacy (v1)

[`legacy/`](legacy/) contains the original Streamlit app, a single-user tool with in-memory processing. Some of its loading logic was ported into `backend/app/engine/loaders`, with fixes. To run it:

```bash
cd legacy
pip install -r requirements.txt
streamlit run data_analysis_app.py
```
