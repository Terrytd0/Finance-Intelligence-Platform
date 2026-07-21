"""FastAPI application exposing the Finance Intelligence Platform over
HTTP.

This module only orchestrates the existing ingestion, analytics and AI
modules (CSV -> pipeline -> KPI engine -> anomaly detector); it contains
no business logic of its own.
"""
import logging
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, UploadFile

from src.ai.anomaly_detector import LLMClient, LLMResponseError, generate_anomaly_report
from src.ai.openai_client import (
    OpenAIClientError,
    OpenAIConfigurationError,
    OpenAILLMClient,
)
from src.ai.openai_client import OpenAITimeoutError as OpenAIClientTimeoutError
from src.analytics.kpi_engine import generate_kpis
from src.api.errors import (
    AnomalyGenerationError,
    ConfigurationError,
    CSVProcessingError,
    InvalidFileError,
    OpenAIServiceError,
    OpenAITimeoutServiceError,
    ValidationFailedError,
    register_exception_handlers,
)
from src.api.schemas import AnomalyReportResponse
from src.config import get_settings
from src.ingestion.pipeline import PipelineResult, run_pipeline
from src.logging_config import configure_logging
from src.models.financial_schema import Transaction

configure_logging()
logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_SUFFIXES = {".csv"}

app = FastAPI(title="Finance Intelligence Platform API", version="1.0.0")
register_exception_handlers(app)


def get_llm_client() -> LLMClient:
    """FastAPI dependency that builds the OpenAI-backed LLM client.

    Overridden in tests via `app.dependency_overrides` to inject a fake
    client so no real network call is ever made.
    """
    try:
        return OpenAILLMClient(settings=get_settings())
    except OpenAIConfigurationError as exc:
        raise ConfigurationError(str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@app.post("/analyze", response_model=AnomalyReportResponse)
def analyze(
    file: UploadFile = File(...),
    llm_client: LLMClient = Depends(get_llm_client),
) -> AnomalyReportResponse:
    """Runs an uploaded CSV through the existing ingestion pipeline, KPI
    engine, and anomaly detector, returning the resulting AnomalyReport.
    """
    transactions = _ingest_upload(file)
    kpis = generate_kpis(transactions)

    try:
        report = generate_anomaly_report(kpis, transactions, llm_client)
    except LLMResponseError as exc:
        raise AnomalyGenerationError(str(exc)) from exc
    except OpenAIClientTimeoutError as exc:
        raise OpenAITimeoutServiceError(str(exc)) from exc
    except OpenAIClientError as exc:
        raise OpenAIServiceError(str(exc)) from exc

    return AnomalyReportResponse.from_domain(report)


def _ingest_upload(file: UploadFile) -> list[Transaction]:
    """Validates the upload's file type, runs it through the existing
    ingestion pipeline, and returns its transactions.

    Raises InvalidFileError for an unsupported file type, CSVProcessingError
    if the pipeline cannot read the file at all, and ValidationFailedError
    if every row fails validation.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise InvalidFileError(
            f"Unsupported file type '{suffix or 'unknown'}'; only .csv is accepted."
        )

    tmp_path = _save_upload_to_temp_file(file, suffix)
    try:
        result = _run_pipeline_safely(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not result.transactions:
        error_count = len(result.errors)
        first_detail = result.errors[0].detail if result.errors else "no rows found"
        raise ValidationFailedError(
            f"No valid transactions found in upload ({error_count} row error(s); "
            f"first: {first_detail})."
        )

    return result.transactions


def _save_upload_to_temp_file(file: UploadFile, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        return Path(tmp.name)


def _run_pipeline_safely(path: Path) -> PipelineResult:
    try:
        return run_pipeline(path)
    except Exception as exc:
        raise CSVProcessingError(f"Failed to process uploaded file: {exc}") from exc
