# Batch Processing Strategy

## Status

This document describes two distinct things and, like
`docs/performance-optimization.md`, is careful not to blur them:

1. **How uploads are processed today.** The MVP (Minimum Viable Product)
   processes uploads **individually** — one file per request, one request
   per pipeline run, one pipeline run producing one report. Nothing in
   `src/` or `n8n/Finance-Intelligence-Pipeline.json` accepts, queues, or
   processes more than one file per invocation. This is verified against
   the current code, not assumed from the architecture diagrams.
2. **How batch processing could be introduced for enterprise deployments.**
   Everything past [Current Limitations](#current-limitations) is a
   proposed architecture. None of it is implemented. Every section below
   that describes it is labeled **Future Enhancement**.

No claim in this document should be read as "batch processing already
exists." It does not. This document maps the path to it.

---

## Purpose

Financial reporting is rarely a single-file activity in a production
setting. Batch processing matters because:

- **End-of-day reporting** typically means every branch, desk, or business
  unit produces a file at roughly the same time, all of which need to be
  processed before the next business day's decisions are made — not one at
  a time, whenever an analyst happens to upload each one.
- **Multiple branch or entity uploads** need to be reconciled and reported
  on together, not as isolated, disconnected runs of the same pipeline.
- **Scheduled imports** (e.g. a nightly pull from an ERP or accounting
  system) produce files without a human present to upload them one by one —
  this is also the "automated ingestion" gap `docs/design_review.md` §1
  already flags in the current upload-triggered design.
- **Processing many client datasets** at once is the natural shape of work
  for a firm serving multiple clients, and is directly related to the
  "multi-company support" item already listed as a Future Enhancement in
  the README.
- **Operational efficiency and reduced manual intervention** are the
  platform's stated business goals (`docs/Business_Requirements.md`) —
  requiring a human to trigger and babysit each file individually does not
  fully deliver on "reduce reporting time" or "increase automation" once
  upload volume grows past a handful of files a day.

The business value here is throughput and hands-off operation at volume,
not a faster pipeline for a single file — that is the subject of
`docs/performance-optimization.md` instead.

---

## Current Processing Workflow

The current implementation processes one uploaded file through one linear,
synchronous pipeline, entirely within a single HTTP request.

```
CSV Upload
   ↓
Validation
   ↓
Cleaning
   ↓
Deduplication
   ↓
KPI Calculation
   ↓
AI Analysis
   ↓
(n8n) Storage & Audit Trail
   ↓
(n8n) Notifications
```

What happens, and where:

- **Upload** — a caller sends a single `.csv` file to `POST /analyze`
  (`src/api/main.py`). The endpoint signature is `file: UploadFile =
  File(...)` — a single file parameter, not a list. There is no endpoint
  anywhere in `src/api/` that accepts multiple files in one request.
- **Validation, Cleaning, Deduplication** — `run_pipeline()`
  (`src/ingestion/pipeline.py`) reads the file, validates each row
  (`src/ingestion/validator.py`, rules documented in
  `docs/validation_rules.md`), cleans surviving rows
  (`src/ingestion/cleaner.py`), and drops exact-duplicate rows
  (`src/ingestion/deduplicator.py`) — all for that one file, in memory,
  within the same function call.
- **KPI Calculation** — `generate_kpis()` (`src/analytics/kpi_engine.py`)
  computes deterministic totals, revenue by client, expense breakdown,
  monthly totals, and largest transactions from that single file's
  transactions.
- **AI Analysis** — `generate_anomaly_report()`
  (`src/ai/anomaly_detector.py`) builds one prompt from that file's KPIs
  and transactions and sends exactly one request to OpenAI
  (`src/ai/openai_client.py`), returning one `AnomalyReport`.
- **Storage & Audit Trail** — per the README and `docs/decisions.md`
  (ADR-001), n8n sits in front of the FastAPI backend. The workflow
  (`n8n/Finance-Intelligence-Pipeline.json`) calls `/analyze` via an `HTTP
  Request` node triggered by a single `Webhook`, then archives the result
  and updates the audit trail in Airtable.
- **Notifications** — the same n8n workflow's `Switch` node routes on the
  returned anomaly severity to per-severity Slack and Email notification
  nodes, as already described in `docs/performance-optimization.md`'s
  "Severity-based workflow branching" entry.

This is appropriate for the MVP: it is the simplest design that fully
delivers the end-to-end pipeline (`Read → Validate → Clean → Dedupe → KPI
Engine → AI → Store → Notify`) for the primary use case validated so
far — a single analyst uploading a single file and needing a single report
back. It keeps the system easy to reason about, easy to test (see
`tests/test_api.py`, `tests/test_ingestion.py`), and easy to debug, which
matches the "Explainability" and "Maintainability" principles in
`CLAUDE.md`. Building queueing, worker pools, or scheduling ahead of a
validated single-file workflow would have been solving a scaling problem
the project doesn't have evidence of yet.

---

## Current Limitations

These follow directly from the workflow above and are **intentional MVP
trade-offs**, not defects — the same framing `docs/performance-optimization.md`
uses for its "Current Bottlenecks" section, and consistent with
`docs/design_review.md`'s conclusion that the pipeline shape itself is
sound.

- **One upload processed per request.** `POST /analyze` has no concept of a
  batch, a job, or multiple files. A caller with ten files today must make
  ten separate requests.
- **No job queue.** There is no persistence layer between "file received"
  and "file processed" — processing starts immediately, inline, as part of
  handling the HTTP request. If the process is interrupted mid-request, the
  upload is simply lost; nothing durably records that it was ever received.
- **Synchronous execution.** As described in
  `docs/performance-optimization.md`'s "Current Bottlenecks," `/analyze` is
  a synchronous endpoint that blocks on the full pipeline, including the
  OpenAI call, before returning. A batch of files cannot be "submitted and
  checked on later" — the caller's connection stays open for exactly as
  long as one file takes to process.
- **No batch scheduling.** Nothing in the codebase or the n8n workflow
  triggers processing on a schedule (e.g. nightly). The `Webhook` node is
  the only trigger, meaning processing only happens when something calls
  it.
- **No concurrent worker pool.** There is no pool of workers pulling jobs
  off a queue; there is one FastAPI process handling one request's pipeline
  at a time per available thread, and one n8n workflow execution per
  webhook call.
- **One report generates one AI request.** There is no batching of
  multiple files' data into fewer OpenAI calls, and no mechanism to run
  multiple files' AI analysis concurrently — each file's `generate_anomaly_report()`
  call is independent and sequential relative to any other file a caller
  might also be uploading.

None of these are architectural mistakes. They are the direct, reasonable
consequence of building for the validated use case (single-file,
single-analyst upload) first, and are the same set of constraints that
make the MVP easy to explain and verify.

---

## Enterprise Batch Processing Architecture

**Everything in this section is a proposed, unimplemented architecture.**
It is described here to show how batch processing would extend the
existing pipeline, not replace it — the same `Read → Validate → Clean →
Dedupe → KPI Engine → AI → Store → Notify` shape would run once per file,
just orchestrated differently around it.

- **Upload queue** *(Future Enhancement)* — an intake layer that accepts
  multiple files (or a directory/archive of files) and durably records
  that each was received, before any processing starts. This replaces
  "processing starts inline in the request" with "processing starts once a
  job is queued," which is also what makes interrupted processing
  recoverable.
- **Job scheduler** *(Future Enhancement)* — a component responsible for
  triggering batch runs, whether on a schedule (nightly, hourly) or on
  demand (a batch upload endpoint), addressing the "no batch scheduling"
  limitation above and the "automated ingestion" gap in
  `docs/design_review.md` §1.
- **Worker pool** *(Future Enhancement)* — one or more worker processes
  that pull jobs from the queue and run the existing pipeline
  (`run_pipeline` → `generate_kpis` → `generate_anomaly_report`) against
  one file per job. The pipeline code itself would not need to change —
  only how it gets invoked (queue-driven rather than request-driven).
- **Independent batch workers** *(Future Enhancement)* — each worker
  processes one job at a time, but multiple workers running concurrently
  means multiple files' pipelines run in parallel across the batch, rather
  than the current one-request-at-a-time model.
- **Parallel processing across multiple uploads** *(Future Enhancement)* —
  a direct consequence of independent workers: since each file's pipeline
  run has no dependency on any other file's, there is no correctness
  reason they couldn't run concurrently once the surrounding infrastructure
  supports it.
- **Workload distribution** *(Future Enhancement)* — spreading jobs across
  available workers so that a batch of, say, fifty files isn't bottlenecked
  by however long the slowest single file takes if it happened to run
  first.
- **Retrying failed jobs without stopping the entire batch** *(Future
  Enhancement)* — today, a single file's processing failure is scoped to
  that one HTTP request (see `src/api/errors.py`'s structured error
  handling) and does not affect any other request. A batch architecture
  needs to preserve that same isolation at the job level: one file failing
  validation, hitting an OpenAI error, or timing out should not block or
  abort the other files in the same batch. This extends — rather than
  replaces — the existing per-request error isolation already in
  `src/api/errors.py`.
- **Batch completion summaries** *(Future Enhancement)* — a report, once
  all jobs in a batch finish, of how many files succeeded, how many failed,
  and why — something that does not exist today because there is currently
  no notion of "a batch" for anything to be a summary of.

---

## Batch Processing Strategy

The following describes **proposed architectural behavior**, not an
implementation, for how an enterprise batch run would operate once the
components above exist:

1. Receive multiple uploaded files (via a batch upload endpoint, a watched
   directory, or a scheduled pull — the source is an open question, not
   decided here).
2. Create one processing job per file, mirroring the existing one-file
   granularity of `run_pipeline()` / `generate_anomaly_report()` rather
   than inventing a new multi-file unit of work.
3. Place each job on a queue rather than processing it immediately inline.
4. Workers pull jobs from the queue and process them independently, each
   running the same `Read → Validate → Clean → Dedupe → KPI Engine → AI →
   Store → Notify` pipeline that already exists for a single upload today.
5. Successful jobs continue through Storage and Notifications exactly as a
   single upload does now (Airtable archival, audit trail update,
   severity-routed Slack/Email — all per the existing n8n workflow).
6. Failed jobs retry according to a defined retry policy, distinct from
   (but analogous to) the existing OpenAI-call retry logic in
   `src/ai/openai_client.py` — the same principle of "only retry what's
   actually retryable" would apply at the job level, not just the
   API-call level.
7. Jobs that exhaust their retries are logged separately as failed, rather
   than silently dropped or allowed to block the rest of the batch — this
   is a job-level version of the failure branch the n8n workflow already
   implements per file (see `docs/performance-optimization.md`'s reference
   to the `Switch` node's failure routing).
8. Once every job in the batch has either succeeded or exhausted retries, a
   batch summary is generated: files processed, files failed, and reasons
   for failure.
9. A batch-level notification is sent once the batch finishes, distinct
   from the existing per-file, per-severity notifications each individual
   report already triggers.

---

## Monitoring Batch Processing

**Distinguishing what exists from what doesn't matters here more than
anywhere else in this document**, since there is currently no batch concept
at all to monitor.

**What exists today** (per-file, not per-batch):

- `src/logging_config.py`'s console and rotating file logging
  (`logs/app.log`) records events for each individual pipeline run,
  including OpenAI retry attempts.
- `PipelineResult.errors` (`src/ingestion/pipeline.py`) carries structured
  per-row validation failures for a single file.
- The n8n workflow's Airtable "Archive Report" and "Update Audit Trail"
  nodes record a `Processed` / `Failed` status per individual execution —
  this is the same Audit Trail and Processing Failures mechanism referenced
  in `docs/role-based-access-design.md` and `docs/performance-optimization.md`,
  and it is scoped to one file per record today, with no batch identifier
  to group related records together.

**Recommended metrics once batch processing exists** *(all Future
Enhancement — none of this is collected in aggregate today)*:

- Batch duration (start to completion of every job in the batch).
- Queue length (jobs waiting to be picked up by a worker).
- Files processed per batch, and the pass/fail split.
- Failed job count, and failure reasons.
- Retry count per job.
- Worker utilization (idle vs. busy workers over the course of a batch).
- Throughput (files processed per unit time).
- Average processing time per file within a batch, to identify outliers
  (e.g. one unusually large file holding up a batch summary).

As with single-file monitoring in `docs/performance-optimization.md`,
none of this would be automatically aggregated by the existing logging or
Airtable status fields — a batch-aware metrics store is itself part of the
Future Enhancement, not a byproduct of adding a queue.

---

## Future Enhancements

Every item below is a **Future Enhancement**. None is implemented in this
repository today.

- **Celery** — a mature, widely-used task queue that could implement the
  job queue and worker pool described above.
- **Redis** — a natural backing store for a Celery (or similar) queue, and
  already named as a caching candidate in `docs/performance-optimization.md`'s
  Future Enhancements.
- **RabbitMQ** — an alternative message broker to Redis for the same queue
  role, better suited if delivery guarantees beyond what Redis offers are
  required.
- **n8n Queue Mode** — n8n's own built-in mode for distributing workflow
  executions across multiple workers, which would let the *existing* n8n
  workflow itself scale horizontally without introducing a separate queue
  technology, directly addressing the "n8n's own scaling story is
  undocumented" gap already noted in `docs/design_review.md` §2 and
  `docs/performance-optimization.md`'s "Current Bottlenecks."
- **Scheduled nightly processing** — a cron-triggered batch run (e.g. via
  n8n's schedule trigger, or an external scheduler) for end-of-day
  reporting, addressing the "scheduled imports" use case in
  [Purpose](#purpose).
- **Automatic workload balancing** — distributing jobs across workers based
  on current load rather than a fixed assignment.
- **Priority queues** — allowing, for example, a critical or time-sensitive
  client's file to be processed ahead of routine batch volume.
- **Distributed workers** — running worker processes across multiple
  machines rather than a single host, for batch volumes beyond what one
  machine's worker pool can handle.

---

## Summary

The current implementation prioritizes simplicity, correctness, and
reliability for a single-upload workflow: one file, one request, one
pipeline run, one report — fully traceable and easy to verify, which is
the right foundation for an MVP still being validated against real usage.
It does not batch, queue, schedule, or parallelize anything today.

The batch-processing architecture described in this document is a
migration path, not a rewrite. A queue, a worker pool, and job-level retry
and monitoring would sit *around* the existing `Read → Validate → Clean →
Dedupe → KPI Engine → AI → Store → Notify` pipeline — the same pipeline
already implemented and described in `docs/architecture.md` — rather than
replacing it. Introducing batch processing means changing how that pipeline
gets invoked and how many times it runs concurrently, not changing what it
does.
