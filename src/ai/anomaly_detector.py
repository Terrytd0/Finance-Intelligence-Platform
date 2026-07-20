"""Turns FinancialKPIs + transactions into an AI-generated AnomalyReport.

This module never performs financial calculations and never changes KPI
values -- it only builds a prompt from data already computed by
src/analytics/kpi_engine.py, sends it to an injected LLM client, and
parses/validates the response into typed dataclasses. It has no
dependency on any specific LLM provider.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from src.ai.prompt_builder import build_anomaly_prompt
from src.analytics.kpi_engine import FinancialKPIs
from src.models.financial_schema import Transaction

VALID_SEVERITIES = {"low", "medium", "high", "critical"}

REQUIRED_ANOMALY_FIELDS = (
    "severity",
    "title",
    "description",
    "evidence",
    "recommendation",
)


class LLMClient(Protocol):
    """Structural interface expected of an injected LLM client.

    Provider-specific clients (OpenAI, Anthropic, ...) can be adapted to
    this interface without this module knowing about them.
    """

    def complete(self, prompt: str) -> str:
        """Sends `prompt` to the model and returns its raw text response."""
        ...


class LLMResponseError(Exception):
    """Raised when an LLM response cannot be parsed or validated into an
    AnomalyReport."""


@dataclass(frozen=True)
class FinancialAnomaly:
    """One anomaly finding reasoned over supplied financial data."""

    severity: str
    title: str
    description: str
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class AnomalyReport:
    """The AI layer's full response for one batch of financial data."""

    executive_summary: str
    anomalies: list[FinancialAnomaly]
    generated_at: datetime


def generate_anomaly_report(
    kpis: FinancialKPIs,
    transactions: list[Transaction],
    llm_client: LLMClient,
) -> AnomalyReport:
    """Builds a prompt from `kpis` and `transactions`, sends it to
    `llm_client`, and returns the parsed, validated AnomalyReport.

    Raises LLMResponseError if the client's response is not valid JSON or
    does not match the expected schema.
    """
    prompt = build_anomaly_prompt(kpis, transactions)
    raw_response = llm_client.complete(prompt)
    payload = _parse_response(raw_response)
    _validate_payload(payload)

    anomalies = [_to_anomaly(item) for item in payload["anomalies"]]
    return AnomalyReport(
        executive_summary=payload["executive_summary"],
        anomalies=anomalies,
        generated_at=datetime.now(timezone.utc),
    )


def _parse_response(raw_response: str) -> Any:
    """Parses the LLM's raw text response as JSON, tolerating a wrapping
    markdown code fence some models add despite instructions not to."""
    candidate = _strip_code_fence(raw_response.strip())
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM response is not valid JSON: {exc}") from exc


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise LLMResponseError("LLM response must be a JSON object.")

    summary = payload.get("executive_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise LLMResponseError("LLM response is missing a non-empty 'executive_summary'.")

    anomalies = payload.get("anomalies")
    if not isinstance(anomalies, list):
        raise LLMResponseError("LLM response is missing an 'anomalies' list.")

    for index, item in enumerate(anomalies):
        _validate_anomaly(item, index)


def _validate_anomaly(item: Any, index: int) -> None:
    if not isinstance(item, dict):
        raise LLMResponseError(f"anomalies[{index}] must be a JSON object.")

    for field in REQUIRED_ANOMALY_FIELDS:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise LLMResponseError(
                f"anomalies[{index}] is missing a non-empty '{field}'."
            )

    severity = item["severity"].strip().lower()
    if severity not in VALID_SEVERITIES:
        raise LLMResponseError(
            f"anomalies[{index}] has invalid severity '{item['severity']}'; "
            f"expected one of {sorted(VALID_SEVERITIES)}."
        )


def _to_anomaly(item: dict[str, str]) -> FinancialAnomaly:
    return FinancialAnomaly(
        severity=item["severity"].strip().lower(),
        title=item["title"].strip(),
        description=item["description"].strip(),
        evidence=item["evidence"].strip(),
        recommendation=item["recommendation"].strip(),
    )
