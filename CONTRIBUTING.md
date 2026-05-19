# Contributing to vicmap-m1-ai-pipeline

Thanks for considering a contribution. The code is **deployed in production at
a Victorian council**, so the rules below are tighter than a typical hobby
repo — please skim before opening a PR.

## Golden rules

1. **No real council data, ever.** Test fixtures live in `tests/fixtures/`
   and must be synthetic. The `.gitignore` blocks `*.csv`, `*.xlsx`, `*.docx`,
   `data/`, and all validation reports by default.
2. **No real credentials in committed files.** `.env` is gitignored. Use
   placeholders in `.env.example`, `config/settings.example.json`, and
   `download_url.example.json`.
3. **Apache 2.0 license header** on new source files is welcome but not
   required.

## Dev setup

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
# Fill in the placeholders.
```

## Running tests

```bash
pytest v2_m1_ai_validator/tests/
```

Most tests use the synthetic fixture at `tests/fixtures/sample_m1.csv`. The
fast suite (`test_fast_suite.py`) mocks all external API calls.

## Coding style

- Python 3.10+.
- Follow PEP 8; we use 4-space indent.
- Type hints are encouraged on new code; not required to retrofit existing
  code in the same PR.
- One concern per PR — refactors separate from feature work.

## PR process

1. Branch from `main` (e.g. `feat/llm-anthropic-provider`,
   `fix/email-imap-timeout`).
2. Open a PR with a clear description: what changed, why, and how you tested.
3. Mark draft if work-in-progress.
4. PRs touching `v2_m1_ai_validator/` should include or update tests.

## Reporting issues

Open a GitHub issue. For privacy-affecting issues (e.g. you found real council
data in a commit), please email the maintainer directly rather than filing a
public issue.
