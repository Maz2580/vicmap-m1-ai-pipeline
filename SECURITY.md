# Security policy

## Supported versions

This project is pre-1.0. Only `main` receives security fixes. We do not
backport to older commits.

## Threat model

This codebase is designed for deployment on a **council intranet behind a
perimeter firewall**, not on the open internet. See [SECURITY_AUDIT.md](SECURITY_AUDIT.md)
for the full audit and the adopter checklist before deployment.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security findings.** Use one
of the following private channels instead:

1. **Preferred** — open a private security advisory:
   <https://github.com/Maz2580/vicmap-m1-ai-pipeline/security/advisories/new>
2. Or email the maintainer directly.

When reporting, please include:

- A description of the vulnerability and its impact.
- Steps to reproduce, including any required configuration.
- The commit hash or release tag you tested against.

You should receive an acknowledgement within ~7 days. If the report is
confirmed, we'll aim to ship a fix on `main` within 30 days and credit
you in the release notes unless you prefer to remain anonymous.

## Out of scope

- Issues that require an already-compromised host (e.g. "if an attacker can
  edit `.env`, they can…").
- Findings already documented as "Open" in `SECURITY_AUDIT.md`.
- Denial-of-service via expensive LLM calls — known issue, tracked as M-2.
