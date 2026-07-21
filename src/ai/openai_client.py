"""OpenAI-backed implementation of the `LLMClient` protocol expected by
src/ai/anomaly_detector.py.

This module owns everything provider-specific: SDK calls, timeouts, and
retrying transient network/API failures with exponential backoff. It never
parses or validates the model's response content -- that stays in
anomaly_detector.py, which only ever sees a plain string via `complete()`.
"""
import logging
import time

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Failures worth retrying: transient connectivity issues, timeouts, rate
# limiting, and the provider's own 5xx errors. Anything else (bad request,
# auth failure, ...) will not succeed on retry.
RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)

INITIAL_BACKOFF_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0


class OpenAIClientError(Exception):
    """Base exception for all OpenAILLMClient failures."""


class OpenAIConfigurationError(OpenAIClientError):
    """Raised when the client is missing required configuration (e.g. no
    API key)."""


class OpenAITimeoutError(OpenAIClientError):
    """Raised when every attempt, including retries, timed out."""


class OpenAIRequestError(OpenAIClientError):
    """Raised when the OpenAI request fails and cannot be retried further,
    for reasons other than a timeout (connection errors, rate limits,
    5xx responses, or any other API error)."""


class OpenAIResponseError(OpenAIClientError):
    """Raised when OpenAI returns a response with no usable text content.
    Never retried -- a malformed response shape will not fix itself."""


class OpenAILLMClient:
    """Adapts the official OpenAI SDK to the `complete(prompt) -> str`
    interface used throughout the AI layer.

    All tunables (model, timeout, temperature, retry count) default to
    `src.config.Settings` but can be overridden per instance, e.g. for
    tests or ad-hoc scripts.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        temperature: float | None = None,
        max_retries: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        settings = settings or get_settings()

        resolved_api_key = api_key or settings.openai_api_key
        if not resolved_api_key:
            raise OpenAIConfigurationError(
                "OPENAI_API_KEY is not configured. Set it as an environment "
                "variable or pass api_key explicitly."
            )

        self._model = model or settings.openai_model
        self._timeout = timeout if timeout is not None else settings.openai_timeout
        self._temperature = (
            temperature if temperature is not None else settings.openai_temperature
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.openai_retry_count
        )
        self._client = OpenAI(api_key=resolved_api_key, timeout=self._timeout)

    def complete(self, prompt: str) -> str:
        """Sends `prompt` to the configured OpenAI chat model and returns
        its plain text response.

        Transient network/API failures are retried up to `max_retries`
        times with exponential backoff, logging every retry attempt. After
        the final failed attempt, raises `OpenAITimeoutError` (if the last
        failure was a timeout) or `OpenAIRequestError` (for any other
        retryable failure). Non-retryable API errors and malformed
        responses raise immediately without retrying.
        """
        delay = INITIAL_BACKOFF_SECONDS
        last_exc: Exception | None = None
        total_attempts = self._max_retries + 1

        for attempt in range(1, total_attempts + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    timeout=self._timeout,
                    messages=[{"role": "user", "content": prompt}],
                )
                return self._extract_text(response)
            except RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt >= total_attempts:
                    break
                logger.warning(
                    "OpenAI request attempt %d/%d failed (%s: %s); retrying in %.1fs",
                    attempt,
                    total_attempts,
                    type(exc).__name__,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay *= BACKOFF_MULTIPLIER
            except APIError as exc:
                logger.error("OpenAI request failed with a non-retryable error: %s", exc)
                raise OpenAIRequestError(f"OpenAI request failed: {exc}") from exc

        logger.error(
            "OpenAI request failed after %d attempt(s): %s", total_attempts, last_exc
        )
        if isinstance(last_exc, APITimeoutError):
            raise OpenAITimeoutError(
                f"OpenAI request timed out after {total_attempts} attempt(s)."
            ) from last_exc
        raise OpenAIRequestError(
            f"OpenAI request failed after {total_attempts} attempt(s): {last_exc}"
        ) from last_exc

    def _extract_text(self, response: object) -> str:
        try:
            content = response.choices[0].message.content  # type: ignore[attr-defined]
        except (AttributeError, IndexError) as exc:
            raise OpenAIResponseError("OpenAI response contained no choices.") from exc

        if not content or not content.strip():
            raise OpenAIResponseError("OpenAI response content was empty.")
        return content
