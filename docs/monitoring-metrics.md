# Monitoring Metrics

## Status

This document describes two distinct things and, like
`docs/performance-optimization.md`, `docs/batch-processing.md`, and
`docs/scalability-10k-records-per-day.md`, is careful not to blur them:

1. **The monitoring capabilities currently implemented**, verified
   directly against the code in `src/` and the n8n workflow in
   `n8n/Finance-Intelligence-Pipeline.json`.
2. **A recommended monitoring architecture for enterprise deployments**,
   none of which is implemented. Every recommendation is labeled **Future
   Enhancement**.

The MVP (Minimum Viable Product) currently provides operational visibility
primarily through application logs, structured API error handling, the
Audit Trail, Processing Failures, and n8n's own workflow execution
history — not through centralized observability tooling. There is no
metrics collection system, no dashboard, and no alerting platform anywhere
in this repository (`requirements.txt` includes no metrics, tracing, or
APM library of any kind). That gap is described in detail below, not
glossed over.

---

## Purpose

Monitoring matters in a financial intelligence platform because the
system's output — figures and conclusions executives act on — is only
trustworthy if the organization can tell, at any time, whether the
pipeline that produced it is actually working correctly. Concretely:

- **Operational visibility** — knowing whether uploads are being processed
  at all, not discovering a stalled pipeline only when a stakeholder asks
  why a report never arrived.
- **Detecting failures early** — catching a failing OpenAI integration,
  rejected uploads, or a broken n8n workflow before it accumulates into a
  backlog, rather than after.
- **Ensuring reporting reliability** — the platform's core promise (README:
  cutting analyst workload from hours to minutes without sacrificing
  accuracy) depends on the pipeline being demonstrably reliable, not just
  believed to be.
- **Measuring service performance** — understanding whether the system is
  keeping pace with demand as upload volume grows, which is the
  operational counterpart to the architectural discussion in
  `docs/scalability-10k-records-per-day.md`.
- **Supporting incident investigation** — when something does go wrong,
  having enough recorded detail to reconstruct what happened, which stage
  it happened in, and why.
- **Maintaining auditability** — a stated success criterion in the README
  ("every figure and conclusion can be traced back to its source"), which
  monitoring and audit logging jointly support: monitoring for "is it
  working," audit logging for "how did it produce this specific number."
- **Identifying performance bottlenecks** — the operational evidence that
  would validate or correct the analysis in
  `docs/performance-optimization.md`, which is currently reasoned about
  from the code rather than from observed production behavior.
- **Supporting enterprise SLAs** — a client-facing commitment about
  response time or uptime requires monitoring to prove it's being met;
  none exists to make such a commitment against today.

The focus here is business trust and operational confidence, not tooling
for its own sake — the same distinction `docs/performance-optimization.md`
draws between speed and reliability.

---

## Current Monitoring Capabilities

The following are implemented today and verified directly against the
source referenced in each entry.

- **Application logging** (`src/logging_config.py`) — `configure_logging()`
  attaches both a console handler and a rotating file handler to the root
  logger, sharing one format:
  `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`. It is called
  once, idempotently, from `src/api/main.py` at import time.
- **Rotating log files** (`src/logging_config.py`) — `logs/app.log`,
  capped at 5 MB per file with 3 backups (`MAX_LOG_BYTES`,
  `BACKUP_COUNT`), so log volume is bounded without manual cleanup. Log
  level is configurable via `LOG_LEVEL` (`src/config.py`), defaulting to
  `INFO`.
- **Structured API errors** (`src/api/errors.py`) — every failure mode
  (`InvalidFileError`, `CSVProcessingError`, `ValidationFailedError`,
  `AnomalyGenerationError`, `OpenAIServiceError`, `OpenAITimeoutServiceError`,
  `ConfigurationError`) is a typed `APIError` subclass with a fixed
  `status_code` and `error_type`, logged via `logger.warning` before being
  returned to the caller as `{"error": <type>, "message": <str>}`. A
  second handler catches any unexpected exception, logs it with
  `logger.exception` (full traceback to the log, never to the caller), and
  returns a generic 500. This means every failure — expected or not — is
  both observable in the logs and classifiable by type.
- **Validation error reporting** (`src/ingestion/validator.py`,
  `src/ingestion/pipeline.py`) — `PipelineResult.errors` carries a
  structured `ValidationError` (row number, rule, detail) for every row
  that failed validation, rather than a bare pass/fail count. This is
  already the raw data a validation-failure-rate metric would be built
  from, as noted in `docs/performance-optimization.md`'s Monitoring
  Performance section.
- **Retry logging** (`src/ai/openai_client.py`) — every retried OpenAI
  request attempt logs a warning with the attempt number, total attempts,
  exception type, and backoff delay (`logger.warning` in `complete()`);
  the final failure (if retries are exhausted) logs an error with the
  total attempt count. This gives visibility into how often — and why —
  the AI layer is degrading, without needing a separate metrics system to
  see it.
- **Audit Trail** (`n8n/Finance-Intelligence-Pipeline.json`) — the n8n
  workflow's "Update Audit Trail" Airtable nodes record an entry per
  execution, as already described in `docs/role-based-access-design.md`,
  `docs/performance-optimization.md`, and `docs/batch-processing.md`.
- **Processing Failures** (`n8n/Finance-Intelligence-Pipeline.json`) — the
  workflow includes a dedicated failure branch, separate from the
  per-severity success branches, that archives and audits processing
  errors instead of silently dropping them (also referenced in the same
  three documents above).
- **Airtable status tracking** (`n8n/Finance-Intelligence-Pipeline.json`) —
  the Airtable node schemas define a `Processed` / `Failed` status field
  per record, giving a queryable (if manual) view of outcomes over time
  directly in Airtable.
- **Workflow execution history** (n8n) — every webhook-triggered run of
  the workflow is retained in n8n's own execution history by default,
  giving a per-execution view of which nodes ran, which branch was taken,
  and whether the run succeeded — this is n8n's built-in behavior, not
  something this repository configures beyond defining the workflow
  itself.
- **FastAPI health endpoint** (`src/api/main.py`) — `GET /health` returns
  `{"status": "ok"}`, a basic liveness check confirming the process is up
  and responding. It performs no dependency checks (e.g. it does not
  verify OpenAI reachability or configuration validity).

Together, these give an operator the ability to answer "did this specific
upload succeed, and if not, why" — but not "how is the system doing right
now, in aggregate" without manually reading logs or Airtable records.
That distinction is the basis for the gaps below.

---

## Current Monitoring Gaps

These are the same class of gap already acknowledged in
`docs/performance-optimization.md`'s Monitoring Performance section and
`docs/scalability-10k-records-per-day.md`'s Monitoring Scalability
section — **reasonable MVP decisions**, not oversights. Building
centralized observability tooling before the core pipeline had been
validated would have been solving a problem the project didn't have
evidence of yet.

- **No centralized dashboard.** There is nowhere to look at the system's
  current health at a glance; understanding status means reading
  `logs/app.log`, querying Airtable directly, or opening n8n's execution
  history.
- **No metrics aggregation.** Log lines and Airtable status fields are
  per-event records, not aggregated counters, rates, or histograms — there
  is no answer today to "what's the validation failure rate this week"
  without manually processing raw logs.
- **No alerting platform.** Nothing notifies an operator proactively when
  something goes wrong at the system level. The n8n workflow notifies
  *stakeholders* about report severity (per
  `docs/role-based-access-design.md`'s Alert Routing table), which is a
  business notification, not an operational alert about the platform's own
  health.
- **No infrastructure monitoring.** There is no visibility into CPU,
  memory, or disk usage of the FastAPI process or its host — unsurprising,
  since (per `docs/scalability-10k-records-per-day.md`) there is no
  deployment configuration for that host in the first place.
- **No latency dashboards.** Request and AI response times are implicitly
  present in log timestamps but are never extracted, aggregated, or
  visualized.
- **No request throughput monitoring.** There is no running count of
  requests per minute/hour/day; volume can only be reconstructed after the
  fact by counting log lines or Airtable records.
- **No resource utilization metrics.** No CPU, memory, or connection-pool
  utilization is tracked for the FastAPI process itself.
- **No distributed tracing.** A single request's path through validation,
  KPI calculation, the OpenAI call, and the n8n workflow it triggers is
  reconstructable only by manually correlating log timestamps and Airtable
  records — there is no trace ID connecting them.
- **No uptime monitoring.** `GET /health` exists, but nothing polls it on
  a schedule or records historical uptime; nothing would notice
  automatically if the service went down.
- **No SLA reporting.** With no aggregated metrics, there is no
  operational basis to report against a response-time or availability
  commitment, even an internal one.

---

## Operational Metrics

The following metrics would become important as the platform grows past
manual-log-reading scale. None are currently collected in aggregate; each
is grouped by what it measures and why it matters.

**Application Metrics**

| Metric | Why it matters |
| --- | --- |
| Requests per minute | Basic load visibility — the prerequisite for noticing an unusual spike or drop. |
| Average response time | Directly reflects the user-facing experience of `/analyze`, which currently blocks for the full pipeline duration (`docs/performance-optimization.md`'s "Current Bottlenecks"). |
| Request success rate | The single clearest "is the system healthy" signal, distinguishing normal operation from a degrading integration or bad deploy. |
| Request failures (by `error_type`) | `src/api/errors.py` already classifies every failure by type; aggregating that classification shows *which* failure mode is actually occurring at volume, not just that failures are occurring. |
| Validation failures | Sourced from `PipelineResult.errors` — a rising validation failure rate often signals an upstream data-quality problem (a source system change, a malformed export) rather than a platform bug. |

**Pipeline Metrics**

| Metric | Why it matters |
| --- | --- |
| Files processed | The basic unit of platform throughput. |
| Processing duration (per stage) | Distinguishes where time is actually spent — ingestion, KPI calculation, or the AI call — rather than treating the pipeline as one opaque block. |
| Duplicate records removed | Sourced from `src/ingestion/deduplicator.py`'s behavior; an unusually high duplicate rate can indicate a client re-uploading the same file repeatedly, worth surfacing operationally. |
| AI analysis duration | Isolates the slowest, most externally-dependent stage of the pipeline (`docs/performance-optimization.md`). |
| Pipeline completion rate | The share of uploads that make it end-to-end to a delivered report, versus those that fail at some stage. |

**Business Metrics**

| Metric | Why it matters |
| --- | --- |
| Reports generated | The platform's core unit of business value delivered. |
| Anomaly severity distribution | Whether the system is mostly surfacing low-severity noise or genuinely actionable high/critical findings — relevant to tuning the AI layer's usefulness, not just its uptime. |
| Client uploads (by client) | Supports capacity planning and highlights uneven usage across clients, relevant to the multi-company ambitions noted in the README. |
| Processing turnaround time | The end-to-end, business-facing version of the README's "hours to minutes" goal — the metric that would actually prove that goal is being met. |

---

## AI Monitoring

Cross-references `docs/performance-optimization.md`'s AI Performance
Optimization section throughout, since AI monitoring is the operational
counterpart to the optimizations already documented there.

- **OpenAI latency** — currently implicit in log timestamps around the
  `complete()` call in `src/ai/openai_client.py`, but never extracted or
  aggregated. This is the same latency `docs/performance-optimization.md`
  identifies as "the OpenAI call is a hard sequential dependency."
- **Token usage** — not recorded anywhere today; `src/ai/openai_client.py`
  never inspects or logs the response's token usage. Already named as a
  Future Enhancement ("Token usage monitoring") in
  `docs/performance-optimization.md`.
- **Retry count** — partially observable today: each retry attempt is
  individually logged (`logger.warning` in `openai_client.py`), but retry
  counts are not aggregated into a rate or trend — an operator would need
  to grep logs to know whether retries are rare or constant.
- **API failures** — classified by type via `OpenAIServiceError` /
  `OpenAITimeoutServiceError` (`src/api/errors.py`), but again not
  aggregated into a failure-rate metric.
- **Rate limiting** — `RETRYABLE_EXCEPTIONS` in `src/ai/openai_client.py`
  already includes `RateLimitError` and retries it with backoff; there is
  no metric today showing how often rate limiting is actually being hit,
  which would be the leading indicator that AI request volume is
  approaching account limits (relevant to
  `docs/scalability-10k-records-per-day.md`'s "Rate-limit handling"
  discussion).
- **Cost monitoring** — not implemented; no component in `src/ai/` tracks
  or reports spend. Directly related to the "Cost optimization" Future
  Enhancement already named in `docs/performance-optimization.md`.
- **Response quality review** — there is no sampling or human review
  process for AI-generated executive summaries and anomaly findings;
  `docs/design_review.md` §1 already flags the related, larger gap of no
  human sign-off before distribution.
- **Model utilization** — `src/config.py` makes the model configurable
  (`DEFAULT_OPENAI_MODEL = "gpt-4o-mini"`), but nothing tracks which
  model was actually used per request over time, relevant if model choice
  is ever varied by environment or cost tier.

---

## Infrastructure Monitoring

**Every item in this section is a Future Enhancement.** As
`docs/scalability-10k-records-per-day.md` already notes, there is no
deployment or infrastructure configuration in this repository today (no
`Dockerfile`, no container orchestration, no cloud infrastructure
definitions), so there is no infrastructure layer to monitor yet, only the
application layer described above.

- **CPU utilization** *(Future Enhancement)* — of the FastAPI process
  (and, per `docs/batch-processing.md`, any future worker processes).
- **Memory utilization** *(Future Enhancement)* — particularly relevant
  given `src/ingestion/reader.py` currently loads entire files into
  memory (`docs/scalability-10k-records-per-day.md`'s "in-memory
  processing" constraint).
- **Disk usage** *(Future Enhancement)* — for the rotating log directory
  and any future raw-file staging area (`docs/design_review.md` §2's
  missing raw-file archive gap).
- **Network activity** *(Future Enhancement)* — particularly outbound
  traffic to OpenAI and Airtable, the two external dependencies on the
  request path.
- **Worker utilization** *(Future Enhancement)* — contingent on the worker
  pool architecture proposed in `docs/batch-processing.md` and
  `docs/scalability-10k-records-per-day.md`; no worker pool exists today.
- **Queue depth** *(Future Enhancement)* — contingent on the queue-based
  architecture proposed in the same two documents; no queue exists today.
- **Database performance** *(Future Enhancement)* — contingent on the
  database migration off Airtable recommended in `docs/design_review.md`
  §2–3 and `docs/scalability-10k-records-per-day.md`'s Data Scalability
  section.
- **API availability** *(Future Enhancement)* — uptime tracked over time
  against `GET /health`, rather than the endpoint existing but nothing
  polling or recording its results.

---

## Alerting Strategy

No alerting exists today — every item below describes a proposed
operational purpose an alert would serve, not a specific product or an
implemented capability.

- **Repeated API failures** — alerting when the request failure rate
  (classified via `src/api/errors.py`'s `error_type`) crosses a threshold,
  so a degrading integration is caught before it accumulates into a large
  backlog of failed uploads.
- **High AI latency** — alerting when OpenAI response time trends upward,
  since it is already the slowest step in the pipeline and the one most
  exposed to third-party degradation.
- **Failed workflow executions** — alerting on n8n workflow failures,
  extending the existing Processing Failures branch
  (`n8n/Finance-Intelligence-Pipeline.json`) from "recorded" to "actively
  surfaced" to an operator.
- **Excessive retry counts** — alerting when OpenAI retries
  (`src/ai/openai_client.py`) become frequent rather than occasional,
  which is a leading indicator of a developing problem (rate limiting,
  provider instability) before it becomes outright failures.
- **Failed uploads** — alerting on a sustained rise in validation failure
  rate (`PipelineResult.errors`), which more often indicates an upstream
  data-quality regression than a platform defect, and is worth routing to
  a different owner than a platform failure would be.
- **Infrastructure failures** — once infrastructure exists to monitor (see
  Infrastructure Monitoring above), alerting on host- or container-level
  failures.
- **Queue backlog** — once a queue exists (`docs/batch-processing.md`),
  alerting when queue depth grows faster than workers can drain it.
- **Database connectivity issues** — once a database exists (per the
  Airtable-migration recommendation), alerting on connection failures or
  elevated query latency.

The operational purpose in every case is the same: catch degradation while
it is still an early signal, not after it has become a stakeholder-visible
failure to deliver a report.

---

## Monitoring Architecture

**This section describes a proposed architecture. None of it is
implemented.** It is designed to complement the existing Audit Trail and
Processing Failures mechanism, not replace it — the Audit Trail answers
"what happened to this specific report," while the architecture below
would answer "how is the system doing overall."

- **Centralized log aggregation** *(Future Enhancement)* — collecting the
  existing rotating file logs (`src/logging_config.py`) from every
  instance into one searchable location, rather than reading `logs/app.log`
  on whichever host happens to be running the process.
- **Metrics collection** *(Future Enhancement)* — extracting the
  Operational Metrics described above from logs and application code into
  a queryable time-series store, rather than leaving them implicit in log
  text.
- **Dashboards** *(Future Enhancement)* — visualizing collected metrics for
  at-a-glance system health, replacing "read the logs" with "look at a
  chart."
- **Alert manager** *(Future Enhancement)* — the component that would
  evaluate metrics against the thresholds described in Alerting Strategy
  above and notify an operator, distinct from the existing stakeholder
  notification logic in the n8n workflow.
- **Audit dashboards** *(Future Enhancement)* — a visualization layer over
  the existing Audit Trail data, making the `Processed`/`Failed` history
  already recorded in Airtable queryable and browsable instead of
  requiring a manual Airtable lookup.
- **Performance dashboards** *(Future Enhancement)* — visualizing the
  latency and throughput metrics discussed in
  `docs/performance-optimization.md` and
  `docs/scalability-10k-records-per-day.md`, over time rather than as a
  point-in-time code-level analysis.
- **Historical trend analysis** *(Future Enhancement)* — comparing current
  metrics against historical baselines (e.g. "is validation failure rate
  higher this month than last"), which requires the metrics collection
  layer above to exist first.
- **Operational reporting** *(Future Enhancement)* — periodic summaries
  (e.g. weekly) of system health and throughput for stakeholders who need
  the aggregate picture rather than per-report detail.

Every layer here is additive: the existing Audit Trail, Processing
Failures, and application logs remain the system of record for "what
happened to this specific request"; this architecture would sit alongside
them as the system for "how is the platform doing in aggregate."

---

## Future Enhancements

Every item below is a **Future Enhancement**. None is implemented in this
repository today.

- **Prometheus** — a metrics collection and storage system, the typical
  backing store for the Metrics collection layer described above.
- **Grafana** — a dashboarding tool commonly paired with Prometheus, for
  the Dashboards described above.
- **OpenTelemetry** — an instrumentation standard for emitting traces and
  metrics from application code, relevant to closing the "no distributed
  tracing" gap identified above.
- **ELK Stack (Elasticsearch, Logstash, Kibana)** — an alternative
  approach to centralized log aggregation and search, extending (not
  replacing) the existing rotating file logs in `src/logging_config.py`.
- **Loki** — a log aggregation system designed to pair with Grafana,
  another option for the centralized log aggregation layer above.
- **CloudWatch** — a cloud-provider-native option for infrastructure and
  application monitoring, relevant if the platform is deployed on AWS.
- **Azure Monitor** — the equivalent cloud-provider-native option if
  deployed on Azure.
- **Datadog** — a commercial, unified observability platform covering
  logs, metrics, and traces, an alternative to assembling the
  Prometheus/Grafana/Loki/OpenTelemetry combination piece by piece.
- **PagerDuty** — an alerting and on-call notification platform, the
  typical destination for the Alert manager described above.
- **Distributed tracing** — end-to-end request tracing across the FastAPI
  layer, the OpenAI call, and the n8n workflow it triggers, closing the
  gap where a single request's path today can only be reconstructed
  manually from log timestamps.

---

## Summary

The current implementation already provides monitoring sufficient for an
MVP: application logs (`src/logging_config.py`), structured API error
handling (`src/api/errors.py`), validation error reporting
(`src/ingestion/pipeline.py`), retry logging
(`src/ai/openai_client.py`), and the n8n workflow's Audit Trail and
Processing Failures records together give an operator enough information
to understand what happened to any individual upload and why. This is
consistent with the "Explainability" and "Reliability" principles in
`CLAUDE.md`, and appropriate for a system whose primary validated use case
is still one analyst, one file, one report.

The monitoring architecture proposed here — metrics collection,
dashboards, alerting, and infrastructure monitoring — is a practical
roadmap toward enterprise-grade observability, not a signal that current
monitoring is inadequate for where the platform is today. Every proposed
layer sits alongside the existing Audit Trail and Processing Failures
mechanism rather than replacing it, and none of it requires changing what
the pipeline (`Read → Validate → Clean → Dedupe → KPI Engine → AI → Store
→ Notify`, per `docs/architecture.md`) actually does — only how visible
its behavior is once it's running at volume.
