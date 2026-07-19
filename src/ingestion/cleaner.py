"""Normalizes rows that have already passed validation, per the Cleaning
step in docs/architecture.md: trim whitespace and standardize currency
codes. Rows reaching this module are assumed valid — cleaning does not
re-validate.
"""


def clean_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [_clean_row(row) for row in rows]


def _clean_row(row: dict[str, str]) -> dict[str, str]:
    cleaned = {key: value.strip() for key, value in row.items()}
    cleaned["currency"] = cleaned["currency"].upper()
    return cleaned
