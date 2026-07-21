from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from openai import BadRequestError

from src.ai.openai_client import (
    OpenAIClientError,
    OpenAIConfigurationError,
    OpenAILLMClient,
    OpenAIRequestError,
    OpenAIResponseError,
    OpenAITimeoutError,
)
from src.config import Settings


def _settings(**overrides: object) -> Settings:
    base = dict(
        openai_api_key="sk-test-key",
        openai_model="gpt-4o-mini",
        openai_timeout=5.0,
        openai_temperature=0.2,
        openai_retry_count=2,
        log_level="INFO",
    )
    base.update(overrides)
    return Settings(**base)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_request())


def _connection_error() -> APIConnectionError:
    return APIConnectionError(request=_request())


def _timeout_error() -> APITimeoutError:
    return APITimeoutError(request=_request())


def _rate_limit_error() -> RateLimitError:
    return RateLimitError("rate limited", response=_response(429), body=None)


def _internal_server_error() -> InternalServerError:
    return InternalServerError("server error", response=_response(500), body=None)


def _bad_request_error() -> BadRequestError:
    return BadRequestError("bad request", response=_response(400), body=None)


def _chat_completion(text: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=text))]
    return completion


@patch("src.ai.openai_client.OpenAI")
def test_complete_returns_text_on_success(mock_openai_cls: MagicMock) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.return_value = _chat_completion("hello world")

    client = OpenAILLMClient(settings=_settings())
    result = client.complete("prompt")

    assert result == "hello world"
    mock_client.chat.completions.create.assert_called_once()


def test_missing_api_key_raises_configuration_error() -> None:
    with pytest.raises(OpenAIConfigurationError):
        OpenAILLMClient(settings=_settings(openai_api_key=""))


@patch("src.ai.openai_client.time.sleep")
@patch("src.ai.openai_client.OpenAI")
def test_retries_on_transient_failure_then_succeeds(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.side_effect = [
        _connection_error(),
        _chat_completion("recovered"),
    ]

    client = OpenAILLMClient(settings=_settings(openai_retry_count=2))
    result = client.complete("prompt")

    assert result == "recovered"
    assert mock_client.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once()


@patch("src.ai.openai_client.time.sleep")
@patch("src.ai.openai_client.OpenAI")
def test_retry_uses_exponential_backoff(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.side_effect = [
        _connection_error(),
        _connection_error(),
        _chat_completion("ok"),
    ]

    client = OpenAILLMClient(settings=_settings(openai_retry_count=2))
    client.complete("prompt")

    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [1.0, 2.0]


@patch("src.ai.openai_client.time.sleep")
@patch("src.ai.openai_client.OpenAI")
def test_exhausted_retries_raise_request_error(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.side_effect = _rate_limit_error()

    client = OpenAILLMClient(settings=_settings(openai_retry_count=2))

    with pytest.raises(OpenAIRequestError):
        client.complete("prompt")

    assert mock_client.chat.completions.create.call_count == 3
    assert mock_sleep.call_count == 2


@patch("src.ai.openai_client.time.sleep")
@patch("src.ai.openai_client.OpenAI")
def test_exhausted_timeouts_raise_timeout_error(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.side_effect = _timeout_error()

    client = OpenAILLMClient(settings=_settings(openai_retry_count=1))

    with pytest.raises(OpenAITimeoutError):
        client.complete("prompt")

    assert mock_client.chat.completions.create.call_count == 2


@patch("src.ai.openai_client.time.sleep")
@patch("src.ai.openai_client.OpenAI")
def test_internal_server_error_is_retried(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.side_effect = [
        _internal_server_error(),
        _chat_completion("ok"),
    ]

    client = OpenAILLMClient(settings=_settings(openai_retry_count=2))
    result = client.complete("prompt")

    assert result == "ok"
    assert mock_client.chat.completions.create.call_count == 2


@patch("src.ai.openai_client.time.sleep")
@patch("src.ai.openai_client.OpenAI")
def test_non_retryable_api_error_raises_immediately(
    mock_openai_cls: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.side_effect = _bad_request_error()

    client = OpenAILLMClient(settings=_settings(openai_retry_count=3))

    with pytest.raises(OpenAIRequestError):
        client.complete("prompt")

    mock_client.chat.completions.create.assert_called_once()
    mock_sleep.assert_not_called()


@patch("src.ai.openai_client.OpenAI")
def test_empty_response_content_raises_response_error_without_retry(
    mock_openai_cls: MagicMock,
) -> None:
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.return_value = _chat_completion("   ")

    client = OpenAILLMClient(settings=_settings(openai_retry_count=3))

    with pytest.raises(OpenAIResponseError):
        client.complete("prompt")

    mock_client.chat.completions.create.assert_called_once()


@patch("src.ai.openai_client.OpenAI")
def test_response_with_no_choices_raises_response_error(mock_openai_cls: MagicMock) -> None:
    mock_client = mock_openai_cls.return_value
    completion = MagicMock()
    completion.choices = []
    mock_client.chat.completions.create.return_value = completion

    client = OpenAILLMClient(settings=_settings())

    with pytest.raises(OpenAIResponseError):
        client.complete("prompt")


def test_openai_timeout_error_is_an_openai_client_error() -> None:
    assert issubclass(OpenAITimeoutError, OpenAIClientError)
    assert issubclass(OpenAIRequestError, OpenAIClientError)
    assert issubclass(OpenAIResponseError, OpenAIClientError)
    assert issubclass(OpenAIConfigurationError, OpenAIClientError)
