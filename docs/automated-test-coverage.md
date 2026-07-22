# Automated Test Coverage Summary

This document summarizes the automated unit and integration tests contained 
in the tests/ directory. Each entry identifies the feature under test and the 
specific behaviour or failure mode verified by the test suite.

---

## tests/test_anomaly_detector.py
Feature: `src.ai.anomaly_detector.generate_anomaly_report` — turns KPIs +
transactions + an LLM client into a validated `AnomalyReport`.

- `test_generate_anomaly_report_returns_full_report` — a well-formed LLM
  JSON payload with two anomalies is parsed into an `AnomalyReport` with
  correctly ordered `FinancialAnomaly` objects and a timestamped
  `generated_at`.
- `test_markdown_code_fences_are_stripped` — an LLM response wrapped in
  \`\`\`json ... \`\`\` fences is still parsed correctly (fences are stripped
  before JSON parsing).
- `test_malformed_json_raises_llm_response_error` — non-JSON LLM output
  raises `LLMResponseError` instead of crashing.
- `test_missing_executive_summary_raises` — payload missing the
  `executive_summary` key is rejected.
- `test_missing_anomalies_raises` — payload missing the `anomalies` key is
  rejected.
- `test_anomaly_missing_required_field_raises` (parametrized over
  severity/title/description/evidence/recommendation) — an anomaly object
  missing any required field is rejected.
- `test_invalid_severity_raises` — an unrecognized severity value (e.g.
  `"extreme"`) is rejected.
- `test_severity_is_normalized_to_lowercase` — a severity given as `"HIGH"`
  is normalized to `"high"` in the resulting report.
- `test_empty_string_fields_are_rejected` (parametrized over
  title/description/evidence/recommendation) — empty-string values in
  required anomaly fields are rejected, not silently accepted.
- `test_build_anomaly_prompt_output_is_sent_to_llm_client` — the prompt
  actually sent to the LLM client contains the expected KPI labels
  ("Total Revenue", "Total Expenses", "Net Profit") and instruction
  boilerplate ("Respond with ONLY valid JSON", "Never invent numbers").
- `test_generated_at_is_timezone_aware` — the report's `generated_at`
  timestamp carries tzinfo/UTC offset rather than being naive.

## tests/test_api.py
Feature: `src.api.main` FastAPI app — the `/health` and `/analyze` HTTP
endpoints, using a `TestClient` and a fake LLM client injected via
dependency override so no network calls occur.

- `test_health_check_returns_ok` — `GET /health` returns `200` with
  `{"status": "ok"}`.
- `test_analyze_returns_anomaly_report_for_valid_csv` — uploading a valid
  CSV returns `200` with the anomaly report JSON (executive summary,
  anomalies list, severities, `generated_at`).
- `test_analyze_rejects_unsupported_file_type` — uploading a `.txt` file
  returns `400` with an `InvalidFileError` naming the rejected extension.
- `test_analyze_reports_unreadable_csv_as_csv_processing_error` — a file
  with invalid (non-UTF-8) bytes returns `400` with `CSVProcessingError`.
- `test_analyze_reports_validation_failure_when_all_rows_invalid` — a CSV
  where every row fails validation returns `422` with
  `ValidationFailedError`.
- `test_analyze_reports_malformed_llm_response_as_anomaly_generation_error`
  — a non-JSON LLM response surfaces as `502` `AnomalyGenerationError`.
- `test_analyze_reports_openai_timeout_as_gateway_timeout` — an
  `OpenAITimeoutError` from the LLM client surfaces as `504`
  `OpenAITimeoutError`.
- `test_analyze_reports_openai_request_error_as_bad_gateway` — an
  `OpenAIRequestError` from the LLM client surfaces as `502`
  `OpenAIServiceError`.
- `test_analyze_reports_unexpected_exception_as_internal_server_error_without_traceback`
  — an unhandled exception from the LLM client is turned into a `500`
  `InternalServerError` whose message does not leak the original exception
  text or a traceback.

## tests/test_ingestion.py
Feature: `src.ingestion.pipeline.run_pipeline` and
`src.ingestion.reader.read_rows` — reading, cleaning and validating
transaction files (CSV and XLSX).

- `test_valid_transactions_pass_with_no_errors` — a fully valid CSV
  produces all 4 transactions with zero errors.
- `test_missing_values_are_rejected` — rows missing required fields are
  rejected with rule `"required_field"`, valid rows still pass.
- `test_invalid_data_is_rejected` — rows with a bad date, bad amount, and
  bad category are all rejected with the matching rule names
  (`invalid_date`, `invalid_amount`, `invalid_category`).
- `test_duplicate_transaction_id_is_rejected_but_first_occurrence_kept` —
  when a transaction ID repeats, the first occurrence is kept and later
  duplicates are rejected with rule `"duplicate_transaction_id"`.
- `test_xlsx_and_csv_sources_produce_equivalent_transactions` — an XLSX
  file and an equivalent CSV file produce identical parsed transactions
  (native Excel types vs. text are reconciled by the pipeline).
- `test_xlsx_reader_skips_hidden_sheets` — `read_rows` ignores hidden
  worksheet tabs and only reads the visible "transactions" sheet.
- `test_currency_is_normalized_to_uppercase` — a lowercase currency code
  in the source file is normalized to uppercase.
- `test_cleaner_trims_whitespace` — leading/trailing whitespace in text
  fields (description, currency) is trimmed during cleaning.
- `test_xlsx_reader_fills_merged_cell_values` — for a merged Excel cell
  range, the value is propagated to every row in the merged range rather
  than left blank on all but the top-left cell.

## tests/test_kpi_engine.py
Feature: `src.analytics.kpi_engine.generate_kpis` — deriving financial KPIs
from a transaction list.

- `test_totals_and_net_profit_exclude_budget` — total revenue, total
  expenses, and net profit are computed correctly and "budget" category
  transactions are excluded from all three.
- `test_revenue_by_client_sums_per_client_descending` — revenue is summed
  per client and returned ordered highest to lowest.
- `test_expenses_by_category_uses_description_as_grouping` — expenses are
  grouped/keyed by their description text.
- `test_monthly_totals_are_net_and_exclude_budget` — monthly totals are
  net (revenue minus expenses) and exclude budget-category transactions.
- `test_largest_transactions_ranked_by_absolute_amount` — the top-N
  largest transactions are ranked by absolute amount, not signed amount.
- `test_empty_input_returns_zeroed_kpis` — an empty transaction list
  produces zeroed/empty KPI values instead of raising.

## tests/test_openai_client.py
Feature: `src.ai.openai_client.OpenAILLMClient` — the OpenAI SDK wrapper,
including retry/backoff and error translation. The underlying `OpenAI`
class and `time.sleep` are mocked/patched throughout, so no real network
or wall-clock delay occurs.

- `test_complete_returns_text_on_success` — a successful chat completion
  call returns the response text and the SDK is called exactly once.
- `test_missing_api_key_raises_configuration_error` — constructing the
  client with an empty API key raises `OpenAIConfigurationError`.
- `test_retries_on_transient_failure_then_succeeds` — a connection error
  followed by a success is retried once and returns the successful result.
- `test_retry_uses_exponential_backoff` — successive retries sleep for
  exponentially increasing delays (1.0s, then 2.0s).
- `test_exhausted_retries_raise_request_error` — persistent rate-limit
  errors across all retry attempts raise `OpenAIRequestError` after
  exhausting the configured retry count.
- `test_exhausted_timeouts_raise_timeout_error` — persistent timeouts
  across all retries raise `OpenAITimeoutError`.
- `test_internal_server_error_is_retried` — a 500-level API error is
  treated as retryable and a subsequent success is returned.
- `test_non_retryable_api_error_raises_immediately` — a 400 bad-request
  error is not retried; it raises `OpenAIRequestError` immediately with no
  sleep and only one SDK call.
- `test_empty_response_content_raises_response_error_without_retry` — a
  completion whose message content is blank/whitespace raises
  `OpenAIResponseError` without retrying.
- `test_response_with_no_choices_raises_response_error` — a completion
  with an empty `choices` list raises `OpenAIResponseError`.
- `test_openai_timeout_error_is_an_openai_client_error` — all specific
  OpenAI exception types (`OpenAITimeoutError`, `OpenAIRequestError`,
  `OpenAIResponseError`, `OpenAIConfigurationError`) are subclasses of the
  common `OpenAIClientError`, so callers can catch one base type.

## tests/test_prompt_builder.py
Feature: `src.ai.prompt_builder.build_anomaly_prompt` — assembling the LLM
prompt text from KPIs and transactions.

- `test_build_anomaly_prompt_returns_a_string` — the builder returns a
  non-empty string.
- `test_executive_summary_context_section_exists` — the prompt includes
  an "## Executive Summary Context" section header.
- `test_key_kpis_section_exists` — the prompt includes a "## Key KPIs"
  section containing Total Revenue, Total Expenses, and Net Profit.
- `test_monthly_totals_section_exists` — the prompt includes a
  "## Monthly Totals" section header.
- `test_expense_breakdown_section_exists` — the prompt includes an
  "## Expense Breakdown" section header.
- `test_largest_transactions_section_exists` — the prompt includes a
  "## Largest Transactions" section header.
- `test_transaction_ledger_section_exists_with_sample_ids` — the prompt
  includes a "## Full Transaction Ledger" section listing every sample
  transaction's ID.
- `test_json_response_schema_is_present` — the prompt documents the
  expected JSON response schema, naming every required field
  (executive_summary, anomalies, severity, title, description, evidence,
  recommendation).
- `test_prompt_contains_key_instructions` — the prompt includes the key
  guardrail instructions: "Respond with ONLY valid JSON", "Never invent
  numbers", and a reference to "supplied data".
- `test_empty_transaction_list_does_not_raise` — building a prompt from
  zero transactions/zeroed KPIs succeeds and renders "(none)" placeholders
  instead of raising.
- `test_transaction_ledger_is_truncated_to_max_ledger_transactions` — when
  transactions exceed `MAX_LEDGER_TRANSACTIONS`, the ledger section is
  truncated to that limit, includes a "(truncated: showing X of Y
  transactions)" note, and only the first N transactions' IDs appear (not
  the ones beyond the cutoff).
- `test_currency_values_are_formatted_and_key_kpi_numbers_appear` — dollar
  KPI values are formatted with `$` and thousands separators (e.g.
  `$231,200.50`) and match the actual computed KPI numbers.
