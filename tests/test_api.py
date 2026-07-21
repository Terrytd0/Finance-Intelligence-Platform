import json

import pytest
from fastapi.testclient import TestClient

from src.ai.openai_client import OpenAIRequestError, OpenAITimeoutError
from src.api.main import app, get_llm_client

client = TestClient(app, raise_server_exceptions=False)

VALID_CSV = (
    "transaction_id,client_id,date,category,description,amount,currency\n"
    "T1001,C001,2026-01-05,revenue,Q1 advisory fee,125000.00,USD\n"
    "T1002,C001,2026-01-12,expense,Office lease,-8500.00,USD\n"
)

ALL_ROWS_INVALID_CSV = (
    "transaction_id,client_id,date,category,description,amount,currency\n"
    "T1001,C001,not-a-date,revenue,Bad row,not-a-number,USD\n"
)

VALID_LLM_PAYLOAD = {
    "executive_summary": "Stable period with one notable finding.",
    "anomalies": [
        {
            "severity": "medium",
            "title": "Large lease payment",
            "description": "The office lease payment is unusually large.",
            "evidence": "Office lease: -8500.00 USD.",
            "recommendation": "Review the lease terms.",
        }
    ],
}


class FakeLLMClient:
    """Fake LLMClient for API tests; never touches the network."""

    def __init__(self, response: str | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc

    def complete(self, prompt: str) -> str:
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


def _use_llm_client(fake_client: object) -> None:
    app.dependency_overrides[get_llm_client] = lambda: fake_client


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _upload(content: str | bytes, filename: str = "transactions.csv", content_type: str = "text/csv"):
    return client.post("/analyze", files={"file": (filename, content, content_type)})


def test_health_check_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_returns_anomaly_report_for_valid_csv():
    _use_llm_client(FakeLLMClient(response=json.dumps(VALID_LLM_PAYLOAD)))

    response = _upload(VALID_CSV)

    assert response.status_code == 200
    body = response.json()
    assert body["executive_summary"] == VALID_LLM_PAYLOAD["executive_summary"]
    assert len(body["anomalies"]) == 1
    assert body["anomalies"][0]["severity"] == "medium"
    assert body["anomalies"][0]["title"] == "Large lease payment"
    assert "generated_at" in body


def test_analyze_rejects_unsupported_file_type():
    _use_llm_client(FakeLLMClient(response=json.dumps(VALID_LLM_PAYLOAD)))

    response = _upload(VALID_CSV, filename="transactions.txt", content_type="text/plain")

    assert response.status_code == 400
    assert response.json() == {
        "error": "InvalidFileError",
        "message": "Unsupported file type '.txt'; only .csv is accepted.",
    }


def test_analyze_reports_unreadable_csv_as_csv_processing_error():
    _use_llm_client(FakeLLMClient(response=json.dumps(VALID_LLM_PAYLOAD)))

    response = _upload(b"\xff\xfe\x00\x01not valid utf-8", filename="broken.csv")

    assert response.status_code == 400
    assert response.json()["error"] == "CSVProcessingError"


def test_analyze_reports_validation_failure_when_all_rows_invalid():
    _use_llm_client(FakeLLMClient(response=json.dumps(VALID_LLM_PAYLOAD)))

    response = _upload(ALL_ROWS_INVALID_CSV)

    assert response.status_code == 422
    assert response.json()["error"] == "ValidationFailedError"


def test_analyze_reports_malformed_llm_response_as_anomaly_generation_error():
    _use_llm_client(FakeLLMClient(response="this is not json"))

    response = _upload(VALID_CSV)

    assert response.status_code == 502
    assert response.json()["error"] == "AnomalyGenerationError"


def test_analyze_reports_openai_timeout_as_gateway_timeout():
    _use_llm_client(FakeLLMClient(exc=OpenAITimeoutError("timed out after 3 attempts")))

    response = _upload(VALID_CSV)

    assert response.status_code == 504
    assert response.json()["error"] == "OpenAITimeoutError"


def test_analyze_reports_openai_request_error_as_bad_gateway():
    _use_llm_client(FakeLLMClient(exc=OpenAIRequestError("failed after 3 attempts")))

    response = _upload(VALID_CSV)

    assert response.status_code == 502
    assert response.json()["error"] == "OpenAIServiceError"


def test_analyze_reports_unexpected_exception_as_internal_server_error_without_traceback():
    class ExplodingLLMClient:
        def complete(self, prompt: str) -> str:
            raise RuntimeError("something unexpected and sensitive")

    _use_llm_client(ExplodingLLMClient())

    response = _upload(VALID_CSV)

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "InternalServerError"
    assert "something unexpected and sensitive" not in body["message"]
    assert "Traceback" not in body["message"]
