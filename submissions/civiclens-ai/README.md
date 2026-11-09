# CivicLens AI

> **One-line pitch:** An agentic investigation platform for city infrastructure complaints. IBM Db2 stores every complaint, finds duplicates with in-database geo-distance queries, identifies hotspots, and keeps an auditable record of every AI tool call and human decision.

> **Status: Phase 01A.** Investigation API, evidence-grounded recommendations, authenticated human review with atomic Db2 transactions, a bounded LangChain agent, and a clearly labelled rule-based fallback are implemented and verified against a live IBM Db2 12.1 server. **The LLM path has not yet been run against a real hosted model** (no credentials were available), so every recommendation produced so far is labelled `DETERMINISTIC_FALLBACK`. The React dashboard is planned for Phase 01B. See [`docs/PHASE_00_REPORT.md`](docs/PHASE_00_REPORT.md) and [`docs/PHASE_01A_REPORT.md`](docs/PHASE_01A_REPORT.md).

---

## Table of Contents
- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [IBM Db2 Integration](#ibm-db2-integration)
- [AI / LLM Architecture](#ai--llm-architecture)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)
- [Testing & Verification](#testing--verification)
- [Screenshots & Demo](#screenshots--demo)
- [Known Limitations & Future Roadmap](#known-limitations--future-roadmap)
- [Team Members & Credits](#team-members--credits)

---

## Problem Statement
- Municipal bodies receive large numbers of complaints about potholes, broken streetlights, water leaks, garbage and drainage. Many are **duplicates** of the same underlying fault, and the patterns, such as clusters in one neighbourhood or failures that recur after repairs, are hard to see one ticket at a time.
- **Target users:** municipal engineers, ward officers, and civic analysts who must decide where to send crews.
- **Gap:** ticketing tools track individual complaints but rarely explain *why* something should be prioritised, and AI assistants that write their own SQL against production data are hard to trust and to audit.

## Solution Overview
CivicLens AI combines a relational system of record in IBM Db2 with an AI investigator that can only use **audited, allow-listed tools**:

| Capability | Phase 00 status |
|---|---|
| Complaint ingestion API with validation | ✅ Implemented, verified on Db2 |
| IBM Db2 schema, migrations, parameterized data access | ✅ Implemented, verified on Db2 |
| Duplicate detection (Db2 haversine distance + time window + text similarity) | ✅ Implemented, verified on Db2 |
| Geo-temporal hotspot analysis (Db2 `GROUP BY` geo-cell × category) | ✅ Implemented, verified on Db2 |
| Investigation audit log + read API | ✅ Verified on Db2 |
| Secure LangChain tools | ✅ 4 read-only tools, verified on Db2 |
| Investigation API (create / get / evidence / audit / recommendations) | ✅ Verified on Db2 over HTTP |
| Evidence-grounded recommendations (always `PROPOSED`) | ✅ Verified; fabricated ids rejected by the app **and** by Db2 constraints |
| Human review: approve / reject, atomic, no double decisions, self-review blocked | ✅ Verified on Db2 incl. a concurrency test |
| Bounded LangChain agent (allow-list, step limit, timeout) | ✅ Loop verified with a scripted test double; ⚠️ **not yet run against a real LLM provider** |
| Rule-based fallback (labelled "NO LLM") | ✅ Verified on Db2 |
| Interactive dashboard and map (React/Vite/Tailwind) | ⏳ Phase 01–02 |
| Playwright end-to-end tests | ⏳ Phase 02 |

## IBM Db2 Integration
- **Db2 edition and environment:** IBM Db2 Community Edition **12.1.5** in Docker (`icr.io/db2_community/db2`). The same code supports Db2 on Cloud over TLS (`DB2_SECURITY=SSL`); this has not yet been verified against a cloud instance.
- **Connector:** native `ibm_db` 3.3.0 driver, using `prepare` / `execute` with bound parameters only.
- **Schema (`CIVICLENS`):** `COMPLAINTS`, `INVESTIGATIONS`, `INVESTIGATION_EVIDENCE`, `RECOMMENDATIONS`, `REVIEW_DECISIONS`, `AUDIT_LOG`, with CHECK and foreign-key constraints and 5 secondary indexes. DDL: [`src/backend/civiclens/db/schema.sql`](src/backend/civiclens/db/schema.sql).
- **Key operations:**
  - `SELECT … FROM FINAL TABLE (INSERT …)` returns identity keys in a single round-trip.
  - The great-circle (haversine) distance is computed **inside Db2** using `RADIANS`/`SIN`/`COS`/`ASIN`, after a bounding-box filter on the indexed coordinates.
  - Hotspots: `GROUP BY GEO_CELL, CATEGORY HAVING COUNT(*) >= ?` over a time window.
  - Multi-statement writes run in explicit transactions (commit and rollback are both tested).
  - Idempotent migrations check `SYSCAT.SCHEMATA`, `SYSCAT.TABLES` and `SYSCAT.INDEXES` before each `CREATE`.

## AI / LLM Architecture
- **Framework:** LangChain (`langchain-core` `StructuredTool`).
- **Tools (Phase 00, read-only):** `search_complaints`, `get_complaint`, `find_duplicate_candidates`, `hotspot_summary`.
- **Security model:** the LLM never writes SQL. Each tool maps to one fixed, parameterized query. Arguments are validated by Pydantic with hard bounds, and every call (including failures) is written to `AUDIT_LOG` with the investigation id. Future write tools may only create `PROPOSED` recommendations; approval is always a human action.
- **Model provider:** to be selected in Phase 01 (IBM watsonx.ai Granite preferred). No model is called in Phase 00.

## Tech Stack
- **Backend:** Python 3.11+ (verified on 3.13), FastAPI, Pydantic v2, Uvicorn
- **Database:** IBM Db2 (`ibm_db`)
- **AI:** LangChain (`langchain-core`)
- **Frontend (planned):** React, TypeScript, Vite, Tailwind CSS
- **Quality:** Pytest, Ruff

## Prerequisites
- Python ≥ 3.11 and `pip`
- Docker, with about 4 GB of RAM free, for local Db2 Community Edition. Alternatively, access to an existing Db2 instance.
- Linux/macOS x86_64 or arm64, or Windows. The `ibm_db` wheel bundles the Db2 CLI driver (about 137 MB).

## Setup & Installation
```bash
cd submissions/civiclens-ai
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r src/backend/requirements-dev.txt
```

## Configuration
```bash
cp .env.example .env                 # then set DB2_PASSWORD to a strong local password
```
`.env` is gitignored. Every setting can also be supplied as a process environment variable, or via `CIVICLENS_ENV_FILE=/path/to/file`.

> **Note:** the official `scripts/validate_submission.py` fails if any file named `.env` exists inside the submission folder, even an untracked one. Before running it, move your secrets file out (`CIVICLENS_ENV_FILE`) or delete it.

> **Security warning:** never commit `.env`, real passwords or API keys.

## Running the Project
```bash
# 1. Start Db2 Community Edition (first start takes ~3–5 minutes)
docker compose -f docker-compose.db2.yml up -d
docker logs -f civiclens-db2         # wait for "(*) Setup has completed."

# 2. Create the schema (idempotent; also upgrades a Phase 00 database) and load the SYNTHETIC demo dataset
python src/backend/scripts/db2_migrate.py
python src/backend/scripts/seed_synthetic.py

# 3. Run the API (needs CIVICLENS_AUTH_TOKENS in .env for the investigation endpoints)
cd src/backend && uvicorn civiclens.api.main:app --port 8000
# OpenAPI docs: http://localhost:8000/docs

# 4. Drive the full workflow over HTTP (prints a transcript; never prints tokens)
python scripts/api_workflow_demo.py
```

### Choosing the investigator: real LLM or rule-based fallback
* `LLM_PROVIDER=none` (default): `mode=auto` uses the **rule-based fallback**. Every result says `generator: DETERMINISTIC_FALLBACK` and `NO LLM WAS USED`; `mode=llm` returns `409 LLM_NOT_CONFIGURED` instead of silently falling back.
* To use a real model: `pip install -r src/backend/requirements-llm.txt`, then set `LLM_PROVIDER` (`openai`, `anthropic` or `watsonx`), `LLM_MODEL` and the provider credentials in `.env`. Recommendations are then stored with `generator_type = LLM` and `model_name = provider:model`.
* In `auto` mode, if the LLM run fails, the fallback is used and `fallback_reason` explains why.

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness check (no database access) |
| `GET /api/health/db` | Runs a real query against Db2 and returns the server version |
| `POST /api/complaints` | Validates and stores a complaint, then returns duplicate candidates |
| `GET /api/complaints` | Lists complaints, filtered by `category`, `status`, `ward`, `synthetic` and `limit` |
| `GET /api/complaints/{id}` | Returns one complaint |
| `GET /api/hotspots` | Geo-cell × category hotspots, filtered by `days`, `category`, `min_count` and `limit` |
| `POST /api/investigations` | **analyst** · create an investigation |
| `GET /api/investigations`, `GET /api/investigations/{id}` | any user · list / retrieve |
| `GET /api/investigations/{id}/evidence` · `POST …/evidence` | any user read · **analyst** attach existing complaints |
| `GET /api/investigations/{id}/audit` | any user · full audit history |
| `GET /api/investigations/{id}/recommendations` · `POST …/recommendations` | any user read · **analyst** manual proposal |
| `POST /api/investigations/{id}/run` | **analyst** · run the agent (`mode`: `auto` \| `llm` \| `fallback`) |
| `POST /api/recommendations/{id}/decision` | **reviewer** · `APPROVED` / `REJECTED` (reviewer = authenticated user) |

Authentication is a static bearer token per user (`Authorization: Bearer …`) configured through `CIVICLENS_AUTH_TOKENS`; the complaint and hotspot endpoints from Phase 00 remain public. See [`architecture.md`](architecture.md#authentication--authorization).

## Testing & Verification
```bash
pytest                                        # unit tests (no database needed)
CIVICLENS_DB2_TESTS=1 pytest                  # + live Db2 integration tests (needs the .env settings exported)
CIVICLENS_LLM_TESTS=1 CIVICLENS_DB2_TESTS=1 pytest -m llm   # billable real-LLM test (opt-in)
python src/backend/scripts/check_secrets.py --literal-from-env   # committed-secret scan
python src/backend/scripts/db2_smoke_test.py  # end-to-end Db2 evidence → docs/evidence/
ruff check . && ruff format --check .
python ../../scripts/validate_submission.py .   # official validator (from repo root: submissions/civiclens-ai)
```
The integration tests use **no mocks**: they insert, query, aggregate, roll back and audit against the configured Db2 server. Recorded output from a real run is in [`docs/evidence/`](docs/evidence/).

## Screenshots & Demo
- **Live demo:** not deployed yet. Public deployment needs approval and a hosted Db2 instance (see the Phase 00 report).
- **Demo video:** not recorded yet.
- **Recorded evidence:** [`docs/evidence/db2_smoke_test_result.json`](docs/evidence/db2_smoke_test_result.json), [`docs/evidence/pytest_live_db2.txt`](docs/evidence/pytest_live_db2.txt).

## Known Limitations & Future Roadmap
- **Synthetic data:** all demo complaints are fictional, generated by `scripts/generate_synthetic.py`, and stored with `IS_SYNTHETIC = 1` and the `[SYNTHETIC]` marker.
- **Not implemented yet:** the React frontend, rate limiting, per-user token management / OIDC, and hosted deployment. The LLM loop exists but has not been exercised against a real provider.
- **Duplicate text similarity** uses token Jaccard similarity. Phase 02 may add embeddings stored in Db2 (`VECTOR` type), after verifying feature support on the target edition.
- See [`docs/PHASE_00_REPORT.md`](docs/PHASE_00_REPORT.md) for blockers and the next-phase plan.

## Team Members & Credits
| Name | GitHub Handle | Role / Contribution |
|---|---|---|
| _To be completed by the team_ | [@tej-1916](https://github.com/tej-1916) | Lead developer |

Third-party software: FastAPI (MIT), Pydantic (MIT), LangChain (MIT), Uvicorn (BSD-3), `ibm_db` (Apache-2.0), IBM Db2 Community Edition (IBM license, accepted at container start).
