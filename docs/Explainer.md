# Explainer

**Date:** 2026-07-19

## What this covers

This document records the work done to scaffold the repository into the
target structure (`docs/`, `data/`, `src/`, `tests/`) that had previously
existed only as directories with placeholder content or hadn't existed at
all. It lists every file created or modified, and what each one does, so
the change is traceable without having to reconstruct it from diffs.

> **Update (2026-07-19, later same day):** `src/ingestion/reader.py`'s
> Excel path was rewritten to use `openpyxl` instead of the hand-rolled
> XML parser described below — see "Later amendment" at the bottom of this
> document. The description of `reader.py` under `src/` is left as
> originally written for history; it no longer matches the code.

## Files created

### `docs/`

- **`docs/data_schema.md`** — Defines the column-level contract for the
  `transactions` and `clients` tables (names, types, required/optional,
  allowed values). This is the single source of truth that
  `validation_rules.md`, the sample fixtures in `data/sample/`, and the
  code in `src/` all agree on.
- **`docs/validation_rules.md`** — Lists the concrete, testable validation
  rules enforced by `src/ingestion/validator.py` (required fields, valid
  date, valid amount, valid category, unique `transaction_id`), each mapped
  to the sample file that exercises it, plus how failures are handled and
  how deduplication is scoped separately from validation.
- **`docs/Explainer.md`** — This file.

### `data/`

- **`data/raw/clients.csv`** — Sample client reference data (4 fictitious
  clients) matching the `clients` schema in `data_schema.md`.
- **`data/raw/transactions.csv`** — Sample transaction data (8 fictitious
  rows spanning `revenue`, `expense`, and `budget` categories) matching the
  `transactions` schema.
- **`data/raw/transactions.xlsx`** — The same transaction data as
  `transactions.csv`, saved as an actual `.xlsx` file. It was built directly
  from XML parts via Python's `zipfile`/`xml.etree` (no `pandas`/`openpyxl`
  installed in this environment), so `src/ingestion/reader.py`'s Excel path
  has a real file to be tested against. `tests/test_ingestion.py` asserts
  this file and `transactions.csv` read to identical rows.
- **`data/processed/.gitkeep`** — Placeholder keeping the empty
  `processed/` directory (pipeline output destination) in git; its contents
  are gitignored.
- **`data/sample/valid_transactions.csv`** — Rows that pass every
  validation rule; used to assert the "happy path" in tests.
- **`data/sample/duplicate_transactions.csv`** — Contains a repeated
  `transaction_id`, to exercise the duplicate-ID validation rule.
- **`data/sample/missing_values.csv`** — Rows missing required fields
  (`date`, `client_id`, `amount`), to exercise the required-field rule.
- **`data/sample/invalid_data.csv`** — Rows with an unparseable date, a
  non-numeric amount, and an invalid category, to exercise those three
  rules.

### `src/`

- **`src/__init__.py`, `src/models/__init__.py`, `src/ingestion/__init__.py`**
  — Empty package markers so the modules below are importable as
  `src.ingestion.*` / `src.models.*`.
- **`src/models/financial_schema.py`** — `Transaction` and `Client`
  dataclasses plus the `VALID_CATEGORIES` and required-field constants,
  mirroring `docs/data_schema.md` in code.
- **`src/ingestion/reader.py`** — Reads a `.csv` or `.xlsx` file into a
  list of `dict[str, str]` rows keyed by header column. The CSV path uses
  `csv.DictReader`; the XLSX path parses the zip/XML parts directly
  (workbook relationships, shared strings, inline strings, cell
  coordinates) using only the standard library.
- **`src/ingestion/validator.py`** — Implements the rules from
  `docs/validation_rules.md`. Returns `(valid_rows, errors)`, where each
  `ValidationError` carries the row number, the rule that failed, and a
  detail string.
- **`src/ingestion/cleaner.py`** — Normalizes validated rows: trims
  whitespace on all fields and uppercases the currency code.
- **`src/ingestion/deduplicator.py`** — Drops exact-duplicate rows (e.g.
  from re-uploading the same file), independent of the validator's
  duplicate-`transaction_id` check.
- **`src/ingestion/pipeline.py`** — Orchestrates the above in order (Read →
  Validate → Clean → Deduplicate → build `Transaction` objects) and returns
  a `PipelineResult(transactions, errors)`.

### `tests/`

- **`tests/test_ingestion.py`** — Five tests run against
  `run_pipeline()` and `read_rows()`: valid file passes with zero errors,
  missing-values file rejects the expected rows, invalid-data file rejects
  on the three specific rules, duplicate-ID file keeps the first occurrence
  and rejects the second, and the XLSX reader produces output identical to
  the CSV reader for the same data. All five pass.

### Repository root

- **`conftest.py`** — Adds the repository root to `sys.path` so `pytest`
  can resolve `from src...` imports regardless of where it's invoked from;
  there's no `pyproject.toml`/packaging config yet to do this otherwise.

## Files modified

- **`README.md`** — Updated the "Repository Structure" tree to include
  `docs/data_schema.md`, `docs/validation_rules.md`, and the new `data/`,
  `src/`, and `tests/` trees, and added a short paragraph pointing from the
  architecture description to the concrete pipeline implementation. This
  keeps the README in sync with what's actually in the repo, which
  `docs/design_review.md` had flagged as a standing gap.
- **`.gitignore`** — Added `.pytest_cache/` (generated by running the new
  test suite) and ignored `data/processed/*` while keeping `.gitkeep`, since
  processed output is pipeline-generated, not source-controlled data.

## What this does and doesn't do

This scaffolding implements the **Validation** and **Cleaning** stages of
the pipeline described in `docs/architecture.md`, as a standalone, tested
Python module. It does **not** implement KPI calculation, anomaly
detection, AI summarization, Airtable storage, or notifications — those
remain n8n-workflow concerns per the existing architecture decisions
(`docs/decisions.md`) and are out of scope for this change. It also does
not resolve any of the open gaps `docs/design_review.md` raised (approval
gate, audit-log immutability, OpenAI data handling, missing ADRs) — it
only adds the sample data and schema contract that review noted was
missing, and a concrete implementation of the two stages it could evaluate
against real code.

## Later amendment (2026-07-19): reader.py switched to openpyxl

At the user's request, `src/ingestion/reader.py`'s Excel path was rewritten
to use `openpyxl` instead of the hand-rolled zip/XML parser, because
OOXML is a large, evolving format and a minimal parser doesn't handle
real-world edge cases: formulas, merged cells, mixed date formats, hidden
sheets, multiple worksheets. `openpyxl` is the maintained, spec-compliant
library for this.

- **`src/ingestion/reader.py`** — `_read_xlsx` now loads the workbook with
  `openpyxl.load_workbook(path, data_only=True)` (`data_only=True` so a
  formula cell yields its last-cached computed value, since openpyxl has
  no calculation engine of its own). It picks the first worksheet whose
  `sheet_state == "visible"`, skipping hidden helper/calculation sheets.
  Merged cells are handled explicitly: openpyxl only stores a value on a
  merged range's top-left cell, so `_merged_cell_values` maps every
  coordinate in each range back to that anchor value before building rows.
  Cell values are normalized to strings (`_cell_str`) so the XLSX and CSV
  paths keep producing the same `dict[str, str]` shape: dates become
  ISO `YYYY-MM-DD` strings, whole-number floats drop their trailing `.0`.
- **`requirements.txt`** — Added, pinning `openpyxl>=3.1`. This is the
  first real runtime dependency the project has had; there was no
  `requirements.txt`/`pyproject.toml` before.
- **`data/raw/transactions.xlsx`** — Regenerated with `openpyxl` (real
  `date`/numeric cell types) instead of the original hand-built file,
  so the fixture reflects how an actual Excel file stores this data.

### Two pre-existing issues fixed along the way

- **`src/models/financial_schema.py`** had a stray, accidental duplicate
  `class Transaction:` at the end of the file (docstring only, no fields)
  from an earlier manual edit. Because Python keeps the last definition of
  a name, this silently emptied `Transaction` of all its fields and broke
  every test that builds one. The docstring was merged into the real
  class and the duplicate removed; the `amount: Decimal` change from that
  same edit was kept.
- **`src/ingestion/pipeline.py`** still built `Transaction.amount` with
  `float(row["amount"])`, left over from before `amount` became `Decimal`.
  Changed to `Decimal(row["amount"])` (constructed from the original
  string, not via `float`, to avoid introducing binary floating-point
  error into a money field).

### Test changes

`tests/test_ingestion.py`'s XLSX/CSV comparison test was rewritten: it
previously asserted the raw rows read from `transactions.csv` and
`transactions.xlsx` were string-identical, which broke once XLSX numeric
cells stopped round-tripping through exact text (a `125000.00`-looking
value in the CSV becomes a numeric `125000` in Excel — that's correct
Excel behavior, not a bug). It now runs both files through the full
pipeline and compares the resulting `Transaction` objects instead, which
is the actual invariant that matters. Two new tests were added:
`test_xlsx_reader_skips_hidden_sheets` and
`test_xlsx_reader_fills_merged_cell_values`, each building a small
workbook in-memory with `openpyxl` to prove those two edge cases work.
All 7 tests pass.
