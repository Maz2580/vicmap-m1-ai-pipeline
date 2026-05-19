<!--
Thanks for contributing! Please skim CONTRIBUTING.md once for the golden
rules (no real council data, no committed credentials, no Co-Authored-By).
-->

## What this changes

<!-- A clear, one-paragraph summary. Reference the issue(s) this closes. -->

Closes #

## Why

<!-- Motivation: what problem does this solve? -->

## How to verify

<!-- Step-by-step instructions a reviewer can follow. If you added tests, mention them here. -->

1.
2.
3.

## Checklist

- [ ] No real council data in any commit (CSVs, reports, spatial files).
- [ ] No credentials in committed files (`.env`, `settings.json`, etc.).
- [ ] No `Co-Authored-By` trailer in commit messages.
- [ ] `pytest v2_m1_ai_validator/tests/test_fast_suite.py` still passes.
- [ ] If this touches a Flask route: confirmed `API_TOKEN` auth still works
      (or documented why this route is exempt).
- [ ] If this touches `database_helper.py`: SQL is still parameterized with
      `?` placeholders — no f-strings or `+` concatenation inside queries.
- [ ] README / docs updated if user-visible behaviour or env vars changed.
