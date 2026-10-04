# ICP Engine

ICP Engine turns a company website or CSV lead list into structured, evidence-backed account intelligence and a configurable ICP score. It collects public company data, extracts useful business signals, applies a consistent qualification policy, and returns structured results through an API-ready workflow.

## The problem

GTM teams spend hours opening company sites, estimating fit, copying findings into a CRM, and explaining why an account is worth attention. Pure LLM scoring is fast but inconsistent and hard to audit. ICP Engine separates interpretation from scoring: website and optional LLM extraction produce structured facts and cited signals, while deterministic code applies the ICP.

## Features

- Accept one company or a UTF-8 CSV with `name` and `website` columns.
- Fetch a bounded set of public pages with timeouts, retries, response limits, and redirect validation.
- Extract company attributes and evidence with deterministic rules plus optional structured LLM interpretation.
- Rank competing extraction candidates by evidence strength and retain field-level confidence internally.
- Score industry, company type, size, sales motion, and growth/automation signals against a JSON ICP configuration.
- Store companies, evidence, component scores, and explanations in SQLite or PostgreSQL.
- Expose the complete workflow through FastAPI Swagger at `/docs`.
- Continue in deterministic mode when no LLM key is present.

## Architecture

```mermaid
flowchart LR
    U[Swagger / CSV client] --> API[FastAPI routes]
    API --> O[Analysis orchestrator]
    O --> S[Safe website scraper]
    S --> E[Deterministic extractor]
    E --> L[Optional LLM researcher]
    L --> C[Configurable scorer]
    C --> DB[(SQLite / PostgreSQL)]
    DB --> API
```

The scraper owns network safety and collection. The extractor creates a typed baseline. The LLM is limited to interpreting supplied page text and must return validated JSON; unsupported evidence is discarded. The scorer alone assigns points. SQLAlchemy keeps persistence independent of the database engine. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Quick start

Python 3.11 or later is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs`. An API key is optional. To enable LLM enrichment, set `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` in `.env` for an OpenAI-compatible chat completions service.

Docker is also supported:

```bash
docker compose up --build
```

For PostgreSQL, change `DATABASE_URL` to a SQLAlchemy URL such as `postgresql+psycopg://user:password@localhost/icp-engine`. Schema creation is automatic for this demo project.

## API examples

Analyze one company:

```bash
curl -X POST http://localhost:8000/companies/analyze \
  -H 'Content-Type: application/json' \
  -d '{"name":"Close","website":"https://www.close.com"}'
```

Analyze a CSV:

```bash
curl -X POST http://localhost:8000/companies/batch \
  -F 'file=@examples/companies.csv'
```

Retrieve results:

```bash
curl http://localhost:8000/companies
curl http://localhost:8000/companies/1
curl http://localhost:8000/companies/1/signals
curl http://localhost:8000/health
```

The batch endpoint processes valid rows and returns a row-level error for invalid or unreachable companies, keeping successful work visible.

## Scoring

The default policy lives in [config/default_icp.json](config/default_icp.json), rather than inside route or LLM prompts. Its weights total 100:

| Component | Max | Evidence used |
|---|---:|---|
| Industry fit | 25 | Extracted industry and company copy |
| Business model | 20 | B2B, SaaS, enterprise language |
| Company size | 20 | Estimated range compared with the 30–50 target |
| Sales motion | 20 | Demo/contact-sales and prospect-research signals |
| Growth signals | 15 | Hiring/funding and GTM automation opportunity |

Each response includes component values, a line-by-line explanation, and signals with evidence, source URL, confidence, and potential point contribution. Duplicate signals in a category do not stack. Edit the JSON policy or point `ICP_CONFIG_PATH` at another compatible file to change the ICP.

Unknown fields receive zero points. Confirmed matches receive their full component value, while evidence below the strong-confidence threshold receives a reduced contribution. Business-model classification recognizes B2B SaaS, B2C SaaS, Software / SaaS, Services, Marketplace, Ecommerce, Agency / Consultancy, Other, and Unknown; weighted phrases prevent isolated navigation wording from overruling stronger product evidence.

An abbreviated response is available at [examples/example-output.json](examples/example-output.json).

## Configuration

All settings are documented in [.env.example](.env.example). Fetching defaults to four pages, 10-second requests, two retries, a 2 MB page limit, and a 100-row batch limit. URL validation rejects credentials, localhost, and resolved private, loopback, link-local, or reserved addresses, and validates every redirect target.

## Quality checks

```bash
pytest
ruff check .
mypy app
```

Tests cover scoring boundaries, input validation, persistence, single-company API behavior, and partial batch failures.

## Screenshots

Add portfolio screenshots here after running the demo:

1. `POST /companies/analyze` expanded in Swagger.
2. A successful response showing the score explanation and cited signals.
3. `GET /companies` showing persisted account research.

## Limitations

- Website-derived employee counts are estimates and are often absent; ICP Engine reports unknown rather than fabricating a value.
- JavaScript-only pages, robots restrictions, login walls, and anti-bot systems can reduce available evidence.
- Batch rows run sequentially for this portfolio-scale service.
- Deterministic extraction favors precision over broad recall. LLM quality depends on the configured provider and model.
- Production deployments should add migrations, a job queue, rate limiting, robots-policy handling, and observability.

## Future improvements

- Add pluggable enrichment providers for firmographics and funding data.
- Version ICP policies and retain the version used for each score.
- Push qualified accounts and evidence into a CRM through idempotent webhooks.
- Add background jobs, domain rate limits, and result caching for larger lists.
- Evaluate extraction accuracy and score stability against a labeled account set.

## Why this matters for GTM teams

ICP Engine makes qualification consistent and reviewable. Reps can see which fact affected a score and open its source, RevOps can change the ICP without rewriting prompts, and engineering teams get structured JSON that can flow into routing, sequencing, and CRM automation.
