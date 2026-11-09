# Evidence index

Recorded output of real runs, not summaries. Nothing here is hand-edited except that absolute local paths are replaced by `<submission>` / `<venv>` and ANSI colour codes are stripped. Secret values never appear: the scans print only file names and kinds of match, and tokens are read from the environment by the tests and never logged.

| File | Phase | What it is |
|---|---|---|
| `db2_smoke_test_result.json`, `pytest_live_db2.txt` | 00 | Db2 smoke test and the first live-Db2 test run |
| `api_workflow_transcript.txt`, `pytest_phase01a_live_db2.txt` | 01A | HTTP transcript of the investigation workflow and the live-Db2 run after Phase 01A |
| `pytest_phase01b_live_db2.txt` | 01B | The whole backend suite against **live IBM Db2** (`CIVICLENS_DB2_TESTS=1`): 138 passed, 1 skipped (the opt-in real-LLM test) |
| `backend_static_and_unit.txt` | 01B | `ruff check`, `ruff format --check` and the backend unit tests in a clean environment (no DB, no tokens, no LLM settings) |
| `frontend_checks.txt` | 01B | `tsc --noEmit`, ESLint and the Vitest component / API-integration suite (verbose) |
| `contract_live_test.txt` | 01B | The real TypeScript API client + zod schemas against the running FastAPI + Db2 (no mocks) |
| `e2e_functional_results.txt` | 01B | The Playwright run against the production build, the real backend and IBM Db2 (list reporter) |
| `bundle_scan.txt` | 01B | `npm run verify:bundle`: no literal secret value, no database identifier, CSP present in the built bundle |
| `secrets_scan.txt` | 01B | `check_secrets.py --literal-from-env` over the repository |
| `submission_validator.txt` | 01B | Output of the official `scripts/validate_submission.py` |
| `palette_validation.txt` | 01B | The dataviz skill's palette validator on the dashboard's colours (includes the status-colour run that fails, with the reason) |
| `llm_verification.txt` | 01B | Why real-LLM verification is **BLOCKED**, checked by variable names only, and how to unblock it |

Screenshots are in [`../screenshots/`](../screenshots/README.md) with their own manifest.
