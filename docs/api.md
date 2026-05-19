# REST API reference

This project ships **three Flask services** with ~80 REST endpoints combined.
This page is the operator's reference: which service serves what, what they
expect, what they return, and which env vars influence behaviour.

For broader architecture, see [README.md](../README.md). For security posture
and auth setup, see [SECURITY_AUDIT.md](../SECURITY_AUDIT.md).

## Services at a glance

| Service | File | Default port | Purpose |
|---|---|---|---|
| Main app + web UI | `app.py` | `5000` | Pipeline orchestration, settings UI, log streaming, report browsing. The web UI is served from `/`. |
| Validation API | `v2_m1_ai_validator/api/m1_validation_api.py` | `5001` | AI-assisted M1 validation, batch processing, preview, AI-utility endpoints (comment enhancement, error recovery, field mapping). |
| Preview API | `v2_m1_ai_validator/api/preview_api.py` | `5002` (configurable) | Lightweight preview/inspection of Pozi files and validation results without invoking the validator. |

## Authentication

All three services share **the same Bearer-token model** (added in commit
`9cb8c2f`):

- Set `API_TOKEN` in `.env` (comma-separated for multiple valid tokens):
  ```
  API_TOKEN=my-token-here,operator-2-token,ci-token
  ```
- Every request to a non-exempt path must include:
  ```
  Authorization: Bearer my-token-here
  ```
- **Exempt paths** (no auth required):
  `/`, `/static/*`, `/api/health`, `/api/health/validation-api`,
  and all `OPTIONS` preflight requests.

If `API_TOKEN` is **unset**, auth is disabled and a warning is logged at
startup. This is the legacy behaviour — strongly discouraged outside a
trusted single-operator workstation.

## CORS

All three services read `ALLOWED_ORIGINS` (comma-separated). If unset, CORS
is not configured at all (browsers reject cross-origin requests). Example
for a bundled-UI deployment:

```
ALLOWED_ORIGINS=http://localhost:5000
```

## Conventions

- **Successful POSTs** return `200 OK` with JSON `{"success": true, ...}`.
- **Errors** return `4xx`/`5xx` with JSON `{"success": false, "error": "..."}`
  or `{"error": "..."}`.
- All examples below assume `API_TOKEN=devtoken` and `BASE_URL=http://localhost:5000`.

---

## Main app — `app.py` (port 5000)

### Pipeline orchestration

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/email/check` | Poll the configured IMAP inbox for the VicMap delivery email; extract the S3 URL into `download_url.json`. |
| `POST` | `/api/download` | Download the S3 ZIP referenced in `download_url.json`, unzip into `data/extract/`. Zip-slip protected. |
| `POST` | `/api/fme/run` | Run the configured FME workspace (`M1_FME_WORKSPACE`). Streams progress to log stream. |
| `POST` | `/api/pozi/run` | Run the 3 Pozi Connect tasks from `config/settings.json` `pozi_tasks` array. ~60 minutes end-to-end. |
| `POST` | `/api/run-all` | Run the full Email → Download → FME → Pozi → Validation sequence with progress streaming. |
| `GET`  | `/api/status` | Return current pipeline state: idle/running, current step, progress %, last email check, ready flags. |
| `POST` | `/api/validate-m1` | Submit a Pozi-generated M1 CSV for AI validation (proxies to port 5001). |
| `GET`  | `/api/validation-status` | Get current validation job state from the validator service. |
| `GET`  | `/api/validation-results` | Get the latest validation results (JSON). |

### Live log stream (SSE)

| Method | Path | Description |
|---|---|---|
| `GET`  | `/api/logs/stream` | **Server-Sent Events**. The web UI subscribes and renders log lines in real time. Each event is a JSON line. |
| `POST` | `/api/logs/add` | Push a log line into the SSE queue (used by background workers). |
| `GET`  | `/api/logs/test` | Emit a test log line; useful for verifying the stream is alive. |

### Settings (web UI persistence)

| Method | Path | Description |
|---|---|---|
| `GET`  | `/api/settings` | Read `config/settings.json` (with passwords redacted). |
| `POST` | `/api/settings` | Write `config/settings.json`. Body matches `settings.example.json` shape. |
| `POST` | `/api/settings/test` | Test the configured FME executable + IMAP credentials. Only tests **server-configured paths** (audit C-2). |

### Reports & files

| Method | Path | Description |
|---|---|---|
| `GET`  | `/api/m1-files/list` | List M1 CSVs the validator can be pointed at. |
| `GET`  | `/api/reports/list` | List historical reports the UI can re-load. |
| `POST` | `/api/reports/load/pozi` | Load a Pozi report by filename and stream rows to the UI. |
| `POST` | `/api/reports/load/validation` | Load a validation report by filename. |
| `POST` | `/api/reports/demo` | Generate demo data for the report viewer (useful when adopters have no real data yet). |

### Health

| Method | Path | Auth required | Description |
|---|---|---|---|
| `GET`  | `/api/health/validation-api` | ❌ exempt | Check whether the port-5001 validation service is reachable. |

### Web UI

| Method | Path | Auth required | Description |
|---|---|---|---|
| `GET`  | `/` | ❌ exempt | Serves `templates/index.html` (the bundled web UI). |
| `GET`  | `/static/<path>` | ❌ exempt | Static assets (CSS, JS, images). |
| `GET`  | `/static/logo.png` | ❌ exempt | Convenience route for the logo. |

---

## Validation API — `m1_validation_api.py` (port 5001)

### Health & introspection

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET`  | `/api/health` | ❌ exempt | Liveness check. Returns `{"status": "ok"}` + version. |
| `GET`  | `/api/test-log` | ✅ | Emit a test log line to the main app's stream. |
| `GET`  | `/api/database-info` | ✅ | Summarize the connected InfoProd database (table counts, schema). |
| `GET`  | `/api/database/explore-schema?layer=address\|property\|parcel` | ✅ | Run the VicMap REST schema explorer for the named layer. |
| `POST` | `/api/database/optimize-query` | ✅ | Body: `{ "query": "...", "params": {...} }`. Returns an optimized SQL plan. |
| `POST` | `/api/database/helper` | ✅ | Generic helper proxy — body specifies the helper method to invoke. |

### Validation runs

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/validate-m1` | Body: `{ "file_path": "..." }`. Standard rule-based validation. |
| `POST` | `/api/smart-validate-m1` | Body: `{ "file_path": "..." }`. Routes through `smart_openai_validator.py` (AI-assisted, pluggable provider). |
| `POST` | `/api/validate-batch` | Body: `{ "file_paths": [ "..." ], "max_rows_per_file": 100 }`. Bulk validation. |
| `GET`  | `/api/validation-status` | Current job state, progress, queued/processed/total counts. |
| `GET`  | `/api/validation-results` | Most recent results as JSON. |
| `POST` | `/api/stop-validation` | Signal the in-flight job to stop after the current row. |
| `POST` | `/api/validation-cleanup` | Clear in-memory state and any temp files. |

### AI utility endpoints

These are the **AI features that aren't pure validation**.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/enhance-comments` | Body: `{ "comments": ["..."] }`. Returns LLM-rewritten clearer versions. |
| `POST` | `/api/error-recovery` | Body: `{ "errors": [...] }`. Returns suggested corrections per error. |
| `POST` | `/api/field-mapping-suggestions` | Body: `{ "headers": ["..."] }`. Returns guesses at which column maps to which M1 V12 field — useful when adopters' source data uses different column names. |

### Reports

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/export-report` | Body: `{ "format": "json"\|"csv", ... }`. Returns the latest report in the chosen format. |
| `GET`  | `/api/reports/list` | (Same as main-app counterpart, scoped to this service.) |
| `POST` | `/api/reports/load/pozi` | (Same as main-app.) |
| `POST` | `/api/reports/load/validation` | (Same as main-app.) |
| `POST` | `/api/reports/demo` | (Same as main-app.) |

### Preview (embedded in validation API)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/preview/pozi` | Upload a Pozi CSV file. `multipart/form-data` with `file=...`. Stores in memory. |
| `GET`  | `/api/preview/pozi/data?page=1&per_page=50` | Paginated rows from the most recent upload. |
| `POST` | `/api/preview/validation` | Upload a validation report JSON. |
| `GET`  | `/api/preview/validation/data?page=1&per_page=50` | Paginated validation rows. |
| `GET`  | `/api/preview/summary` | Aggregate stats (kept / rejected / confidence histogram). |

---

## Preview API — `preview_api.py` (port 5002)

A **lighter-weight standalone variant** of the preview endpoints in the
validation API. Useful when you want inspection without spinning up the
heavy validator. Endpoint surface is largely the same:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/preview/pozi` | Upload Pozi CSV. |
| `GET`  | `/api/preview/pozi/data` | Paginated rows. |
| `POST` | `/api/preview/validation` | Upload validation report. |
| `GET`  | `/api/preview/validation/data` | Paginated rows. |
| `GET`  | `/api/preview/summary` | Aggregate stats. |
| `GET`  | `/api/preview/export/pozi` | Download the loaded Pozi CSV. |
| `GET`  | `/api/preview/export/validation` | Download the loaded validation JSON. |
| `POST` | `/api/preview/clear` | Drop the in-memory cache. |
| `GET`  | `/api/reports/list` | List historical reports. |
| `POST` | `/api/reports/load/pozi` | Load Pozi report. |
| `POST` | `/api/reports/load/validation` | Load validation report. |
| `POST` | `/api/reports/demo` | Demo data. |

---

## Common request examples

Replace `devtoken` with whatever you set in `API_TOKEN`.

### Trigger the full pipeline

```bash
curl -X POST http://localhost:5000/api/run-all \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Smart-validate the synthetic fixture

```bash
curl -X POST http://localhost:5001/api/smart-validate-m1 \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "tests/fixtures/sample_m1.csv"}'
```

### Stream pipeline logs

```bash
curl -N http://localhost:5000/api/logs/stream \
  -H "Authorization: Bearer devtoken"
```

The connection stays open; each new log line arrives as a separate
SSE `data: <json>` event.

### Ask the LLM to enhance noisy comments

```bash
curl -X POST http://localhost:5001/api/enhance-comments \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d '{"comments": ["WARNING: addr mismatch xyz", "no issues"]}'
```

### Guess column → M1-field mapping for an adopter's CSV

```bash
curl -X POST http://localhost:5001/api/field-mapping-suggestions \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d '{"headers": ["LGA", "PropertyNum", "Address", "Comments"]}'
```

---

## Environment variables that affect routes

| Env var | Used by | Effect |
|---|---|---|
| `API_TOKEN` | all 3 services | Enable Bearer-token auth. |
| `ALLOWED_ORIGINS` | all 3 services | CORS allowlist. |
| `API_HOST` | validation API | Bind host (default `0.0.0.0`). |
| `API_PORT` | validation API | Bind port (default `5001`). |
| `VALIDATION_API_URL` | main app | Where main app proxies validation calls. |
| `LLM_PROVIDER` | validators | Selects the LLM backend (`openai` / `openrouter` / `groq` / `ollama` / `together` / `anthropic`). |
| `LLM_PROVIDER_FALLBACK` | validators | Optional secondary provider. |
| `LLM_MODEL` | validators | Override the provider's default model. |
| `LGA_CODE` | validators | Filter VicMap queries by LGA. Required for `/api/validate-m1`. |
| `SAMPLE_M1_CSV` | validators (demo scripts) | Default sample path when no `file_path` is provided. |
| `SMART_VALIDATION_REPORT_PATH` | validators | Where `generate_smart_report` writes the JSON report. |
| `SMART_VALIDATION_RESULTS_CSV` | validators | Where the per-row CSV results are written. |

## Status codes

| Code | Meaning |
|---|---|
| `200 OK` | Success. Body has `success: true` for action endpoints. |
| `400 Bad Request` | Malformed body or missing required field. |
| `401 Unauthorized` | `API_TOKEN` is set but the request didn't provide a valid Bearer token. |
| `404 Not Found` | Unknown route. |
| `500 Internal Server Error` | Unhandled exception. Body has `success: false` and an `error` string. |

## What's NOT in this reference

- Internal helpers, decorators, and the SSE event schema beyond "each event is a JSON object".
- The exact JSON Schema for validation results — see `tests/fixtures/sample_m1.csv` and `smart_openai_validator.py`'s prompt for the response shape.
- Rate limits or quotas — none enforced today (audit M-2 still open).
