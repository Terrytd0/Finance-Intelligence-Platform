"""Pydantic response models mirroring the domain dataclasses in
src.ai.anomaly_detector. These exist only for API serialization and
OpenAPI documentation -- they carry no business logic.
"""
from datetime import datetime

from pydantic import BaseModel

from src.ai.anomaly_detector import AnomalyReport, FinancialAnomaly


class FinancialAnomalyResponse(BaseModel):
    """API representation of a single `FinancialAnomaly`."""

    severity: str
    title: str
    description: str
    evidence: str
    recommendation: str

    @classmethod
    def from_domain(cls, anomaly: FinancialAnomaly) -> "FinancialAnomalyResponse":
        return cls(
            severity=anomaly.severity,
            title=anomaly.title,
            description=anomaly.description,
            evidence=anomaly.evidence,
            recommendation=anomaly.recommendation,
        )


class AnomalyReportResponse(BaseModel):
    """API representation of a full `AnomalyReport`."""

    executive_summary: str
    anomalies: list[FinancialAnomalyResponse]
    generated_at: datetime

    @classmethod
    def from_domain(cls, report: AnomalyReport) -> "AnomalyReportResponse":
        return cls(
            executive_summary=report.executive_summary,
            anomalies=[FinancialAnomalyResponse.from_domain(a) for a in report.anomalies],
            generated_at=report.generated_at,
        )
