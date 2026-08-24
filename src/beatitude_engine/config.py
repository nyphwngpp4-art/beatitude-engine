"""Environment configuration.

All secrets come from environment variables — never hardcoded, never logged.
A plain `.env` file at the repo root is honored for local development (existing
environment variables always win).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_ENV_LOADED = False


def _load_dotenv() -> None:
    """Minimal .env loader: KEY=VALUE lines, '#' comments, no interpolation."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: str | None = None) -> str | None:
    _load_dotenv()
    value = os.environ.get(name, default)
    return value if value not in ("", None) else default


def require_env(name: str, hint: str) -> str:
    value = env(name)
    if value is None:
        from .errors import ConfigError

        raise ConfigError(f"Missing environment variable {name}. {hint}")
    return value


# Model defaults; override via env without touching code.
GROK_MODEL_DEFAULT = "grok-4"
ANTHROPIC_MODEL_DEFAULT = "claude-opus-5"
OPENAI_MODEL_DEFAULT = "gpt-5"

XAI_BASE_URL_DEFAULT = "https://api.x.ai/v1"
