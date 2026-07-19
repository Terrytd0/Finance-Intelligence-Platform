"""Orchestrates the ingestion stages shown in docs/architecture.md, up to
(but not including) the KPI Engine: Read -> Validate -> Clean ->
Deduplicate -> build Transaction records.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.ingestion.cleaner import clean_rows
from src.ingestion.deduplicator import dedupe_rows
from src.ingestion.reader import read_rows
from src.ingestion.validator import ValidationError, validate_rows
from src.models.financial_schema import Transaction


@dataclass(frozen=True)
class PipelineResult:
    transactions: list[Transaction]
    errors: list[ValidationError]


def run_pipeline(path: str | Path) -> PipelineResult:
    raw_rows = read_rows(path)
    valid_rows, errors = validate_rows(raw_rows)
    cleaned_rows = clean_rows(valid_rows)
    deduped_rows = dedupe_rows(cleaned_rows)
    transactions = [_to_transaction(row) for row in deduped_rows]
    return PipelineResult(transactions=transactions, errors=errors)


def _to_transaction(row: dict[str, str]) -> Transaction:
    return Transaction(
        transaction_id=row["transaction_id"],
        client_id=row["client_id"],
        date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
        category=row["category"],
        amount=Decimal(row["amount"]),
        currency=row["currency"],
        description=row.get("description", ""),
    )
