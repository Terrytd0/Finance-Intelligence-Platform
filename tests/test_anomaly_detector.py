import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.ai.anomaly_detector import (
    AnomalyReport,
    FinancialAnomaly,
    LLMResponseError,
    generate_anomaly_report,
)
from src.analytics.kpi_engine import FinancialKPIs, generate_kpis
from src.models.financial_schema import Transaction


def _transaction(
    transaction_id: str,
    client_id: str,
    date_str: str,
    category: str,
    amount: str,
    description: str = "",
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        client_id=client_id,
        date=date.fromisoformat(date_str),
        category=category,
        amount=Decimal(amount),
        currency="USD",
        description=description,
    )


TRANSACTIONS = [
    _transaction("T1", "C001", "2026-01-05", "revenue", "125000.00", "Advisory fee"),
    _transaction("T2", "C001", "2026-01-12", "expense", "-8500.00", "Office lease"),
    _transaction("T3", "C002", "2026-01-15", "revenue", "64200.50", "Management fee"),
    _transaction("T4", "C002", "2026-01-20", "budget", "15000.00", "Q1 marketing budget"),
    _transaction("T5", "C001", "2026-02-01", "expense", "-3200.75", "Software licensing"),
    _transaction("T6", "C002", "2026-02-10", "revenue", "42000.00", "Performance fee"),
]

KPIS: FinancialKPIs = generate_kpis(TRANSACTIONS)


def _anomaly_dict(**overrides: str) -> dict[str, str]:
    base = {
        "severity": "high",
        "title": "Concentrated revenue from a single client",
        "description": "Client C001 accounts for the majority of revenue this period.",
        "evidence": "C001 revenue is 125000.00 out of 231200.50 total revenue.",
        "recommendation": "Diversify the client base to reduce concentration risk.",
    }
    base.update(overrides)
    return base


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "executive_summary": "Overall financial position is stable with one notable finding.",
        "anomalies": [_anomaly_dict()],
    }
    base.update(overrides)
    return base


class RecordingLLMClient:
    """Fake LLMClient that records the prompt it was sent and returns a
    fixed canned response, so tests never touch a real network or SDK."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.received_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.received_prompt = prompt
        return self.response


def test_generate_anomaly_report_returns_full_report():
    anomalies = [
        _anomaly_dict(title="Large lease payment", severity="medium"),
        _anomaly_dict(title="Client concentration risk", severity="high"),
    ]
    client = RecordingLLMClient(json.dumps(_payload(anomalies=anomalies)))

    report = generate_anomaly_report(KPIS, TRANSACTIONS, client)

    assert isinstance(report, AnomalyReport)
    assert report.executive_summary == "Overall financial position is stable with one notable finding."
    assert isinstance(report.generated_at, datetime)
    assert len(report.anomalies) == 2

    first, second = report.anomalies
    assert isinstance(first, FinancialAnomaly)
    assert first.severity == "medium"
    assert first.title == "Large lease payment"
    assert first.description == _anomaly_dict()["description"]
    assert first.evidence == _anomaly_dict()["evidence"]
    assert first.recommendation == _anomaly_dict()["recommendation"]
    assert second.severity == "high"
    assert second.title == "Client concentration risk"


def test_markdown_code_fences_are_stripped():
    fenced_response = "```json\n" + json.dumps(_payload()) + "\n```"
    client = RecordingLLMClient(fenced_response)

    report = generate_anomaly_report(KPIS, TRANSACTIONS, client)
    
    payload = _payload()

    assert report.executive_summary == payload["executive_summary"]
    assert len(report.anomalies) == 1
    assert report.anomalies[0].title == _anomaly_dict()["title"]


def test_malformed_json_raises_llm_response_error():
    client = RecordingLLMClient("this is not json at all")

    with pytest.raises(LLMResponseError):
        generate_anomaly_report(KPIS, TRANSACTIONS, client)


def test_missing_executive_summary_raises():
    payload = _payload()
    del payload["executive_summary"]
    client = RecordingLLMClient(json.dumps(payload))

    with pytest.raises(LLMResponseError):
        generate_anomaly_report(KPIS, TRANSACTIONS, client)


def test_missing_anomalies_raises():
    payload = _payload()
    del payload["anomalies"]
    client = RecordingLLMClient(json.dumps(payload))

    with pytest.raises(LLMResponseError):
        generate_anomaly_report(KPIS, TRANSACTIONS, client)


@pytest.mark.parametrize("missing_field", ["severity", "title", "description", "evidence", "recommendation"])
def test_anomaly_missing_required_field_raises(missing_field: str):
    anomaly = _anomaly_dict()
    del anomaly[missing_field]
    client = RecordingLLMClient(json.dumps(_payload(anomalies=[anomaly])))

    with pytest.raises(LLMResponseError):
        generate_anomaly_report(KPIS, TRANSACTIONS, client)


def test_invalid_severity_raises():
    anomaly = _anomaly_dict(severity="extreme")
    client = RecordingLLMClient(json.dumps(_payload(anomalies=[anomaly])))

    with pytest.raises(LLMResponseError):
        generate_anomaly_report(KPIS, TRANSACTIONS, client)

def test_severity_is_normalized_to_lowercase():
    anomaly = _anomaly_dict(severity="HIGH")
    client = RecordingLLMClient(
        json.dumps(_payload(anomalies=[anomaly]))
    )

    report = generate_anomaly_report(KPIS, TRANSACTIONS, client)

    assert report.anomalies[0].severity == "high"

@pytest.mark.parametrize("empty_field", ["title", "description", "evidence", "recommendation"])
def test_empty_string_fields_are_rejected(empty_field: str):
    anomaly = _anomaly_dict(**{empty_field: ""})
    client = RecordingLLMClient(json.dumps(_payload(anomalies=[anomaly])))

    with pytest.raises(LLMResponseError):
        generate_anomaly_report(KPIS, TRANSACTIONS, client)


def test_build_anomaly_prompt_output_is_sent_to_llm_client():
    client = RecordingLLMClient(json.dumps(_payload()))

    generate_anomaly_report(KPIS, TRANSACTIONS, client)

    assert client.received_prompt is not None
    assert "Total Revenue" in client.received_prompt
    assert "Total Expenses" in client.received_prompt
    assert "Net Profit" in client.received_prompt
    assert "Respond with ONLY valid JSON" in client.received_prompt
    assert "Never invent numbers" in client.received_prompt


def test_generated_at_is_timezone_aware():
    client = RecordingLLMClient(json.dumps(_payload()))

    report = generate_anomaly_report(KPIS, TRANSACTIONS, client)

    assert report.generated_at.tzinfo is not None
    assert report.generated_at.utcoffset() is not None
    
