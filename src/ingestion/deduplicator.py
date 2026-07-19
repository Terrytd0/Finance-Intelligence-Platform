"""Drops exact-duplicate rows, e.g. from the same file being uploaded
twice. This is distinct from validator.py's duplicate-transaction_id check
(a data integrity error to report) — see "Deduplication" in
docs/validation_rules.md.
"""


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        key = tuple(row.items())
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped
