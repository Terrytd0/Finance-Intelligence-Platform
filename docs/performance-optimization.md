# Performance Optimization Strategy

## Status

This document describes two distinct things and is careful not to blur them:

1. **Performance-relevant behavior that already exists in the Minimum Viable Product (MVP)** —
   optimizations that are implemented today in `src/` and
   `n8n/Finance-Intelligence-Pipeline.json`, verified against the current
   code rather than assumed from the architecture diagrams.
2. **Recommended optimizations for enterprise-scale deployments** — changes
   that are not implemented, would require new infrastructure or code, and
   are labeled explicitly as **Future Enhancement** throughout.

The MVP has been validated at small, single-upload volumes typical of
manual testing and the fixtures in `data/sample/`. It has **not** been
load-tested, and no claim here should be read as "this system already
performs at enterprise scale." That is the gap this document maps, not a
gap it closes.

---

## Purpose

Performance optimization in this system is not about raw speed for its own
sake. It is about:

- reducing unnecessary computation (not doing expensive work on data that
  is already known to be invalid or irrelevant)
- minimizing AI API costs, since OpenAI usage is billed per token and is
  the most expensive step in the pipeline
- improving reliability, since a system that fails predictably and retries
  correctly is more "performant" in practice than one that is fast but
  fragile
- supporting future scaling, so that growth in upload volume or client
  count doesn't require a architectural rewrite, only additive changes
- maintaining responsiveness as workload increases, so that processing time
  degrades gracefully rather than falling over

---

## Current Performance Optimizations

The following are implemented today and verified directly against the
source referenced in each row.

| Optimization | Where it exists | What it does | Why it helps |
| --- | --- | --- | --- |
| Early, cheap validation before expensive work | `src/ingestion/validator.py` | Rows are checked against required fields, valid dates, valid amounts, valid categories, and duplicate IDs before anything downstream runs. `_validate_row` returns immediately on missing required fields rather than attempting to parse a date/amount that isn't there. | Ingesting, cleaning, computing KPIs, and calling OpenAI are all more expensive than a field-presence check. Rejecting bad rows before those stages avoids doing that work on data that was never going to produce a usable report. |
| Fail fast when a whole upload is unusable | `src/api/main.py` (`_ingest_upload`), via `ValidationFailedError` | If every row in an upload fails validation, the API raises `ValidationFailedError` before `generate_kpis` or any OpenAI call runs. | Guarantees the most expensive step in the request — the LLM call — is never reached for an upload that has nothing valid to analyze. |
| Staged pipeline that narrows its input at each step | `src/ingestion/pipeline.py` (`run_pipeline`) | Rows flow `read → validate → clean → dedupe` in sequence; each stage only operates on the rows that survived the previous one (`clean_rows` and `dedupe_rows` never see rejected rows). | Later, more expensive stages never redo work on data already filtered out earlier, keeping per-request cost proportional to valid data volume, not raw upload size. |
| Bounded prompt size | `src/ai/prompt_builder.py` (`MAX_LEDGER_TRANSACTIONS = 200`) | The full transaction ledger section of the AI prompt is capped at 200 rows regardless of how many transactions were uploaded; the prompt discloses when it has been truncated. | Directly bounds OpenAI token usage (and therefore cost and latency) for large uploads, instead of prompt size — and spend — growing unbounded with file size. |
| Deterministic math kept out of the LLM | `src/analytics/kpi_engine.py` + `src/ai/prompt_builder.py`'s instructions section | KPIs (totals, revenue by client, expense breakdown, monthly totals) are computed in Python and handed to the model as already-final numbers; the prompt explicitly instructs the model not to recalculate or invent figures. | The LLM is only asked to reason and narrate over numbers it's given, not to perform arithmetic it could get wrong — this is a cost and reliability optimization as much as a correctness one, since it keeps the task the model does as small as possible. |
| Retry only what's actually retryable | `src/ai/openai_client.py` (`RETRYABLE_EXCEPTIONS`, `complete`) | Connection errors, timeouts, rate limits, and 5xx responses are retried with exponential backoff (`INITIAL_BACKOFF_SECONDS = 1.0`, `BACKOFF_MULTIPLIER = 2.0`, attempt count from `Settings.openai_retry_count`). Non-retryable `APIError`s (bad request, auth failure) raise immediately without retrying. | Retrying transient failures improves reliability without wasting time retrying failures that cannot succeed — an auth error retried three times with backoff would only add latency for no benefit. |
| Structured, cheap error handling | `src/api/errors.py` | Every failure mode maps to a typed `APIError` subclass with a fixed `status_code`/`error_type`, handled by two registered FastAPI exception handlers. No raw tracebacks are constructed or returned. | Avoids the cost of unhandled-exception stack unwinding reaching the client, and gives callers (including n8n) a stable, parseable shape to branch on instead of parsing free-text error strings. |
| Severity-based workflow branching | `n8n/Finance-Intelligence-Pipeline.json` (`Switch` node, routing on `severity` into `low`/`medium`/`high`/`critical` branches) | Each severity gets its own Airtable archive node and notification path, rather than every report triggering every notification channel. | Avoids sending Slack messages and emails for low-severity findings that don't warrant them, which is both a UX and a cost/throughput optimization on the notification channels themselves. |
| Configurable tunables instead of redeploys | `src/config.py` (`Settings`) | OpenAI model, timeout, temperature, and retry count are all environment-driven with defaults, cached via `@lru_cache`. | Retry/timeout behavior — a direct lever on both cost and latency — can be tuned per environment without a code change or redeploy. |
| Lightweight, low-overhead logging | `src/logging_config.py` | A single rotating file handler (5 MB × 3 backups) plus console output, configured once and idempotently (`_configured` guard). | Avoids the overhead and failure modes of a heavier logging pipeline while still giving operators a bounded, rotating record of what happened — see [Monitoring Performance](#monitoring-performance) below. |

---

## Current Bottlenecks

These are read as **acceptable MVP trade-offs**, consistent with
`docs/design_review.md`'s conclusion that the pipeline shape itself is
sound. None of them are implementation mistakes — they are the natural
result of building a correctness-first MVP before an enterprise-scale one.

- **Single FastAPI instance, synchronous request handling.** `/analyze` in
  `src/api/main.py` is a regular (non-`async def`) endpoint that runs the
  entire pipeline — read, validate, clean, dedupe, KPI calculation, and the
  OpenAI call — inline within one request. FastAPI runs sync endpoints in a
  thread pool, but there is no multi-worker deployment configuration
  (e.g. multiple `uvicorn`/`gunicorn` workers) documented anywhere in the
  repo, so throughput today is bounded by however the service happens to be
  started.
- **The OpenAI call is a hard sequential dependency.** A request cannot
  return until the LLM responds (or every retry attempt is exhausted). The
  exponential backoff in `src/ai/openai_client.py` improves reliability but
  also means a transient failure can add several seconds of wall-clock time
  (1s, 2s, 4s, ... per `Settings.openai_retry_count`) directly onto the
  caller's request — a direct reliability-for-latency trade-off, made
  deliberately.
- **The n8n workflow executes sequentially per upload.** `Webhook → HTTP
  Request → Switch → (Airtable / Slack / Email nodes)` is one linear chain
  per triggered execution. Nothing in `n8n/Finance-Intelligence-Pipeline.json`
  or `n8n/README.md` describes queue mode or worker scaling, so — as
  `docs/design_review.md` §2 already notes — n8n's own scaling story is
  currently undocumented.
- **Airtable as both data store and audit trail.** As `docs/design_review.md`
  §2 and §6 already flag, Airtable enforces per-base row caps and
  request-rate limits. Because the n8n workflow uses it for both report
  archival and audit-trail entries, concurrent uploads share the same rate
  limit budget for two purposes at once.
- **No caching.** Every upload is fully reprocessed regardless of whether
  identical or near-identical data was seen before; there is no memoization
  of KPI results or OpenAI responses.
- **No batching.** One uploaded file produces exactly one OpenAI request;
  there is no mechanism to batch multiple small files into fewer LLM calls.
- **Entire file held in memory.** `src/ingestion/reader.py` reads a file's
  rows into memory as part of `run_pipeline`; this is unproven beyond the
  row counts in `data/sample/` and would need revisiting for very large
  files.
- **No concurrency/backpressure handling.** Nothing in the API or n8n layer
  throttles or queues simultaneous uploads; each is processed independently
  and immediately, which is fine at low volume and a real constraint at
  higher volume (also noted in `docs/design_review.md` §2).

---

## Future Performance Enhancements

Everything below is a **proposal**, not implemented functionality. None of
it changes the shape of the existing pipeline (`Read → Validate → Clean →
Dedupe → KPI Engine → AI → Store → Notify`); each is additive.

- **Asynchronous request handling** — convert `/analyze` to `async def` and
  move blocking I/O (file reads, the OpenAI call) off the request thread,
  or move processing to a background task with a polling/webhook-based
  status endpoint instead of holding the HTTP connection open for the full
  pipeline duration.
- **Horizontal FastAPI scaling** — run multiple `uvicorn` workers behind a
  load balancer so throughput isn't bounded by a single process.
- **Queue-based architecture** — introduce a job queue (e.g. Celery, RQ, or
  n8n's own queue mode) between file upload and pipeline execution, so
  uploads are accepted immediately and processed by a pool of workers
  rather than synchronously in the request path.
- **Worker pools** — dedicated worker processes for the OpenAI call
  specifically, since it is the slowest and most failure-prone stage, so a
  burst of uploads doesn't have to serialize through it one at a time.
- **Batch processing** — group multiple small uploads (or multiple report
  sections) into fewer OpenAI requests where the business logic allows it,
  to reduce per-request overhead and cost.
- **Redis (or equivalent) caching** — cache OpenAI responses keyed by a hash
  of the prompt content, so re-uploading unchanged data doesn't re-spend
  tokens; cache computed KPIs for identical input sets.
- **Database indexing** — contingent on the storage-layer migration off
  Airtable that `docs/design_review.md` §2–3 already recommends (e.g. to
  Postgres); indexing would target the fields used for historical trend
  and anomaly lookups.
- **Parallel execution across independent uploads** — once processing moves
  off a single synchronous request path, independent uploads (different
  clients/files) can run concurrently; there is currently nothing to
  parallelize within a single upload's pipeline, since each stage depends
  on the previous stage's output.

---

## AI Performance Optimization

### Current Implementation

- **Prompt size is bounded**, not unbounded — `MAX_LEDGER_TRANSACTIONS`
  (`src/ai/prompt_builder.py`) caps the transaction ledger at 200 rows and
  states the truncation explicitly in the prompt, so cost doesn't scale
  linearly with arbitrarily large uploads.
- **The model is not asked to do arithmetic.** All KPI figures are computed
  deterministically in `src/analytics/kpi_engine.py` before the prompt is
  built; the prompt instructs the model to treat them as ground truth and
  never recompute them (`_build_context_section` in `prompt_builder.py`).
  This keeps the model's job — narration and pattern-finding, not
  calculation — smaller and cheaper than it would otherwise be.
- **Retries are scoped to genuinely transient failures.** `src/ai/openai_client.py`
  only retries `APIConnectionError`, `APITimeoutError`, `RateLimitError`,
  and `InternalServerError`; a non-retryable `APIError` (e.g. a malformed
  request or auth failure) fails immediately rather than burning through
  the retry budget on an error that retrying cannot fix.
- **Temperature is fixed low by default** (`DEFAULT_OPENAI_TEMPERATURE = 0.2`
  in `src/config.py`), favoring consistent, parseable JSON output over
  creative variation — this reduces (though does not eliminate) malformed
  responses that would otherwise need to be surfaced as `LLMResponseError`.
- **Model, timeout, and retry count are configurable** without a code
  change (`src/config.py`), so cost/latency trade-offs can be tuned per
  environment.

### Future Enhancements

- **Response caching** — avoid paying for a duplicate OpenAI call when the
  same (or functionally identical) data is submitted more than once.
- **Token usage monitoring** — track tokens consumed per request and over
  time, so cost is visible and can be budgeted or alerted on; nothing today
  records token counts anywhere in `src/ai/`.
- **Prompt versioning** — track changes to `build_anomaly_prompt`'s
  structure against output quality over time, so prompt changes are
  reviewable rather than silent.
- **Retry-with-repair on malformed responses** — today, a response that
  fails `_validate_payload` in `src/ai/anomaly_detector.py` raises
  `LLMResponseError` immediately with no retry; a future enhancement could
  attempt one repair round-trip (e.g. re-prompting with the parse error)
  before failing the request.
- **Further minimizing prompt size** — e.g. summarizing the transaction
  ledger instead of truncating it at a fixed row count, so large uploads
  lose the least-relevant rows first rather than simply the last ones past
  row 200.
- **Streaming responses** — stream the model's output as it's generated to
  reduce perceived latency, instead of waiting for the full completion
  before any downstream processing begins.

---

## Monitoring Performance

Some of the raw material for performance monitoring already exists, but it
is not currently aggregated into dashboards or alerting — it is log lines
and per-record status fields, not a queryable metrics store. That gap is
itself worth naming rather than glossing over.

**What exists today:**

- `src/logging_config.py` writes every log line (including each OpenAI
  retry attempt, logged via `logger.warning` in `openai_client.py`) to both
  console and a rotating file (`logs/app.log`), with a consistent
  timestamp/level/module/message format.
- `PipelineResult.errors` (`src/ingestion/pipeline.py`) already carries a
  structured count of per-row validation failures for every upload, which
  is the raw data a validation-failure-rate metric would be built from.
- The n8n workflow's Airtable "Archive Report" and "Update Audit Trail"
  nodes (`n8n/Finance-Intelligence-Pipeline.json`) record a `Processed` /
  `Failed` status per execution, and route failures through a dedicated
  failure branch instead of dropping them — this is the closest thing the
  system has to an audit trail and processing-failure record today, and it
  is where operational metrics would be sourced from until a dedicated
  metrics store exists.

**Recommended metrics to monitor** (not currently collected in aggregate):

- End-to-end processing time per upload (ingestion through AI response).
- Validation failure rate (rejected rows / total rows), sourced from
  `PipelineResult.errors`.
- OpenAI retry count and failure rate per request.
- AI response time, isolated from the rest of the pipeline's latency.
- n8n workflow execution duration, per severity branch.
- Reports processed per day/hour, and their pass/fail split.
- Notification delivery latency and failure rate (Slack/Email nodes).
- Overall success rate: completed and notified vs. failed and routed to the
  failure branch.

Wiring these into an actual metrics/observability stack (e.g. Prometheus,
Grafana, or structured log aggregation) is itself a **Future Enhancement**,
not something the current logging and Airtable status fields provide on
their own.

---

## Summary

The MVP, as built, prioritizes correctness, reliability, and
maintainability over raw throughput — consistent with the Engineering
Principles in `CLAUDE.md` and the "APPROVED WITH RECOMMENDATIONS" verdict in
`docs/design_review.md`. The optimizations already in place (early
validation, bounded prompt size, scoped retries, severity-based branching)
exist to avoid wasted computation and AI spend at the volumes the MVP is
designed for, not to support enterprise scale.

The future enhancements described here — async processing, horizontal
scaling, a queue-based architecture, caching, and a real metrics store —
are a roadmap toward enterprise-scale deployments, not a signal that the
current architecture is wrong. Every enhancement listed is additive to the
existing pipeline shape (`Read → Validate → Clean → Dedupe → KPI Engine →
AI → Store → Notify`); none of them require redesigning it.
