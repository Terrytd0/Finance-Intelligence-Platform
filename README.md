# Finance Intelligence Platform

## Executive Summary

**Client:** Horizon Capital Partners

The Finance Intelligence Platform is an AI-assisted system that automates the
ingestion, validation, analysis, and reporting of financial data. It is being
built for Horizon Capital Partners to cut daily analyst workload from hours to
minutes while preserving the accuracy and auditability required in a finance
context.

## Business Problem

Analysts currently spend 2–3 hours a day on manual, repetitive work:

- Cleaning and reconciling spreadsheets
- Calculating KPIs by hand
- Identifying anomalies in the numbers
- Writing executive summaries
- Distributing reports to stakeholders

Horizon Capital Partners wants this workload reduced to under 15 minutes per
day without sacrificing accuracy or the ability to audit how a number or
conclusion was produced.

## Success Criteria

The platform is considered successful when it delivers, end-to-end:

- **Upload-triggered ingestion** A user uploads a CSV/Excel file, which automatically starts the processing pipeline.
- **Validation** that catches data quality issues before they reach reports
- **KPI calculation** consistent with current analyst methodology
- **Anomaly detection** that surfaces issues analysts would otherwise catch manually
- **Executive reporting** that is clear and decision-ready
- **Notifications** so stakeholders are alerted without manual distribution
- **Audit logging** so every figure and conclusion can be traced back to its source
- **Scalable architecture** that holds up as data volume and client count grow

## Proposed Solution

An automated pipeline that mirrors the analyst workflow it replaces, so
behavior stays explainable and easy to validate against current practice:

1. **Ingestion** — pull in raw financial data from source systems/spreadsheets
2. **Validation** — check data quality and flag issues before they propagate
3. **KPI Calculation** — compute the same metrics analysts calculate today
4. **Anomaly Detection** — flag values outside predefined business thresholds.
5. **Executive Reporting** — generate summaries suited for decision-makers
6. **Notifications** — distribute reports/alerts to reviewers automatically who then send to stakeholders once approved.
7. **Audit Logging** — record how each figure and conclusion was derived, for traceability

Each stage is designed to be independently reviewable, so a human can verify
or override any step without re-deriving the whole pipeline.

## High-Level Architecture

_Detailed component and data-flow design is tracked in
[`docs/architecture.md`](docs/architecture.md); architectural decisions and
their trade-offs are recorded in [`docs/decisions.md`](docs/decisions.md) as
they're made._

At a high level, the system follows the pipeline above: data flows from
ingestion through validation, KPI calculation, and anomaly detection, into
reporting and notification, with audit logging running alongside every stage
to keep the process traceable end to end.

## Technology Stack

_To be finalized and recorded in [`docs/decisions.md`](docs/decisions.md) as
architecture decisions are made. Stack choices should be evaluated against
the reliability, explainability, and scalability needs above before being
locked in._

## Supported Financial Data

Version 1 of the platform processes:

- Revenue reports
- Expense reports
- Budget vs Actual reports
- Monthly P&L statements
- Cash flow summaries
- Financial KPI exports

## Key Features

- Automated spreadsheet ingestion (`src/ingestion/`)
- Intelligent validation (`src/ingestion/validator.py`)
- Financial KPI engine (`src/analytics/kpi_engine.py`)
- AI anomaly detection (`src/ai/anomaly_detector.py`)
- Executive summary generation (`src/ai/prompt_builder.py` +
  `anomaly_detector.py`)
- Audit trail
- Email & Slack notifications
- Scalable workflow architecture

## Future Enhancements

- Interactive dashboard
- Scheduled report generation
- Multi-company support
- Predictive forecasting
- Role-based access
- Approval workflows
- ERP integrations (SAP, Oracle, Dynamics)

## Repository Structure

```
Finance-Intelligence-Platform/
│
├── README.md
├── CLAUDE.md
├── LICENSE
├── .gitignore
├── requirements.txt
├── conftest.py
│
├── docs/
│   ├── architecture.md
│   ├── assumptions_and_open_questions.md
│   ├── business_requirements.md
│   ├── decisions.md
│   ├── design_review.md
│   ├── data_schema.md
│   ├── Explainer.md
│   ├── validation_rules.md
│   └── screenshots/
│
├── data/
│   ├── raw/
│   │   ├── transactions.csv
│   │   ├── transactions.xlsx
│   │   └── clients.csv
│   │
│   ├── processed/
│   │
│   └── sample/
│       ├── valid_transactions.csv
│       ├── duplicate_transactions.csv
│       ├── missing_values.csv
│       ├── invalid_data.csv
│       ├── lowercase_currency.csv
│       └── whitespace_values.csv
│
├── src/
│   ├── __init__.py
│   ├── ingestion/
│   │   ├──  __init__.py
│   │   ├── reader.py
│   │   ├── validator.py
│   │   ├── cleaner.py
│   │   ├── deduplicator.py
│   │   └── pipeline.py
│   │
│   ├── analytics/
│   │   ├── __init__.py
│   │   └── kpi_engine.py
│   │
│   ├── ai/
│   │   ├── prompt_builder.py
│   │   └── anomaly_detector.py
│   │
│   └── models/
│       ├──  __init__.py
│       └── financial_schema.py
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_kpi_engine.py
│   ├── test_prompt_builder.py
│   └── test_anomaly_detector.py
│
├── workflows/
│
├── assets/
│
└── examples/
```

The `src/ingestion` pipeline (Read → Validate → Clean → Deduplicate) is a
concrete, testable implementation of the Validation and Cleaning stages
described above, and the sample data under `data/sample/` doubles as its
test fixtures — see [`docs/data_schema.md`](docs/data_schema.md) and
[`docs/validation_rules.md`](docs/validation_rules.md) for the contract it
implements. Excel files are read with `openpyxl` (see `requirements.txt`),
so it handles real-world `.xlsx` edge cases — formulas, merged cells,
hidden sheets — rather than a hand-rolled parser.

## Analytics & AI Reporting Layer

Once transactions are ingested and cleaned, two further stages compute the
KPI Calculation and AI-assisted Anomaly Detection / Executive Reporting
steps from the pipeline above:

- **`src/analytics/kpi_engine.py`** — deterministic, non-AI KPI
  calculations (`generate_kpis`). Computes total revenue, total expenses,
  net profit, revenue by client, expenses by category, monthly totals, and
  the largest transactions from a batch of validated `Transaction` records.
  Every figure here is reproducible from the transaction data alone, which
  keeps the numbers the AI layer reasons over auditable.
- **`src/ai/prompt_builder.py`** — formats a `FinancialKPIs` snapshot and
  the underlying transactions into a structured prompt
  (`build_anomaly_prompt`). It performs no calculations of its own; it only
  renders figures already computed by the KPI engine, and instructs the
  model to reason solely from the supplied data rather than inventing or
  recomputing numbers.
- **`src/ai/anomaly_detector.py`** — sends that prompt to an injected
  `LLMClient` (a small `Protocol`, so the module has no dependency on any
  specific provider), then parses and validates the JSON response into
  typed `FinancialAnomaly` / `AnomalyReport` dataclasses. Malformed or
  schema-invalid responses raise `LLMResponseError` rather than being
  silently accepted, so downstream reporting can trust the shape of an
  `AnomalyReport`.

This split — deterministic math in `analytics/`, everything AI-facing in
`ai/` — keeps KPI figures explainable and independently testable, while
containing prompt/response handling (and the risk of model
hallucination) to a single, narrow boundary.

