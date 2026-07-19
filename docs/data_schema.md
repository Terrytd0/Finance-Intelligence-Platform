# Data Schema

This document defines the contract for data entering the ingestion pipeline.
It exists so Validation (`docs/validation_rules.md`), the sample fixtures in
`data/sample/`, and the pipeline code in `src/` all agree on the same shape.
Any change here should be reflected in all three.

## transactions

Source of the Revenue, Expense, and Budget vs Actual reports referenced in
`README.md`. One row per financial transaction.

| Column          | Type              | Required | Notes |
|-----------------|-------------------|----------|-------|
| `transaction_id`| string            | yes      | Unique per transaction. Used for deduplication. |
| `client_id`     | string            | yes      | Foreign key into `clients`. |
| `date`          | date (`YYYY-MM-DD`)| yes     | Transaction date. Source files may use other formats (see Cleaning in `docs/architecture.md`); normalization happens before this schema applies. |
| `category`      | string            | yes      | One of: `revenue`, `expense`, `budget`. |
| `description`   | string            | no       | Free text. |
| `amount`        | decimal           | yes      | Positive for revenue/budget, negative for expense outflows. Currency-normalized. |
| `currency`      | string (ISO 4217) | yes      | e.g. `USD`. |

## clients

Reference data joined against `transactions.client_id`.

| Column       | Type   | Required | Notes |
|--------------|--------|----------|-------|
| `client_id`  | string | yes      | Unique. Matches `transactions.client_id`. |
| `client_name`| string | yes      | Display name used in executive reports. |
| `region`     | string | no       | Used for grouping in reporting. |
| `active`     | boolean| yes      | Inactive clients are excluded from new reports but retained for audit history. |

## File formats

Both `transactions` and `clients` may arrive as CSV or Excel (`.xlsx`), per
the "Universal compatibility" choice recorded in `docs/architecture.md`. The
column names and types above apply regardless of source format — format
handling is the responsibility of `src/ingestion/reader.py`, so everything
downstream of it works against a single in-memory representation.

## Open questions

Tracked in `docs/assumptions_and_open_questions.md`. Notably: this schema
assumes uploaded files roughly match these columns; strict schema
enforcement vs. tolerant/mapped ingestion is not yet decided.
