# vicmap-m1-ai-pipeline

End-to-end automation for the **Victorian M1 form** workflow — from VicMap
delivery email through FME, Pozi Connect, and AI-assisted validation.

Built originally for Greater Shepparton Council, open-sourced under Apache 2.0
so any Victorian LGA (or other interested party) can adopt and extend it.

## The 5-phase pipeline

```
1. Email     →  Monitor IMAP inbox for the VicMap Datashare delivery email,
                extract the S3 pre-signed URL.
2. Download  →  Fetch the .zip from S3, unzip into data/extract/.
3. FME       →  Run FME workspaces to project the extract into the M1 schema.
4. Pozi      →  Three Pozi Connect tasks (Import Pathway, Import Vicmap,
                Generate M1) — ~60 minutes end-to-end.
5. Validate  →  AI-assisted validation against the TechnologyOne InfoProd
                database + VicMap REST services. Produces a per-row
                pass/warn/fail report.
```

Phases 1–4 are sequential and triggered from a Flask web UI (`app.py`, port
5000). Phase 5 runs as a separate Flask API service (`v2_m1_ai_validator/api/`,
port 5001) and can be called standalone on any existing M1 CSV.

## Quick start

```bash
git clone https://github.com/<your-fork>/vicmap-m1-ai-pipeline.git
cd vicmap-m1-ai-pipeline

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
cp config/settings.example.json config/settings.json
cp download_url.example.json download_url.json
# Then edit .env and config/settings.json with your council's values.

python app.py            # Web UI on http://localhost:5000
python v2_m1_ai_validator/api/m1_validation_api.py   # Validation API on :5001
```

## Configuration

All deployment-specific values live in `.env` (gitignored). See `.env.example`
for the full list. The minimum required to run validation against an existing
M1 CSV:

- `LGA_CODE` — your Victorian LGA code (e.g. `346` for Greater Shepparton)
- `LLM_PROVIDER` + the corresponding API key (`OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, or
  `OLLAMA_BASE_URL`)
- `DB_SERVER`, `DB_USERNAME`, `DB_PASSWORD` — TechnologyOne InfoProd
  connection details (only needed if you want DB-cross-referenced validation)

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  app.py (Flask :5000)                                               │
│    └─ orchestrates email → download → FME → Pozi → validation       │
│                                                                     │
│  v2_m1_ai_validator/                                                │
│  ├─ smart_openai_validator.py   ← primary AI validator (today)      │
│  ├─ openai_pozi_validator.py    ← Pozi-aware variant                │
│  ├─ ai_intelligent_pozi_validator.py / ai_pozi_analyzer.py          │
│  ├─ api/m1_validation_api.py    ← Flask API (:5001)                 │
│  ├─ api/preview_api.py          ← preview/inspection endpoints      │
│  ├─ data_processing/                                                │
│  │  ├─ database_helper.py       ← TechnologyOne InfoProd queries    │
│  │  ├─ vicmap_validator.py      ← VicMap REST API queries           │
│  │  └─ enhanced_validator.py    ← rule-based validation             │
│  └─ tests/                                                          │
└─────────────────────────────────────────────────────────────────────┘
```

## What's in the box

- 5-phase pipeline orchestration with live status streaming to the web UI
- M1 V12 schema validation (52 columns, edit codes B/C/E/P/S/Z/A/R)
- Cross-reference against VicMap ArcGIS REST services (public, free)
- Cross-reference against your council's TechnologyOne InfoProd database
- AI-assisted comment analysis using GPT-4-class models
- A synthetic test fixture (`tests/fixtures/sample_m1.csv`) you can run
  the pipeline against with zero real-world data

## What you need to adapt

This codebase was originally written for Greater Shepparton's deployment.
After cloning, search for these strings and adjust them for your council:

```bash
# Informational strings still referencing Shepparton (docstrings, error
# messages, comments). None of these break the code — they just say
# "Shepparton" where they should say your LGA's name.
grep -ri "shepparton\|greater shepparton" --include="*.py"

# Hard-coded LGA code in error/suggestion messages.
grep -rn "346" --include="*.py"
```

Most will be in docstrings or error suggestion text — find-and-replace is
safe.

## LLM provider support

Today the validators target OpenAI / OpenRouter. A pluggable provider layer
(supporting Anthropic, Ollama, and Azure OpenAI) is the next planned change —
see issues for tracking.

## Status & known limitations

- **Pre-1.0**: APIs may change without notice.
- **Windows-first**: developed against a Windows deployment (FME, Pozi
  Connect are Windows-only). The Flask layer and validators run on macOS/Linux.
- **TechOne InfoProd-specific**: the DB cross-reference targets TechnologyOne
  InfoProd schema. Adopters using a different ERP will need to rewrite
  `v2_m1_ai_validator/data_processing/database_helper.py`.

## License

Apache 2.0 — see [LICENSE](LICENSE). The explicit patent grant in Apache 2.0
matters for council/government adopters.

## Acknowledgements

- **State of Victoria** for the public M1 specification — see
  [docs/m1_reference.md](docs/m1_reference.md).
- **Vicmap helpdesk** (`vicmap.help@transport.vic.gov.au`) for the M1 process
  and validation rules.
- **Greater Shepparton Council** for sponsoring the initial development.
