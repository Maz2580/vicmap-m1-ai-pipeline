# vicmap-m1-ai-pipeline

[![tests](https://github.com/Maz2580/vicmap-m1-ai-pipeline/actions/workflows/test.yml/badge.svg)](https://github.com/Maz2580/vicmap-m1-ai-pipeline/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](#requirements)
[![security](https://img.shields.io/badge/security-audit_published-green.svg)](SECURITY_AUDIT.md)

> **End-to-end automation for the Victorian M1 form workflow.**
> From the VicMap delivery email, all the way to a per-row pass/warn/fail
> report — with a configurable LLM doing the heavy lifting on validation.

Built originally for **Greater Shepparton Council**, open-sourced under
Apache 2.0 so any Victorian LGA (or any team curious about LGA-scale
property automation) can adopt and extend it.

---

## What you get

It's not a single script. It's a **Flask web application + two micro-APIs**
with ~80 REST endpoints across them, an LLM provider abstraction with five
built-in backends, and an opinionated 5-phase pipeline.

### The 5-phase pipeline

```
┌─────────────┐    ┌────────────┐    ┌─────────┐    ┌──────────┐    ┌─────────────┐
│   1 Email   │ →  │ 2 Download │ →  │ 3 FME   │ →  │ 4 Pozi   │ →  │ 5 Validate  │
│  IMAP poll  │    │  S3 unzip  │    │ workspace│    │ 3 tasks  │    │ AI + rules  │
│  for VicMap │    │  + slip-   │    │  (Windows│    │  ~60 min │    │  +  database│
│  delivery   │    │   safe     │    │   only)  │    │          │    │   crossref  │
└─────────────┘    └────────────┘    └─────────┘    └──────────┘    └─────────────┘
```

Trigger the whole thing with `POST /api/run-all`, or call each phase
individually — see [`docs/api.md`](docs/api.md).

### Headline capabilities

- ⚡ **Deterministic rule engine in front of the LLM.** 8 rules covering
  schema, SDE-grounded spatial checks (road-locality, parcel-property link,
  point-in-property, distance-based-address), and Pozi sync-drift comment
  patterns. ~50% of rows resolve here with zero LLM cost. Rule findings
  are passed as context to the LLM for the ambiguous remainder.
- 🤖 **AI-assisted validation** with **strict JSON-schema output**,
  role-separated prompts (prompt-injection-resistant), and a learned-pattern
  layer that conditions on your council's prior accept/reject decisions.
- 🔌 **5 LLM backends behind one interface** — OpenAI, OpenRouter, Groq,
  Ollama, Together.ai (all via the OpenAI-compatible API), plus Anthropic
  Claude natively. Optional fallback provider for transient-error recovery.
- 📡 **Server-Sent Events log stream** at `/api/logs/stream` — the web UI
  renders pipeline progress live.
- 🧰 **AI utility endpoints**: comment enhancement, error recovery
  suggestions, column→M1-field mapping suggestions.
- 🗂️ **Batch validation** of multiple CSVs in one request.
- 🔍 **Preview & pagination** of Pozi CSVs and validation reports without
  invoking the validator.
- 🗄️ **TechnologyOne InfoProd cross-reference** — property number lookup
  with `Status='C'` filter, parcel-relationship validation, rates table
  introspection.
- 🌏 **VicMap ArcGIS REST integration** for live property/address/parcel
  checks (public endpoints, no auth required).
- 📧 **IMAP email monitoring** — auto-extracts the S3 URL from VicMap's
  delivery email so the pipeline can be fully unattended.
- 🛡️ **Bearer-token auth + CORS allowlist** on every Flask service.
- 📋 **Published security audit** — [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md)
  with severity-rated findings and an adopter checklist.

### The architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│  app.py — Main Flask app (port 5000)                                   │
│  ─────────────────────────────────                                     │
│  • Web UI (templates/index.html)                                       │
│  • Pipeline orchestration: /api/email/check, /api/download,            │
│    /api/fme/run, /api/pozi/run, /api/run-all                           │
│  • Settings UI: /api/settings, /api/settings/test                      │
│  • Live log streaming via SSE: /api/logs/stream                        │
│  • Report browsing: /api/reports/list, /api/reports/load/*             │
│  • Proxies validation calls to port 5001                               │
└────────────────────────────────────────────────────────────────────────┘
            │                                       │
            ▼ proxy                                 ▼
┌──────────────────────────────────┐   ┌──────────────────────────────────┐
│  Validation API (port 5001)      │   │  Preview API (port 5002)         │
│  v2_m1_ai_validator/api/         │   │  v2_m1_ai_validator/api/         │
│    m1_validation_api.py          │   │    preview_api.py                │
│  ─────────────────────────────   │   │  ─────────────────────────────   │
│  • /api/validate-m1              │   │  • Inspection-only mirror of     │
│  • /api/smart-validate-m1        │   │    the preview endpoints (no     │
│  • /api/validate-batch           │   │    validator runtime needed)     │
│  • /api/enhance-comments         │   │                                  │
│  • /api/error-recovery           │   │                                  │
│  • /api/field-mapping-suggestions│   │                                  │
│  • /api/database/explore-schema  │   │                                  │
│  • /api/preview/*                │   │                                  │
└──────────────────────────────────┘   └──────────────────────────────────┘
            │                                       │
            ▼                                       │
┌──────────────────────────────────────────────────────────────────────────┐
│  v2_m1_ai_validator/                                                     │
│  ────────────────────                                                    │
│  • providers/        ← pluggable LLM layer (5 OpenAI-compat + Anthropic) │
│  • data_processing/  ← InfoProd queries, VicMap REST, validators         │
│  • utils/            ← schema explorer, query optimizer, logging         │
│  • tests/            ← pytest (fast suite mocks external APIs)           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## LLM provider matrix

Set `LLM_PROVIDER` in `.env`. Optionally set `LLM_PROVIDER_FALLBACK` to
auto-failover (e.g. paid OpenAI as primary, free Groq as fallback).

| `LLM_PROVIDER` | API key env var | Default model | Notes |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-5.4` | Default. Paid. OpenAI's affordable workhorse for structured-output tasks. |
| `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-5.4` | Routes to many models incl. free tiers. |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | Free tier available, very fast. |
| `ollama` | none | `llama3.1` | Local-only. Set `OLLAMA_BASE_URL` if not on `localhost:11434`. |
| `together` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Paid. |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` | Requires `pip install anthropic` (commented in `requirements.txt`). |

Override the model per-provider with `LLM_MODEL=<model-id>`.

---

## Quick start

### Requirements

- **Python 3.10+** (tested on 3.10 / 3.11 / 3.12 via CI).
- **Windows** for the full pipeline (FME and Pozi Connect are Windows-only).
  Validators, the Flask layer, and the AI utilities run on macOS/Linux too —
  just the orchestration phases 3 and 4 won't fire.
- **(Optional) TechnologyOne InfoProd** SQL Server for cross-reference validation.
- **(Optional) FME** for phase 3 and **Pozi Connect** for phase 4.

### Install

```bash
git clone https://github.com/Maz2580/vicmap-m1-ai-pipeline.git
cd vicmap-m1-ai-pipeline

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
# Optional, only if you'll use Anthropic Claude:
# pip install anthropic
```

### Configure

```bash
cp .env.example .env
cp config/settings.example.json config/settings.json
cp download_url.example.json download_url.json
```

At minimum, set in `.env`:

```dotenv
# ⚠️ CRITICAL: Set this to YOUR council's 3-digit Victorian LGA code.
# This is NOT optional — every SDE query and VicMap REST query filters by it.
# Examples: 300=Alpine, 328=Greater Shepparton, 363=Mildura.
# Full list: https://www.land.vic.gov.au/maps-and-spatial/
LGA_CODE=

LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Strongly recommended:
API_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
ALLOWED_ORIGINS=http://localhost:5000
```

> ### ⚠️ Setting LGA_CODE wrong means silent zero results
>
> Every spatial/property query in the validator filters by your LGA code.
> If you set the wrong code (or leave it blank), the rule engine will
> query the database, get back zero matching rows, and conclude *"nothing
> wrong, KEEP the row"* — even when there genuinely is an issue. The
> Greater Shepparton instance ran for months with `LGA_CODE=346`
> (Strathbogie's code) before we noticed every VicMap query was
> returning empty. **Always verify your LGA code against the official
> Victorian list before deploying.**

### Run

```bash
# Terminal 1 — web UI + orchestration
python app.py
# → http://localhost:5000

# Terminal 2 — validation API
python v2_m1_ai_validator/api/m1_validation_api.py
# → http://localhost:5001
```

Open the web UI, paste your `API_TOKEN` if you set one, and click through
the 5 phases. Or trigger headlessly:

```bash
curl -X POST http://localhost:5000/api/run-all \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" -d '{}'
```

### Run against the synthetic fixture (no real data needed)

```bash
python v2_m1_ai_validator/smart_openai_validator.py
# Reads tests/fixtures/sample_m1.csv (8 synthetic rows, schema-correct).
```

---

## Configuration reference

Every adopter-tunable knob is an environment variable. See [`.env.example`](.env.example)
for the full list with comments. The highlights:

| Var | Used by | Notes |
|---|---|---|
| `LGA_CODE` | validators | Your council's 3-digit Victorian LGA code. |
| `LLM_PROVIDER` / `LLM_PROVIDER_FALLBACK` | validators | Provider selection — see matrix above. |
| `LLM_MODEL` | validators | Override the default model for the chosen provider. |
| `API_TOKEN` | all 3 services | Bearer-token auth. Comma-separated for rotation. |
| `ALLOWED_ORIGINS` | all 3 services | CORS allowlist. |
| `DB_SERVER` / `DB_USERNAME` / `DB_PASSWORD` / `DB_DATABASE` | validator | TechOne InfoProd connection. Defaults blank — connection fails loudly until set. |
| `EMAIL_USERNAME` / `EMAIL_PASSWORD` / `EMAIL_SERVER` / `EMAIL_PORT` | email monitor | IMAP for the VicMap delivery inbox. |
| `M1_FME_EXE` / `M1_FME_WORKSPACE` | FME runner | Required for phase 3. |
| `M1_POZI_DIR` | Pozi runner | Required for phase 4. |
| `GEOCORTEX_URL` / `GEOCORTEX_USER` / `GEOCORTEX_PASS` | UI | Optional; lets the UI link directly to your council's spatial viewer. |

---

## API reference

Full reference for all ~80 endpoints across all 3 services lives in
[**`docs/api.md`**](docs/api.md). Quick highlights:

```bash
# Full pipeline, fire and forget
POST /api/run-all

# Smart AI validation of a CSV
POST /api/smart-validate-m1   { "file_path": "tests/fixtures/sample_m1.csv" }

# Batch many CSVs at once
POST /api/validate-batch      { "file_paths": [ "...", "..." ] }

# Tail pipeline logs (SSE)
GET  /api/logs/stream

# Get LLM-rewritten clearer comments
POST /api/enhance-comments    { "comments": [ "WARNING addr mismatch..." ] }

# Suggest fixes for validation errors
POST /api/error-recovery      { "errors": [ {...} ] }

# Guess M1-field mappings for an adopter's CSV columns
POST /api/field-mapping-suggestions  { "headers": [ "LGA","PropertyNum",... ] }
```

---

## How it actually works

### Phase 5: validation deep-dive

The validator does **three layers of checks** for each M1 row:

1. **Schema rules** — every column present and typed correctly, edit_code is
   one of `B/C/E/P/S/Z/A/R`, mandatory fields populated for the chosen
   edit_code (per Vicmap V12 — see [`docs/m1_reference.md`](docs/m1_reference.md)).
2. **Cross-references** — propnum / SPI / PFIs resolved against:
   - **TechOne InfoProd** for council-side property records (with
     `Status='C'` filter to match the M1 active set).
   - **VicMap ArcGIS REST** for state-side property/address/parcel layers.
3. **AI judgement** — the LLM examines the row in light of patterns
   learned from labelled training data, decides KEEP / REJECT, and
   produces a confidence + reason.

The AI output is **structured JSON** via OpenAI's strict json_schema mode
(`response_format={"type":"json_schema","strict":true,...}`), which
guarantees the model returns a parseable object matching the validator's
expected shape — no malformed JSON, no missing fields. Role-separated
prompts mean the system message holds the rules and schema while the user
message holds **only the row data**. A malicious `comments` field can't
impersonate the rule-giver — the system prompt explicitly tells the model
to treat user content as data, never as instructions.

There's a deterministic **rule engine** in front of the LLM (see
`v2_m1_ai_validator/data_processing/rule_engine.py`). For each M1 row it
runs cheap schema checks first, then SDE-grounded spatial checks
(road-locality lookup, parcel-property link, point-in-property,
distance-based-address detection), then comment-pattern checks (the Pozi
sync-drift signature). Only rows that the rule engine cannot classify go
to the LLM — which means ~50% of rows in production training data
resolve at zero LLM cost. Adding a new rule is ~30 lines; see the rules
already in the file as templates.

### Pluggable LLM providers

The provider layer (`v2_m1_ai_validator/providers/`) exposes one ABC —
`LLMProvider.chat(messages, response_format=None, temperature=0.0,
max_tokens=2000) -> ChatResponse`. Every backend either calls the
OpenAI-compatible Chat Completions API at a different base URL (OpenAI,
OpenRouter, Groq, Ollama, Together) or, for Anthropic, bridges to
`messages.create()` with system-prompt-emulated JSON mode.

Adding a new provider is ~50 lines — see `anthropic_provider.py` as the
template.

---

## Status

- **Pre-1.0** — APIs may change without notice.
- **Production deployment exists** at Greater Shepparton Council (separate
  private repo).
- **CI runs** on Ubuntu + Windows for Python 3.10/3.11/3.12 — only the fast
  test suite is in scope until the integration suite is reworked for
  the synthetic fixture.
- **5/9 audit findings resolved**, 4 still open — see
  [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md).

### Roadmap

- 🛠️ **Implement M-2** — rate limit + per-request row cap on LLM endpoints.
- 🛠️ **Implement M-1** — redact DB password in connection-string helpers.
- 🔁 **Apply provider refactor to `openai_pozi_validator.py`** (same
  pattern, ~550 lines).
- 📊 **Adopter-friendly LGA config** — replace remaining `"Greater
  Shepparton"` strings in error messages with the LGA name from settings.
- 📚 **More worked examples** in `docs/` — splits, merges, multi-assessment.

---

## Adapting this for your LGA

### Mandatory changes

1. **Set `LGA_CODE` in `.env` to your Victorian LGA code.** Three-digit
   string. Find your code on the Victorian Department's
   [LGA list](https://www.land.vic.gov.au/maps-and-spatial/). A few
   examples:

   | LGA | Code | LGA | Code |
   |---|---|---|---|
   | Alpine Shire | 300 | Greater Shepparton City | 328 |
   | Greater Geelong City | 322 | Mildura Rural City | 363 |
   | Greater Bendigo City | 320 | Whittlesea City | 379 |
   | Greater Dandenong City | 321 | Yarra City | 384 |

   **If you set this wrong, every SDE/VicMap query returns zero rows
   silently — and the rule engine concludes "no issues" for rows that
   genuinely have problems.** This is the single most common
   misconfiguration; verify before deploying.

2. **Populate `config/settings.json` `pozi_tasks`** with your council's
   3 `.ini` files (replace the `<YourLGA>` placeholders).

3. **Set `DB_SERVER`/`DB_USERNAME`/`DB_PASSWORD`** in `.env` to your
   council's SQL Server. If you have ArcSDE on the same server, also
   set `SDE_DATABASE` — the rule engine will use it.

### Optional cleanup

Override docstrings / error messages that still reference Greater
Shepparton (informational only, doesn't affect behaviour):

```bash
grep -rni "shepparton" --include="*.py"
```

### If your council uses a different ERP

If you use Civica Pathway, Civica Authority, MagiQ, etc. instead of
TechnologyOne InfoProd, replace
`v2_m1_ai_validator/data_processing/database_helper.py` with one
targeted at your schema. Everything else above the DB layer is
vendor-agnostic.

If your ArcSDE Vicmap layers use different column names than the
defaults baked into `sde_validator.py` (we discovered Greater
Shepparton's schema via `INFORMATION_SCHEMA.COLUMNS` — yours may
differ), pass override dicts via the `ReadOnlySDEHelper` constructor:

```python
sde = ReadOnlySDEHelper(
    col_address={"table": "[SDE].[SDEADMIN].[ADDRESS]",
                 "road_name": "ROADNAME", ...},
    col_property={...},
    col_parcel={...},
)
```

Or subclass it.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The golden rules:

- **No real council data, ever** — synthetic fixtures only.
- **No credentials in committed files** — use `.env`.
- **No `Co-Authored-By:` trailers** in commits.

See [SECURITY.md](SECURITY.md) for the vulnerability disclosure process.

---

## License & acknowledgements

Apache 2.0 — see [LICENSE](LICENSE). The explicit patent grant matters for
council/government adopters.

- **State of Victoria** for the public Vicmap M1 V12 specification — see
  [`docs/m1_reference.md`](docs/m1_reference.md).
- **Greater Shepparton Council** for sponsoring the initial development.
- **Vicmap helpdesk** (`vicmap.help@transport.vic.gov.au`) for the M1
  process and validation rules.
