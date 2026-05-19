"""Shared Bearer-token authentication for the Flask services.

Reads the comma-separated `API_TOKEN` env var; if it's empty, authentication
is **disabled** and a loud warning is logged at startup. If it's set, every
non-exempt route requires `Authorization: Bearer <one of the tokens>`.

Call `register_auth(app, exempt_paths=...)` once during each Flask app's
initialization.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)


def _expected_tokens() -> set[str]:
    """Parse the API_TOKEN env var into a set of valid tokens.

    Multiple tokens can be configured by comma-separating them — useful for
    per-operator tokens or for rotating without downtime.
    """
    raw = os.getenv("API_TOKEN", "").strip()
    if not raw:
        return set()
    return {t.strip() for t in raw.split(",") if t.strip()}


def _is_exempt(path: str, exempt: Iterable[str]) -> bool:
    """Match `path` against an exempt list. Trailing `/*` means prefix match."""
    for pattern in exempt:
        if pattern.endswith("/*"):
            if path.startswith(pattern[:-2]):
                return True
        elif path == pattern:
            return True
    return False


# Default exempt paths: the web UI itself, static assets, and health checks.
# Adopters can override per-app via the `exempt_paths` argument.
DEFAULT_EXEMPT_PATHS: tuple[str, ...] = (
    "/",
    "/static/*",
    "/api/health",
    "/api/health/validation-api",
)


def register_auth(
    app: Flask,
    *,
    exempt_paths: tuple[str, ...] = DEFAULT_EXEMPT_PATHS,
) -> None:
    """Install a `before_request` hook on `app` that enforces Bearer-token auth.

    Behavior:
    - If `API_TOKEN` env var is empty: auth is DISABLED. A warning is logged
      so operators know the service is wide-open.
    - If `API_TOKEN` is set: every request to a non-exempt path must include
      `Authorization: Bearer <token>` matching one of the configured tokens.
    - OPTIONS requests are always exempt (CORS preflight).
    """
    tokens = _expected_tokens()
    if not tokens:
        logger.warning(
            "API_TOKEN not set — authentication is DISABLED. Anyone with "
            "network access can call this service. Set API_TOKEN in .env "
            "to require Bearer-token auth on every non-exempt route."
        )
    else:
        logger.info(
            "API_TOKEN auth enabled (%d valid token%s). Exempt paths: %s",
            len(tokens),
            "" if len(tokens) == 1 else "s",
            ", ".join(exempt_paths) or "(none)",
        )

    @app.before_request
    def _check_token():
        # CORS preflight requests must not require auth — the browser sends
        # them without the Authorization header by design.
        if request.method == "OPTIONS":
            return None

        # Re-read on every request so token rotation doesn't need a restart.
        # Negligible cost — just an env-var read + set comprehension.
        current_tokens = _expected_tokens()
        if not current_tokens:
            return None  # Auth disabled

        if _is_exempt(request.path, exempt_paths):
            return None

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({
                "error": "Missing or malformed Authorization header. "
                         "Send `Authorization: Bearer <token>`."
            }), 401

        provided = auth_header[len("Bearer "):].strip()
        if provided not in current_tokens:
            logger.warning(
                "Rejected request to %s from %s — invalid token",
                request.path,
                request.remote_addr,
            )
            return jsonify({"error": "Invalid API token"}), 401

        return None
