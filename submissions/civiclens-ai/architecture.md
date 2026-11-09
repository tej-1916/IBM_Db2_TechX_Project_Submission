# CivicLens AI: System Architecture

## Overview
CivicLens AI has a FastAPI backend with IBM Db2 as its **only persistent store**. All business data, analytics (duplicate detection, hotspot aggregation) and the audit trail live in Db2. A LangChain agent (Phase 01) investigates questions by calling a small set of typed, audited tools. Each tool wraps one static, parameterized Db2 query. A React dashboard (Phase 01–02) talks only to the API.

## Architecture Diagram

```mermaid
graph TD
    UI["React + Vite dashboard<br/>(planned)"] -->|HTTPS JSON| API[FastAPI backend]
    subgraph Backend
      API --> V[Pydantic validation]
      V --> R[Repository<br/>static parameterized SQL]
      API --> AG["LangChain agent<br/>(Phase 01)"]
      AG -->|tool calls only| TK[CivicLensToolkit<br/>allow-listed, bounded, audited]
      TK --> R
    end
    R -->|ibm_db prepare/execute| DB2[(IBM Db2<br/>schema CIVICLENS)]
    TK -->|every call| AUD[AUDIT_LOG]
    AUD --- DB2
    AG -.->|prompt + tool results| LLM["LLM provider<br/>(watsonx.ai, Phase 01)"]
```

## Component Breakdown
| Layer | Module | Responsibility |
|---|---|---|
| Config | `civiclens/config.py` | Env-driven settings; password is a `SecretStr`; schema name validated as a Db2 identifier |
| Db2 connection | `civiclens/db/connection.py` | `ibm_db` session wrapper: prepare/execute with bound params, transactions, server info, redacted errors |
| Migrations | `civiclens/db/migrate.py`, `schema.sql` | Catalog-checked (`SYSCAT.*`) idempotent DDL |
| Repository | `civiclens/db/repository.py` | All SQL: insert/read/list complaints, duplicate candidates, hotspots, investigations, audit |
| Domain | `civiclens/domain/*` | Pydantic models, geo-cells, haversine, text fingerprint/Jaccard (pure, unit-tested) |
| Agent tools | `civiclens/agent/tools.py` | LangChain `StructuredTool`s with bounded args and audit logging |
| API | `civiclens/api/main.py` | REST endpoints, CORS, 503 on DB unavailability |
| Scripts | `src/backend/scripts/` | migrate, synthetic data generate/seed, Db2 smoke test |

## Data Flow
1. **Ingestion:** `POST /api/complaints` validates the payload, then computes `GEO_CELL` and `TEXT_FINGERPRINT`, then runs `INSERT` via `FINAL TABLE` to get the new id.
2. **Duplicate check:** Db2 filters by category, status, an indexed bounding box and a ±14-day window, computes the exact haversine distance in SQL, and keeps rows within the radius. Python re-ranks them by text similarity. The candidates are returned to the caller.
3. **Hotspots:** a Db2 `GROUP BY GEO_CELL, CATEGORY … HAVING COUNT(*) >= ?` over the requested window.
4. **Investigation (Phase 01A):** an analyst creates an investigation (`OPEN`). `POST …/run` atomically claims it (`OPEN|FAILED → RUNNING`, a compare-and-set `UPDATE`), then runs the LLM agent or the rule-based fallback. Every tool call writes an `AUDIT_LOG` row.
5. **Grounding and persistence:** drafts are accepted only if every cited complaint id was *returned by a tool in this run*. One Db2 transaction then attaches the cited complaints (`INVESTIGATION_EVIDENCE`), inserts `RECOMMENDATIONS` (status is the SQL literal `'PROPOSED'`), links `RECOMMENDATION_EVIDENCE`, writes audit rows and moves the investigation to `PENDING_REVIEW`.
6. **Human review:** a reviewer approves or rejects through one Db2 transaction (see below). When no `PROPOSED` recommendation remains, the investigation becomes `CLOSED`.

```text
Investigation:  OPEN ─run→ RUNNING ─ok→ PENDING_REVIEW ─all decided→ CLOSED
                  ▲           └─error→ FAILED ─(re-run)─┘             (no findings → CLOSED)
Recommendation: PROPOSED ─reviewer→ APPROVED | REJECTED   (terminal)
```

### Review transaction (`investigation_repo.decide`)
One transaction: (1) load the recommendation + investigation; (2) refuse if the reviewer created the investigation (four-eyes); (3) require status `PROPOSED` and investigation `PENDING_REVIEW`; (4) require the evidence links to still exist; (5) `UPDATE … SET STATUS=? WHERE STATUS='PROPOSED'` must change exactly one row; (6) insert the `REVIEW_DECISIONS` row; (7) write the audit row; (8) close the investigation if nothing is left to review. Any exception rolls all of it back. The unique index `UX_DECISIONS_REC` is the database-level backstop against double decisions, and `CURRENT LOCK TIMEOUT` is set to 10 s so concurrent writers fail fast.

### Authentication & authorization
* Bearer tokens, one per user, from `CIVICLENS_AUTH_TOKENS` (`id:role:token`, ≥ 24 chars, constant-time comparison). Not configured ⇒ `503` (fail closed); missing or wrong token ⇒ `401`; wrong role ⇒ `403`.
* Roles: **analyst** (create, attach evidence, run, propose) and **reviewer** (approve / reject). The reviewer identity is the authenticated principal, never a request field (a body containing `reviewer` is rejected).
* Rejected review attempts (self-review) are written to `AUDIT_LOG` as `REVIEW_DENIED`.
* Known gap: Phase 00 complaint ingestion and read endpoints are still public, there is no rate limiting, and tokens are static. Production would use OIDC (for example IBM App ID) and per-user revocation.

### Agent safety
Tool allow-list, Pydantic-validated arguments, `AGENT_MAX_STEPS` iterations, an `AGENT_TIMEOUT_S` wall-clock deadline checked before every model and tool call, a per-request provider timeout, size-capped tool messages, strict JSON output validation (unknown keys such as a model-supplied `status` are dropped), and evidence grounding. Complaint text is untrusted input (prompt injection): the system prompt says so, and the blast radius is bounded because the model has no write tool and can only produce `PROPOSED` rows that a human must approve. The wall-clock deadline is cooperative: a single hung provider call is bounded by the provider request timeout, not interrupted.

## IBM Db2 Schema & Storage Design
The full DDL is in [`src/backend/civiclens/db/schema.sql`](src/backend/civiclens/db/schema.sql). Summary:

```text
COMPLAINTS (PK COMPLAINT_ID identity)
  category/status/severity CHECKs, lat/lon DECIMAL(9,6) + CHECK ranges,
  GEO_CELL, TEXT_FINGERPRINT CHAR(64), DUPLICATE_OF -> COMPLAINTS (self FK),
  IS_SYNTHETIC SMALLINT CHECK (0,1), REPORTED_AT, CREATED_AT
  IX (CATEGORY, REPORTED_AT) | IX (GEO_CELL, REPORTED_AT) | IX (TEXT_FINGERPRINT) | IX (STATUS, REPORTED_AT)

RECOMMENDATION_EVIDENCE (PK REC_ID+COMPLAINT_ID; FK REC_ID -> RECOMMENDATIONS;
   composite FK (INVESTIGATION_ID, COMPLAINT_ID) -> INVESTIGATION_EVIDENCE: Db2 refuses
   evidence not attached to the same investigation)
RECOMMENDATIONS also has GENERATOR_TYPE (LLM|DETERMINISTIC_FALLBACK|MANUAL|UNKNOWN) and
   UNIQUE INDEX UX_DECISIONS_REC on REVIEW_DECISIONS(RECOMMENDATION_ID) prevents double review
INVESTIGATIONS (PK INVESTIGATION_ID) -- status OPEN|RUNNING|PENDING_REVIEW|CLOSED|FAILED
INVESTIGATION_EVIDENCE (PK INVESTIGATION_ID+COMPLAINT_ID, FKs cascade, RELEVANCE 0..1)
RECOMMENDATIONS (PK, FK -> INVESTIGATIONS, CONFIDENCE 0..1, status PROPOSED|APPROVED|REJECTED|NEEDS_INFO)
REVIEW_DECISIONS (PK, FK -> RECOMMENDATIONS, reviewer, decision, comment)
AUDIT_LOG (PK, INVESTIGATION_ID, ACTOR_TYPE USER|AGENT|SYSTEM, ACTION, TOOL_NAME,
           INPUT_JSON, OUTPUT_SUMMARY, SUCCESS)   IX (INVESTIGATION_ID, CREATED_AT)
```

Example: the in-database duplicate distance query (abridged):
```sql
WITH NEARBY AS (
  SELECT COMPLAINT_ID, TITLE, DESCRIPTION, TEXT_FINGERPRINT,
         2 * 6371000 * ASIN(SQRT(
             POWER(SIN(RADIANS(CAST(LATITUDE AS DOUBLE) - CAST(? AS DOUBLE)) / 2), 2)
           + COS(RADIANS(CAST(? AS DOUBLE))) * COS(RADIANS(CAST(LATITUDE AS DOUBLE)))
           * POWER(SIN(RADIANS(CAST(LONGITUDE AS DOUBLE) - CAST(? AS DOUBLE)) / 2), 2))) AS DISTANCE_M
  FROM CIVICLENS.COMPLAINTS
  WHERE CATEGORY = ? AND STATUS <> 'DUPLICATE'
    AND LATITUDE BETWEEN ? AND ? AND LONGITUDE BETWEEN ? AND ?
    AND REPORTED_AT BETWEEN CAST(? AS TIMESTAMP) AND CAST(? AS TIMESTAMP)
    AND COMPLAINT_ID <> ?)
SELECT * FROM NEARBY WHERE DISTANCE_M <= CAST(? AS DOUBLE) ORDER BY DISTANCE_M
```

## Secure Agent Tool Design
| Tool | Db2 operation | Bounds |
|---|---|---|
| `search_complaints` | filtered `SELECT` on `COMPLAINTS` | ≤ 25 rows, ≤ 365-day window, enum-validated category/status |
| `get_complaint` | `SELECT … WHERE COMPLAINT_ID = ?` | id ≥ 1 |
| `find_duplicate_candidates` | haversine CTE (above) | radius ≤ 2000 m, window ≤ 90 days |
| `hotspot_summary` | `GROUP BY GEO_CELL, CATEGORY` | ≤ 25 rows, min_count ≥ 2 |
| *(no model-facing write tool)* | Recommendations are persisted by the orchestrator, never by a tool call | status is a SQL literal `'PROPOSED'`; evidence must be grounded |

Rules:
1. No free-form SQL tool exists, and the LLM output is never executed as SQL.
2. Optional filters are assembled only from constant fragments; every value is a bound parameter.
3. `FETCH FIRST n ROWS` uses a server-side clamped integer, never a model-supplied string.
4. Every call is audited, including failures. Error details are not returned to the model, which prevents schema or driver leakage.
5. Write tools cannot approve. Approval exists only on the human review API.

## Security & Secrets Management
- Credentials are read only from the environment or a gitignored `.env`. `DB2_PASSWORD` is a `SecretStr` with no default, and connection errors are redacted.
- The connection-string builder rejects `;` and `=` in host, database and user values.
- The schema name is validated against `^[A-Z][A-Z0-9_]{0,29}$` before it is substituted into SQL.
- CORS is restricted to configured origins. Authentication and authorization for reviewers are planned for Phase 01.
- Synthetic data is always flagged (`IS_SYNTHETIC = 1`, `[SYNTHETIC]` text marker, `SOURCE = 'SYNTHETIC'`).
