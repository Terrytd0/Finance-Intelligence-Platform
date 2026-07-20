# Explainer

**Date:** 2026-07-19 (last updated 2026-07-20)

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

## Update (2026-07-20): Analytics layer (KPI engine) and AI layer added

This adds the two stages that sit after Cleaning/Deduplication in
`docs/architecture.md`: the deterministic **KPI Engine** and a
provider-agnostic **AI** layer that reasons over its output. This
supersedes the "What this does and doesn't do" note above, which said
KPI calculation, anomaly detection, and AI summarization were out of
scope — that gap is now filled by the modules below, implemented as
plain Python rather than as n8n workflow nodes (n8n orchestration per
`docs/decisions.md` ADR-001 remains a later integration step, not
replaced by this).

The project's separation of responsibilities is now:

- **`src/analytics/`** — all financial calculation. Deterministic, fully
  testable, no AI.
- **`src/ai/`** — never calculates or changes a KPI value; only formats
  already-computed data into a prompt and turns an LLM's response into
  typed objects. Depends on `src/analytics/` and `src/models/`, never the
  other way around.

### `src/analytics/`

- **`src/analytics/__init__.py`** — Empty package marker, same pattern as
  `src/ingestion/__init__.py`.
- **`src/analytics/kpi_engine.py`** — One public function,
  `generate_kpis(transactions: list[Transaction], *, top_n: int = 5) ->
  FinancialKPIs`, plus the `FinancialKPIs` dataclass
  (`total_revenue`, `total_expenses`, `net_profit`, `revenue_by_client`,
  `expenses_by_category`, `monthly_totals`, `largest_transactions`).
  Notable decisions, since they aren't obvious from the schema alone:
  - `budget`-category rows are planned figures, not actual money
    movement, so they're excluded from every total except
    `largest_transactions` (a large planned line is still worth
    surfacing).
  - `total_expenses` is reported as a positive number even though
    `Transaction.amount` is stored negative for expenses
    (`docs/data_schema.md`) — that matches how a business reads an
    expense report.
  - `expenses_by_category` groups by `description` (e.g. "Office
    lease", "Software licensing"), not `category` — the schema has no
    dedicated expense-category column, so `description` is the closest
    existing field. Worth revisiting if a real category column is added.
  - `monthly_totals` is net (revenue − expenses) per `YYYY-MM`, budget
    excluded, chronologically sorted.

### `src/ai/`

- **`src/ai/prompt_builder.py`** — One public function,
  `build_anomaly_prompt(kpis: FinancialKPIs, transactions:
  list[Transaction]) -> str`. Formats a `FinancialKPIs` snapshot and the
  underlying transactions into a structured text prompt (Executive
  Summary Context, Key KPIs, Revenue by Client, Expense Breakdown,
  Monthly Totals, Largest Transactions, a Full Transaction Ledger capped
  at `MAX_LEDGER_TRANSACTIONS = 200` rows so a large batch can't blow up
  prompt size, Instructions, and a Response Format section). It performs
  no calculation — every figure is read directly from the objects passed
  in. The Instructions section asks the model to identify unusual
  spending, unusual revenue patterns, concentration risk, unusually
  large transactions, and other financial risks, and to provide
  recommendations, while explicitly telling it to never invent numbers
  and only reason from the supplied data. The Response Format section
  specifies the exact JSON schema `anomaly_detector.py` expects back, so
  the two files stay in sync without either one hardcoding the other's
  internals.
- **`src/ai/anomaly_detector.py`** — One public function,
  `generate_anomaly_report(kpis: FinancialKPIs, transactions:
  list[Transaction], llm_client: LLMClient) -> AnomalyReport`. It calls
  `build_anomaly_prompt()`, sends the result to the injected
  `llm_client`, and parses/validates the JSON response into
  `FinancialAnomaly` (`severity`, `title`, `description`, `evidence`,
  `recommendation`) and `AnomalyReport` (`executive_summary`,
  `anomalies`, `generated_at`) dataclasses. Design points:
  - `LLMClient` is a `typing.Protocol` with a single `complete(prompt:
    str) -> str` method — no OpenAI or Anthropic SDK import anywhere in
    the module, and no API keys or environment variables read. Any
    provider-specific client can be adapted to this shape later.
  - A malformed or schema-violating response raises `LLMResponseError`
    (defined in this module) rather than silently returning a partial
    report.
  - Response parsing tolerates a stray ` ``` ` markdown code fence some
    models add despite being told not to, before running `json.loads`.
  - `severity` is validated against `{"low", "medium", "high",
    "critical"}` and normalized to lowercase; every other field must be
    a non-empty string.
  - `generated_at` is stamped by this module
    (`datetime.now(timezone.utc)`), not trusted from the LLM response.
  - `src/ai/` intentionally has no `__init__.py` — Python's namespace
    packages make `from src.ai.prompt_builder import ...` work without
    one, and only these two files were requested.

### `tests/`

- **`tests/test_kpi_engine.py`** (6 tests) — Totals and net profit
  correctly exclude `budget` rows; revenue-by-client and
  expenses-by-category grouping/sums; monthly net totals; largest
  transactions ranked by absolute amount; empty input returns zeroed
  KPIs rather than raising.
- **`tests/test_anomaly_detector.py`** (18 tests) — Uses a fake
  `RecordingLLMClient` (implements the `LLMClient` protocol in-memory)
  so no test makes a network call or imports an LLM SDK. Covers: a full
  successful report (executive summary, `generated_at`, anomaly count,
  every `FinancialAnomaly` field); markdown-code-fence stripping;
  malformed JSON; a missing `executive_summary`; a missing `anomalies`
  list; each individually-missing required anomaly field; an invalid
  severity value; severity case-normalization; empty-string fields
  being rejected; that the real (unmocked) `build_anomaly_prompt()`
  output is what actually reaches the LLM client; and that
  `generated_at` is timezone-aware.
- **`tests/test_prompt_builder.py`** (12 tests) — Checks the prompt is a
  non-empty string; each required section heading is present (Executive
  Summary Context, Key KPIs, Monthly Totals, Expense Breakdown, Largest
  Transactions, Full Transaction Ledger with sample transaction IDs
  present); the JSON response schema fields are named in the Response
  Format section; the "respond with only JSON" / "never invent numbers"
  / "supplied data" instructions are present; an empty transaction list
  doesn't raise; the transaction ledger truncates at exactly
  `MAX_LEDGER_TRANSACTIONS` (verified against a synthetic batch of
  `MAX_LEDGER_TRANSACTIONS + 10` transactions, scoped to just the ledger
  section so it isn't confused by the separate Largest Transactions
  section); and that currency values are formatted with the expected
  `$`/comma/two-decimal shape. Assertions check behavior (headings,
  labels, counts) rather than pinning the full prompt text, so
  copy-only changes to `prompt_builder.py` won't break them.

All 45 tests in the suite pass (`python -m pytest -q`): 9 from
`test_ingestion.py`, 6 from `test_kpi_engine.py`, 18 from
`test_anomaly_detector.py`, and 12 from `test_prompt_builder.py`.

### What this still doesn't do

No file in `src/ai/` calls a real LLM — `LLMClient` is a structural
protocol with no concrete implementation yet. Wiring an actual OpenAI or
Anthropic client, an n8n node to invoke `generate_anomaly_report()`,
Airtable storage, and notifications are all still open, per
`docs/architecture.md` and `docs/decisions.md`.
