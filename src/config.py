"""Centralized runtime configuration for the production API layer.

Every value is read from environment variables, with sensible defaults for
local development. Nothing here is hardcoded as a secret -- OPENAI_API_KEY
must be supplied by the environment.
"""
import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 30.0
DEFAULT_OPENAI_TEMPERATURE = 0.2
DEFAULT_OPENAI_RETRY_COUNT = 3
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True)
class Settings:
    """Process-wide configuration, sourced entirely from environment
    variables."""

    openai_api_key: str
    openai_model: str
    openai_timeout: float
    openai_temperature: float
    openai_retry_count: int
    log_level: str


def _load_settings() -> Settings:
    return Settings(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        openai_timeout=float(
            os.environ.get("OPENAI_TIMEOUT_SECONDS", DEFAULT_OPENAI_TIMEOUT_SECONDS)
        ),
        openai_temperature=float(
            os.environ.get("OPENAI_TEMPERATURE", DEFAULT_OPENAI_TEMPERATURE)
        ),
        openai_retry_count=int(
            os.environ.get("OPENAI_RETRY_COUNT", DEFAULT_OPENAI_RETRY_COUNT)
        ),
        log_level=os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL),
    )


@lru_cache
def get_settings() -> Settings:
    """Returns the process-wide Settings, loaded once from environment
    variables and cached for subsequent calls.

    Tests that need different environment variables should call
    `get_settings.cache_clear()` after patching `os.environ`.
    """
    return _load_settings()
