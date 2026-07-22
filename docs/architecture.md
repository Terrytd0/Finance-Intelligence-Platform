# Architecture

## Overview

The Finance Intelligence Platform automates the financial reporting
workflow at Horizon Capital Partners: it ingests spreadsheet data,
validates and cleans it, calculates key financial metrics, uses AI to
generate executive insights and flag anomalies, then stores the results
and distributes reports while maintaining an audit trail.

This document describes the pipeline end to end and states plainly which
parts are implemented in code today versus which remain design proposals.
For the concrete module-by-module mapping of "implemented," see the
[README's Key Features](../README.md#key-features),
[Analytics & AI Reporting Layer](../README.md#analytics--ai-reporting-layer),
and [Production API Layer](../README.md#production-api-layer) sections;
for the reasoning behind each technology choice, see
[`decisions.md`](decisions.md).

## Pipeline Stages

```
CSV / Excel upload
        │
        ▼
Validation & Cleaning              src/ingestion/
  - verify required columns          reader.py, validator.py,
  - check data types                 cleaner.py, deduplicator.py,
  - detect missing values            pipeline.py
  - reject malformed files
  - normalize dates & currencies
  - trim whitespace, drop duplicates
        │
        ▼
KPI Engine                         src/analytics/kpi_engine.py
  - total revenue / expenses / net profit
  - revenue by client
  - expenses by category
  - monthly totals
  - largest transactions
  (deterministic — no AI, fully reproducible from the transaction data)
        │
        ▼
AI Analysis                        src/ai/prompt_builder.py
  - explain KPI changes               src/ai/anomaly_detector.py
  - flag anomalies                    src/ai/openai_client.py
  - generate executive summary
  (LLM-based — reasons only over KPIs already computed above; never
  recomputes or invents figures)
        │
        ▼
Production API                     src/api/main.py (FastAPI)
  - POST /analyze runs the full chain above and returns AnomalyReport JSON
  - GET /health liveness check
        │
        ▼
Workflow Orchestration (n8n)       n8n/Finance-Intelligence-Pipeline.json
  - Webhook → HTTP Request calls FastAPI /analyze
  - Switch routes on anomaly severity (low/medium/high/critical)
        │
        ▼
  ┌─────────────┴─────────────┐
  ▼                           ▼
Data Storage (Airtable)   Notifications (Slack / Email)
  - Archive Report            per-severity alerts
  - Update Audit Trail
```

**What this diagram intentionally does not show:** a human approval gate
before distribution, role-based access control, and batch processing —
none of these exist yet. See
[Design & Operations Documentation](../README.md#design--operations-documentation)
in the README for the design docs covering each gap.

## Component Status

| Stage | Status | Implementation |
| --- | --- | --- |
| Ingestion (CSV) | Implemented | `src/ingestion/reader.py` (`csv.DictReader`) |
| Ingestion (Excel) | Implemented in code, not yet exposed via API | `src/ingestion/reader.py` (`openpyxl`); `/analyze` currently accepts `.csv` only |
| Validation | Implemented | `src/ingestion/validator.py` — required fields, date/amount/category format, duplicate transaction ID |
| Cleaning | Implemented | `src/ingestion/cleaner.py` — whitespace trim, currency uppercasing |
| Deduplication | Implemented | `src/ingestion/deduplicator.py` |
| KPI calculation | Implemented | `src/analytics/kpi_engine.py`, deterministic and unit-tested |
| Anomaly detection | Implemented, LLM-based | `src/ai/anomaly_detector.py` — no separate deterministic/statistical anomaly rule exists (see *Anomaly Detection Approach* below) |
| Executive summary generation | Implemented | `src/ai/prompt_builder.py` + `src/ai/anomaly_detector.py` |
| HTTP API | Implemented | `src/api/main.py` (`GET /health`, `POST /analyze`) |
| Structured error handling | Implemented | `src/api/errors.py` — no raw tracebacks returned to callers |
| Retries / backoff (OpenAI calls) | Implemented | `src/ai/openai_client.py` — exponential backoff on transient failures |
| Logging | Implemented | `src/logging_config.py` — console + rotating file (`logs/app.log`) |
| Workflow orchestration | Implemented | `n8n/Finance-Intelligence-Pipeline.json` |
| Data storage (Airtable archive + audit trail) | Implemented (n8n) | Per-severity Airtable nodes in the n8n workflow |
| Notifications (Slack / Email) | Implemented (n8n) | Per-severity Slack/Email nodes in the n8n workflow |
| Approval workflow before distribution | Not implemented | Design only — [`role-based-access-design.md`](role-based-access-design.md#approval-workflow-and-report-status) |
| Role-based access control | Not implemented | Design only — [`role-based-access-design.md`](role-based-access-design.md); `src/api/` has no authentication today |
| Batch processing (multi-file uploads) | Not implemented | Design only — [`batch-processing.md`](batch-processing.md); one file per request today |
| Enterprise-scale throughput (10k+ records/day) | Not implemented / not load-tested | Design only — [`scalability-10k-records-per-day.md`](scalability-10k-records-per-day.md) |
| Centralized monitoring / observability | Partially implemented | Rotating file + console logs exist; no centralized dashboard — [`monitoring-metrics.md`](monitoring-metrics.md) |

## Technology Mapping

| Component | Technology | Why |
| --- | --- | --- |
| Backend API | FastAPI | Typed, fast to develop, built-in OpenAPI docs for the `/analyze` contract |
| Workflow orchestration | n8n | Visual workflows, built-in retries, self-hostable ([ADR-001](decisions.md)) |
| AI analysis | OpenAI (`gpt-4o-mini` by default) | Natural-language summaries and anomaly explanations from structured KPI data |
| Data storage | Airtable | Simple relational storage for the MVP; not intended as the long-term store at scale |
| Notifications | Slack / Email (Gmail) | Stakeholder communication, routed by anomaly severity |
| Source data | CSV (implemented), Excel (`.xlsx`, implemented in the ingestion library, not yet exposed via the API) | Universal spreadsheet compatibility |

## Anomaly Detection Approach

Anomaly detection in this platform is entirely LLM-based: `src/ai/anomaly_detector.py`
sends the KPI snapshot and full transaction ledger to OpenAI and asks it to
identify unusual spending, unusual revenue, concentration risk, and other
financial risks, returning a schema-validated `AnomalyReport`. There is
**no separate deterministic/statistical anomaly rule** (e.g. a
threshold or rolling-average check) sitting in front of it today.

This is a known trade-off, not an oversight — see
[`design_review.md`](design_review.md#3-technology-choices), which
recommends splitting anomaly detection into a deterministic check (inside
the KPI Engine) feeding an LLM step that only explains what was already
flagged, rather than relying on the LLM to both detect and explain. That
recommendation has not been implemented; the KPI Engine remains
deterministic-math-only (see `src/analytics/kpi_engine.py`), and all
anomaly judgment currently happens inside the AI layer. Revisit this if
false positives/negatives from LLM-based detection become a problem in
practice.

## Data Flow

1. A user uploads a financial CSV to `POST /analyze` (or triggers the n8n
   `Webhook`, which calls the same endpoint).
2. Ingestion reads the file and validation ensures it matches the expected
   schema ([`data_schema.md`](data_schema.md), [`validation_rules.md`](validation_rules.md)).
3. Cleaning and deduplication standardize and prepare the surviving rows.
4. The KPI Engine calculates financial metrics from the validated
   transactions.
5. The AI layer builds a prompt from those KPIs, sends it to OpenAI, and
   parses the response into a structured `AnomalyReport` (executive
   summary + severity-ranked anomalies).
6. The API returns that report as JSON. When run through n8n, the `Switch`
   node routes it by severity to the Airtable archive/audit-trail nodes and
   the Slack/Email notification nodes; a separate failure branch handles
   pipeline errors instead of silently dropping them.
7. Every step logs to `logs/app.log` (API layer) and to the n8n execution
   history (workflow layer).

## Error Handling

- **API layer** (`src/api/errors.py`): every failure mode — unsupported
  file type, unreadable CSV, all rows failing validation, a malformed LLM
  response, an OpenAI timeout/service failure, missing configuration, or
  any unhandled exception — is caught and returned as
  `{"error": "<Type>", "message": "<detail>"}` with an appropriate HTTP
  status code. Unhandled exceptions are logged with their full traceback
  server-side but never expose that traceback or the original exception
  text to the caller.
- **OpenAI calls** (`src/ai/openai_client.py`): transient failures
  (connection errors, timeouts, rate limits, 5xx) are retried with
  exponential backoff; non-retryable errors (bad request, auth failure,
  malformed/empty response) raise immediately since retrying them cannot
  succeed.
- **n8n workflow**: a dedicated failure branch archives and audits
  processing errors (Airtable "Archive Report: Processing Failures" /
  "Update Audit Trail: Fail") rather than dropping them.
- **Notifications are only triggered from the success and failure branches
  that already ran** — there is no separate "silent drop" path in the
  current workflow.

## Security Considerations

Current state, stated plainly rather than aspirationally:

- Financial data sent to OpenAI is not redacted or classified before the
  API call; no data-retention agreement is documented. Treat this as an
  open item for real client data, not a solved problem — see
  [`design_review.md`](design_review.md#5-security).
- `OPENAI_API_KEY` and other configuration are read from environment
  variables (`src/config.py`), never hardcoded — but there is no rotation
  policy or secrets-manager integration yet.
- Audit trail rows live in Airtable (via the n8n workflow), which is
  editable by anyone with base access — this is **not** an immutable log
  store today, regardless of how the process is described elsewhere.
- **There is no authentication or authorization on the FastAPI service.**
  `POST /analyze` and `GET /health` are open endpoints. Role-based access
  control is designed but not implemented — see
  [`role-based-access-design.md`](role-based-access-design.md).
- Reports are distributed via the n8n workflow's Slack/Email nodes
  immediately after processing, with no human approval gate in between.

## Related Documents

- [`decisions.md`](decisions.md) — Architecture Decision Records (currently: ADR-001, n8n as orchestration platform).
- [`data_schema.md`](data_schema.md) / [`validation_rules.md`](validation_rules.md) — the ingestion contract.
- [`role-based-access-design.md`](role-based-access-design.md) — RBAC and approval-workflow design (not implemented).
- [`batch-processing.md`](batch-processing.md) — batch-upload design (not implemented).
- [`scalability-10k-records-per-day.md`](scalability-10k-records-per-day.md) — scaling roadmap (not implemented/not load-tested).
- [`monitoring-metrics.md`](monitoring-metrics.md) — current logging vs. proposed centralized observability.
- [`design_review.md`](design_review.md) — architecture review with open risks and recommendations, including the anomaly-detection trade-off above.
- [`Explainer.md`](Explainer.md) — chronological log of what was built, when, and why.
