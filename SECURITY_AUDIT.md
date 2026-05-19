# Security Audit — vicmap-m1-ai-pipeline

**Audit date:** 2026-05-19
**Audited commit:** `1ef2dab` (initial audit)
**Update date:** 2026-05-20 — fixes for C-1, C-2, H-1, H-3, H-4 landed.
**Scope:** Public repo only (`vicmap-m1-ai-pipeline`). Audit covers Flask
routes, SQL handling, subprocess/shell usage, file path safety, LLM prompt
construction, and log/error-path leakage.

## Status (updated 2026-05-20)

| Finding | Status | Where |
|---|---|---|
| C-1 No auth on Flask routes | ✅ **Fixed** | `utils/auth.py` (new) — Bearer-token middleware. `API_TOKEN` env var enables. |
| C-2 `/api/settings/test` runs caller-supplied path | ✅ **Fixed** | `utils/settings_manager.py:test_fme_connection` — only the server-configured `M1_FME_EXE` is tested; caller-supplied paths are rejected. |
| H-1 Wildcard CORS | ✅ **Fixed** | All 3 Flask apps now read `ALLOWED_ORIGINS` env var; CORS disabled if unset. |
| H-2 No CSRF protection | ⚠️ Mitigated by C-1 fix | `API_TOKEN` Bearer header isn't reachable from cross-site form submission. Full `flask-wtf` integration still recommended for cookie-based deployments. |
| H-3 Zip-slip in `download_extract.py` | ✅ **Fixed** | `_is_safe_member` validates every member resolves under `EXTRACT_DIR`. |
| H-4 `shell=True` in fme/pozi runners | ✅ **Fixed** | Both removed; commands passed as lists. `cmd_str` in `pozi_runner.py` replaced with a `cmd` list. |
| M-1 DB password in conn string | ⏳ Open | Still in `database_helper.py:48`. |
| M-2 No LLM rate limit | ⏳ Open | No `flask-limiter` yet. |
| L-1 Bind to 0.0.0.0 | ⏳ Open (documented) | Still the default. |
| L-2 Dev server in prod | ⏳ Open (documented) | Still `app.run()`. |

Adopter checklist below remains accurate for items still marked Open.

> **Threat model assumption.** This codebase is intended for deployment **on
> a council intranet behind a perimeter firewall**, not on the open internet.
> Several findings (CORS, no auth, bind-all-interfaces) are tolerable behind
> a trusted network boundary and dangerous without one. Adopters MUST
> understand which side of that boundary they're on.

## Risk summary

| Sev | Finding | File:Line |
|---|---|---|
| 🔴 CRITICAL | No authentication on any Flask route | `app.py:119–1086`, `v2_m1_ai_validator/api/m1_validation_api.py:215–1272`, `v2_m1_ai_validator/api/preview_api.py:30–536` |
| 🔴 CRITICAL | `/api/settings/test` runs a user-supplied executable path | `app.py:493`, `utils/settings_manager.py:101` |
| 🟠 HIGH | Wildcard CORS (`CORS(app)` with no `origins`) | `app.py:27`, `v2_m1_ai_validator/api/m1_validation_api.py:37`, `v2_m1_ai_validator/api/preview_api.py:18` |
| 🟠 HIGH | No CSRF protection on POST routes that mutate state | (every `methods=['POST']` route) |
| 🟠 HIGH | Zip-slip vulnerability in `download_extract.py` | `download_extract.py:98–104` |
| 🟠 HIGH | `subprocess.run(..., shell=True)` with constructed command strings | `fme_runner.py:184`, `pozi_runner.py:114` |
| 🟡 MEDIUM | DB password formatted into connection string — accidental-log risk | `v2_m1_ai_validator/data_processing/database_helper.py:48` |
| 🟡 MEDIUM | No rate limit / cost cap on LLM-backed endpoints | `app.py:971`, `v2_m1_ai_validator/api/m1_validation_api.py:285,436,580,627,733,777` |
| 🟢 LOW | Bound to `0.0.0.0` by default (LAN-accessible) | `app.py:1169`, `v2_m1_ai_validator/api/m1_validation_api.py:1634` |
| 🟢 LOW | Using Flask's dev server in production paths | `app.py:1169`, `v2_m1_ai_validator/api/m1_validation_api.py:1634` |
| ⚪ INFO | All SQL queries use parameterized placeholders ✓ | `v2_m1_ai_validator/data_processing/database_helper.py` (all `cursor.execute` sites) |
| ⚪ INFO | No secret-in-log patterns observed ✓ | — |

---

## 🔴 CRITICAL

### C-1. No authentication on any Flask route

**Impact:** Anyone with network access to the Flask processes can:
- Trigger the FME pipeline (`/api/fme/run`) — long-running, resource-heavy.
- Trigger Pozi tasks (`/api/pozi/run`) — ~60 min, modifies local FS.
- Save arbitrary settings to disk (`/api/settings`).
- Submit M1 files for validation (`/api/validate-m1`) — burns LLM budget.
- Read validation results / property data (`/api/validation-results`,
  `/api/reports/load/*`).

Combined with C-2 (below), this gives an attacker on the same network a way
to execute arbitrary binaries.

**Fix recommendations (in order of effort):**

1. **Run behind a reverse proxy that enforces auth** (nginx + basic auth, or
   an SSO proxy like oauth2-proxy). Lowest code change.
2. **Add an API token middleware.** Reject any request without a matching
   `Authorization: Bearer <token>` where the token comes from
   `os.getenv("API_TOKEN")`. ~20 lines of Flask middleware.
3. **Restrict bind to `127.0.0.1`** and tunnel via SSH for operators. Drops
   the attack surface to zero non-administrators.

Picking (1) or (2) is recommended for any deployment where the host isn't
locked to a single administrator workstation.

### C-2. `/api/settings/test` invokes a user-supplied executable

**Files:** `app.py:493` (`@app.route('/api/settings/test', methods=['POST'])`)
calls `SettingsManager.test_fme_path(path)` →
`utils/settings_manager.py:101` runs `subprocess.run([path_to_test, '--version'], ...)`.

**Impact:** A POST to `/api/settings/test` with `{"path": "..."}` causes the
server to **execute any binary on the host** as the Flask process user. While
the argument is hardcoded to `--version`, the binary itself is attacker-controlled,
so `path` = `cmd.exe`, `powershell.exe`, `C:\Windows\System32\calc.exe`, or any
attacker-uploaded file would all run.

Combined with C-1 (no auth), this is a network-reachable arbitrary code
execution primitive.

**Fix recommendations:**

1. **Whitelist the test target.** The setting being tested is the FME
   executable path — only run the test if the path matches the configured
   `M1_FME_EXE` env var.
2. **Validate the path is an `.exe` ending in `fme.exe`** and exists on disk
   before invoking.
3. **Drop the route entirely** if the operator can equally well test the path
   themselves from the command line.

---

## 🟠 HIGH

### H-1. Wildcard CORS

```python
# app.py:27, m1_validation_api.py:37, preview_api.py:18
CORS(app)
```

`flask-cors` defaults `origins=*` when `CORS(app)` is called bare. Any web
page anywhere can `fetch('http://<your-host>:5000/api/run-all')` from the
browser, and (combined with C-1) trigger pipeline runs.

**Fix:** `CORS(app, origins=os.getenv("ALLOWED_ORIGINS", "").split(","))`,
with `ALLOWED_ORIGINS` populated to the actual frontend host (or the empty
string to fully disable CORS in localhost-only deployments).

### H-2. No CSRF protection

State-mutating POST routes (`/api/fme/run`, `/api/pozi/run`, `/api/settings`,
`/api/validate-m1`, etc.) have no CSRF token. Once an authenticated user has
a session, any malicious site they visit can submit requests on their behalf.

**Fix:** Add `flask-wtf`'s `CSRFProtect`, OR require an `X-API-Token` header
that browser-form submissions can't naturally include (works as both auth and
CSRF defense — see C-1).

### H-3. Zip-slip in `download_extract.py`

```python
# download_extract.py:98–104
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(EXTRACT_DIR)
```

A malicious `Order_*.zip` containing a member named `../../../etc/passwd` or
`..\..\Windows\System32\malicious.bat` would extract outside `EXTRACT_DIR`.
The S3 bucket is operated by the State of Victoria, so the risk is bounded
(a State-side compromise would have to occur first), but the defense is
trivial:

**Fix:** Before `extractall`, iterate `zf.namelist()` and reject any name
where `os.path.realpath(os.path.join(EXTRACT_DIR, name))` is not under
`os.path.realpath(EXTRACT_DIR)`. Or use `zipfile`'s `extract()` with
explicit path normalization per member.

### H-4. `subprocess.run(..., shell=True)`

```python
# fme_runner.py:184, pozi_runner.py:114
result = subprocess.run(cmd, ..., shell=True)
```

`cmd` is constructed from `config.py` values (FME path + workspace path)
that come from env vars / settings.json. With C-1 (no auth) and C-2 (the
settings.json contents are reachable through `/api/settings` POST), an
attacker can inject shell metacharacters into a setting that ends up in
`cmd`.

**Fix:** Pass the command as a `list` and drop `shell=True`. The comment on
`fme_runner.py:184` says "Important for Windows path handling" but the list
form (with paths as separate list elements) handles spaces fine on Windows
when `shell=False`.

---

## 🟡 MEDIUM

### M-1. DB password in connection-string formatting

```python
# v2_m1_ai_validator/data_processing/database_helper.py:48
f"PWD={self.password}"
```

The full connection string (including the password) becomes a Python string.
If anyone later adds `logger.info("Connecting with %s", conn_str)` — or if
an exception serializing the string is raised and the traceback includes
locals — the password leaks to logs.

**Fix:**
1. Add `__repr__`/`__str__` on the helper that redacts the password.
2. Or: build the connection string inside `pyodbc.connect()` so the local
   variable is short-lived and never logged.
3. Already mitigated by [[security-model-db-creds]] (office-net + 2-week
   rotation), but worth tightening for adopters with different controls.

### M-2. No rate limit on LLM endpoints

Routes that invoke an LLM (`/api/validate-m1`, `/api/smart-validate-m1`,
`/api/enhance-comments`, `/api/error-recovery`, `/api/validate-batch`,
`/api/field-mapping-suggestions`) have no rate limit and no per-request cost
cap. A loop of requests against `/api/validate-batch` with a large CSV could
exhaust the LLM API budget for the day.

**Fix:**
1. `flask-limiter` for per-IP rate limiting.
2. Configurable `MAX_ROWS_PER_REQUEST` env var with a sensible default.
3. Log token usage per request (provider responses already include
   `usage.input_tokens` / `usage.output_tokens` — see `ChatResponse.usage`).

---

## 🟢 LOW

### L-1. Default bind to `0.0.0.0`

```python
# app.py:1169
app.run(debug=False, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
```

Intended for council-LAN access, but means the service is reachable from any
host that can route to the workstation. Acceptable in the documented threat
model; flag here for adopters with stricter requirements.

**Recommendation:** Document the intent in README, and offer a `BIND_HOST`
env var so adopters can lock to `127.0.0.1` without code changes.

### L-2. Flask development server in production

`app.run()` is Flask's built-in dev server, not production-grade (single
worker, no graceful reload, limited concurrency).

**Recommendation:** Document running under `waitress` (Windows-friendly) or
`gunicorn` (POSIX) in the README's "deployment" section.

---

## ⚪ INFO / clean findings

### I-1. SQL is uniformly parameterized ✓

Every `cursor.execute()` call in `database_helper.py` uses `?` placeholders
with parameters in a tuple. No string concatenation, no f-strings inside
SQL. **No SQL injection vector observed** in the audited surface.

Note: `database_relationship_validator.py:62` runs a static `relationships_query`
string with no parameters — verify on a future pass that the query body is
also static.

### I-2. No secret-in-log patterns observed ✓

Grepped for `logger.{info,debug,warning,error}` lines mentioning `password`,
`api_key`, `secret`, `token`. None found leaking secrets into log output.

### I-3. Provider abstraction does NOT log full prompts ✓

The new `v2_m1_ai_validator/providers/` layer logs only the provider name
and model on success — not the message content. Good — prompts may contain
the row data being validated, which on production deployments would include
real PII.

---

## What this audit did NOT cover

- **Static taint analysis** of every request handler's argument flow.
- **Dependency vulnerabilities** (CVEs in pinned versions). Run `pip-audit`
  or `safety` against `requirements.txt` periodically.
- **Browser-side XSS** in the Flask templates. The HTML is largely
  server-rendered and not deeply interactive, but a separate frontend pass
  is recommended.
- **TLS termination.** Assumed handled by a reverse proxy.
- **The Pozi Connect / FME workspaces themselves** — those are
  third-party tools with their own security postures.

## Adopter checklist before deployment

- [ ] Confirm the host runs **only** on the council intranet (no public DNS,
      no port-forward).
- [ ] Add `API_TOKEN` middleware OR put nginx + basic-auth in front
      (fixes C-1).
- [ ] Replace `CORS(app)` with an origin allowlist (fixes H-1).
- [ ] Drop or whitelist the `/api/settings/test` route (fixes C-2).
- [ ] Add zip-slip guard in `download_extract.py` (fixes H-3).
- [ ] Drop `shell=True` from `fme_runner.py` and `pozi_runner.py` (fixes H-4).
- [ ] Run `pip-audit` against the active venv every release cycle.
- [ ] Decide on a TLS strategy if the service is reachable beyond a single
      operator workstation.
