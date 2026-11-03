"""Runtime settings read from environment variables.

The service never hard-codes a key or a model ID. Everything that changes
between a laptop, CI and production comes from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL = "gemini-flash-latest"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable view of the configuration the service needs."""

    model: str = DEFAULT_MODEL
    api_key: str | None = None
    enterprise: bool = False
    project: str | None = None
    location: str = "global"
    timeout_ms: int = 60_000
    retry_attempts: int = 4
    max_prompt_chars: int = 20_000

    @property
    def backend(self) -> str:
        return "agent-platform" if self.enterprise else "developer-api"

    @property
    def configured(self) -> bool:
        """True when the process has enough credentials to call Gemini."""
        if self.enterprise:
            return bool(self.project)
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> Settings:
        # GOOGLE_API_KEY wins over GEMINI_API_KEY, matching the SDK's own rule.
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        enterprise = _env_bool("GOOGLE_GENAI_USE_ENTERPRISE") or _env_bool(
            "GOOGLE_GENAI_USE_VERTEXAI"
        )
        return cls(
            model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
            api_key=api_key or None,
            enterprise=enterprise,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None,
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            timeout_ms=int(os.environ.get("GEMINI_TIMEOUT_MS", "60000")),
            retry_attempts=int(os.environ.get("GEMINI_RETRY_ATTEMPTS", "4")),
            max_prompt_chars=int(os.environ.get("MAX_PROMPT_CHARS", "20000")),
        )
