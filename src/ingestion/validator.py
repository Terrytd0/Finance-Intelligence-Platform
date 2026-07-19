"""Row-level validation, implementing the rules in
docs/validation_rules.md. A row that fails any rule is rejected with the
rule it failed rather than silently dropped, per that document's
"Handling failures" section.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from src.models.financial_schema import REQUIRED_TRANSACTION_FIELDS, VALID_CATEGORIES

# Validation rule identifiers
INVALID_AMOUNT = "invalid_amount"
INVALID_DATE = "invalid_date"
REQUIRED_FIELD = "required_field"
INVALID_CATEGORY = "invalid_category"
DUPLICATE_TRANSACTION_ID = "duplicate_transaction_id"

@dataclass(frozen=True)
class ValidationError:
    row_number: int
    rule: str
    detail: str


def validate_rows(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[ValidationError]]:
    """Split rows into (valid, errors). Row numbers are 1-based and count
    from the first data row (the header is not counted)."""
    valid_rows: list[dict[str, str]] = []
    errors: list[ValidationError] = []
    seen_ids: set[str] = set()

    for row_number, row in enumerate(rows, start=1):
        row_errors = _validate_row(
            row,
            row_number,
            seen_ids,
        )

        if row_errors:
            errors.extend(row_errors)
        else:
            valid_rows.append(row)
            seen_ids.add(row["transaction_id"])

    return valid_rows, errors


def _validate_row(
    row: dict[str, str], row_number: int, seen_ids: set[str]
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    for field in REQUIRED_TRANSACTION_FIELDS:
        if not row.get(field, "").strip():
            errors.append(
                ValidationError(row_number, REQUIRED_FIELD, f"'{field}' is empty")
            )

    if errors:
        # Missing fields make the remaining checks meaningless (e.g. can't
        # parse a missing amount), so stop here for this row.
        return errors

    parsed_date = _parse_date(row["date"])
    if parsed_date is None:
        errors.append(ValidationError(row_number, INVALID_DATE, row["date"]))

    amount = _parse_amount(row["amount"])
    if amount is None:
        errors.append(ValidationError(row_number, INVALID_AMOUNT, row["amount"]))

    if row["category"] not in VALID_CATEGORIES:
        errors.append(
            ValidationError(row_number, INVALID_CATEGORY, row["category"])
        )

    if row["transaction_id"] in seen_ids:
        errors.append(
            ValidationError(
                row_number, DUPLICATE_TRANSACTION_ID, row["transaction_id"]
            )
        )

    return errors


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    

def _parse_amount(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except InvalidOperation:
        return None
