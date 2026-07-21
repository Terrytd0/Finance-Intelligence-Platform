"""Structured API error types and the FastAPI exception handlers that turn
them (and any unexpected exception) into JSON responses of the shape
`{"error": <type>, "message": <str>}`. Raw tracebacks are never returned
to callers.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base class for API errors that map directly to a structured JSON
    response. Subclasses set `status_code` and `error_type`."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "APIError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidFileError(APIError):
    """The upload was missing, empty, or not a supported file type."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "InvalidFileError"


class CSVProcessingError(APIError):
    """The upload could not be read by the ingestion pipeline."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "CSVProcessingError"


class ValidationFailedError(APIError):
    """Every row in the upload failed validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_type = "ValidationFailedError"


class AnomalyGenerationError(APIError):
    """The LLM's response could not be parsed/validated into an
    AnomalyReport."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_type = "AnomalyGenerationError"


class OpenAIServiceError(APIError):
    """The OpenAI request failed after exhausting retries."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_type = "OpenAIServiceError"


class OpenAITimeoutServiceError(OpenAIServiceError):
    """The OpenAI request timed out on every attempt."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    error_type = "OpenAITimeoutError"


class ConfigurationError(APIError):
    """The service is missing required configuration (e.g. no API key)."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type = "ConfigurationError"


def register_exception_handlers(app: FastAPI) -> None:
    """Registers handlers so every `APIError` -- and any exception that
    slips through unhandled -- surfaces as structured JSON with an
    appropriate HTTP status code instead of a raw traceback."""

    @app.exception_handler(APIError)
    async def _handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        logger.warning("%s: %s", exc.error_type, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_type, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception while processing request")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred.",
            },
        )
