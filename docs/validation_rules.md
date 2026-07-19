# Validation Rules

Concrete rules enforced by the Validation stage of the pipeline
(`docs/architecture.md`), implemented in `src/ingestion/validator.py`. Each
sample file in `data/sample/` is a fixture for one of these rules, and is
exercised by `tests/test_ingestion.py`.

## Schema validation

- All required columns from `docs/data_schema.md` must be present.
- Unknown columns are allowed and passed through unused, rather than
  rejecting the file — see "strict vs. tolerant ingestion" in
  `docs/assumptions_and_open_questions.md`.

## Row-level rules

| Rule | Failure mode | Sample fixture |
|------|--------------|-----------------|
| Required fields are non-empty | Row missing `transaction_id`, `client_id`, `date`, `category`, or `amount` | `data/sample/missing_values.csv` |
| `date` parses as a valid calendar date | Unparseable or malformed date string | `data/sample/invalid_data.csv` |
| `amount` parses as a number | Non-numeric `amount` (e.g. stray text, currency symbols left in) | `data/sample/invalid_data.csv` |
| `category` is one of `revenue`, `expense`, `budget` | Any other value | `data/sample/invalid_data.csv` |
| `transaction_id` is unique within the file | Duplicate ID appears more than once | `data/sample/duplicate_transactions.csv` |

A file containing only rows that pass every rule is
`data/sample/valid_transactions.csv`.

## Handling failures

Per `docs/architecture.md`'s Error Handling section:

- A row that fails a rule is **rejected**, not silently dropped — it is
  reported back with the row number and the rule it failed.
- A file is only rejected outright if it fails schema validation (missing
  required columns) or has a rejection rate so high the file is likely the
  wrong file entirely. The exact threshold is not yet decided (see
  `docs/assumptions_and_open_questions.md`).
- Rows that pass validation continue to Cleaning
  (`src/ingestion/cleaner.py`); rejected rows do not.

## Deduplication

Deduplication is treated as a separate concern from validation: a duplicate
`transaction_id` is a validation failure (data integrity issue to report),
while `src/ingestion/deduplicator.py` handles exact duplicate *rows* that can
occur from re-uploading the same file, which is safe to drop rather than
reject.
