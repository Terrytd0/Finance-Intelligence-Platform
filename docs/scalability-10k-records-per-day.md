# Scalability Strategy for 10,000+ Records per Day

## Status

This document describes two distinct things and, like
`docs/performance-optimization.md` and `docs/batch-processing.md`, is
careful not to blur them:

1. **The current scalability characteristics of the platform**, verified
   directly against the code in `src/`, `n8n/Finance-Intelligence-Pipeline.json`,
   and the repository as a whole (there is, for example, no `Dockerfile`,
   `docker-compose.yml`, or any deployment/orchestration configuration
   anywhere in this repository as of this writing).
2. **Architectural recommendations for enterprise-scale growth**, none of
   which are implemented. Every recommendation is labeled **Future
   Enhancement**.

The current MVP (Minimum Viable Product) has been exercised against the
fixtures in `data/sample/` and the test suite in `tests/`, which validate
correctness of individual pipeline runs — not volume. **There is no load
test, benchmark, or production deployment evidence anywhere in this
repository indicating the system has processed, or been proven capable of
processing, 10,000 records per day.** This document should not be read as
a claim that this threshold has already been met; it is a gap analysis and
a roadmap toward it.

---

## Purpose

Scalability matters in a financial intelligence platform because the
system's usefulness is defined by whether it keeps working as the business
around it grows, not just whether it works for a demo. Concretely:

- **Growing client numbers** — Horizon Capital Partners' stated ambitions
  already include multi-company support (README, Future Enhancements), and
  each additional client is additional upload volume the platform needs to
  absorb without degrading service to existing clients.
- **Higher transaction volumes** — a single client's transaction volume
  tends to grow with their business, not stay fixed at whatever the
  original test fixtures assumed.
- **Multiple simultaneous uploads** — end-of-day and end-of-month reporting
  in particular tend to cluster many uploads into a short window rather
  than spreading evenly across the day (see `docs/batch-processing.md`'s
  discussion of end-of-day reporting).
- **Increasing AI usage** — every additional report is an additional
  OpenAI request; cost and latency both scale with volume unless
  deliberately managed (see [AI Scalability](#ai-scalability)).
- **Operational reliability** — a platform that produces figures executives
  act on needs to keep working under load, not degrade in ways that are
  invisible until something breaks in production (`docs/design_review.md`
  §4 already lists several failure modes that volume would make more
  likely, not less).
- **Maintaining response times as demand increases** — the business goal
  of cutting analyst workload from hours to minutes (README) only holds if
  response times don't quietly grow back toward "hours" once real volume
  arrives.

The focus here is business continuity and predictable behavior at scale,
not raw speed — that distinction is the same one drawn in
`docs/performance-optimization.md`'s Purpose section.

---

## Current Architecture

The current architecture, as implemented, is a single linear pipeline
fronted by one HTTP API and orchestrated by one workflow tool:

- **FastAPI** (`src/api/main.py`) — a single application exposing `GET
  /health` and `POST /analyze`. `/analyze` accepts one `.csv` file per
  request and runs it synchronously through the full pipeline before
  returning a JSON `AnomalyReport`.
- **Validation pipeline** (`src/ingestion/`) — `run_pipeline()` reads,
  validates (`validator.py`, rules in `docs/validation_rules.md`), cleans
  (`cleaner.py`), and deduplicates (`deduplicator.py`) rows from one file,
  entirely in memory, within the request.
- **KPI engine** (`src/analytics/kpi_engine.py`) — deterministic,
  non-AI calculation of totals, revenue by client, expense breakdown,
  monthly totals, and largest transactions for that file's transactions.
- **OpenAI analysis** (`src/ai/prompt_builder.py`, `src/ai/anomaly_detector.py`,
  `src/ai/openai_client.py`) — one prompt built from that file's KPIs and
  transactions, sent as one request to OpenAI, with retries on transient
  failures (exponential backoff, scoped to genuinely retryable errors — see
  `docs/performance-optimization.md`'s AI Performance Optimization
  section).
- **n8n orchestration** (`n8n/Finance-Intelligence-Pipeline.json`, per
  ADR-001 in `docs/decisions.md`) — a `Webhook` node triggers an `HTTP
  Request` node that calls `/analyze`, followed by a `Switch` node that
  routes on returned severity.
- **Airtable** — the storage layer for report archival, referenced from the
  n8n workflow's per-severity "Archive Report" nodes.
- **Email and Slack** — the two notification channels, wired as per-severity
  nodes in the same n8n workflow.
- **Audit Trail** — the n8n workflow's "Update Audit Trail" Airtable nodes,
  recording a `Processed`/`Failed` status per execution, as already
  described in `docs/role-based-access-design.md` and
  `docs/performance-optimization.md`.

This architecture is appropriate for an MVP for the same reasons given in
`docs/batch-processing.md`'s Current Processing Workflow section: it is
the simplest design that fully delivers the pipeline for the validated use
case (one analyst, one file, one report), it is easy to test end-to-end
(`tests/test_api.py`), and it keeps every failure mode traceable to one
request rather than a distributed system's worth of moving parts. Building
for 10,000+ records/day before the single-record-at-a-time path was proven
correct would have front-loaded infrastructure complexity onto a system
that hadn't yet validated its core logic.

---

## Current Scalability Constraints

These are the same class of constraint already identified in
`docs/performance-optimization.md`'s "Current Bottlenecks" and
`docs/batch-processing.md`'s "Current Limitations" — reasonable MVP design
decisions, not architectural flaws, viewed here specifically through the
lens of what happens as record volume grows past MVP levels.

- **Synchronous request processing.** `/analyze` is a non-`async def`
  endpoint that blocks for the full pipeline duration, including the
  OpenAI call. At low volume this is invisible; at higher upload
  concurrency, requests queue behind whatever the FastAPI process's thread
  pool is doing.
- **Single upload workflow.** As detailed in `docs/batch-processing.md`,
  there is no batch endpoint — 10,000 records arriving as, say, 50 files in
  a morning would require 50 separate sequential requests today, each
  paying its own full pipeline and OpenAI round-trip cost.
- **No distributed workers.** There is exactly one FastAPI process implied
  by the current code and no deployment configuration (no `Dockerfile`,
  no process manager config, no multi-worker `uvicorn`/`gunicorn` setup)
  anywhere in the repository defining how more than one instance would run.
- **Airtable limitations.** As `docs/design_review.md` §2 already
  documents, Airtable enforces per-base row caps and request-rate limits.
  This is the constraint most directly at odds with a 10,000+ records/day
  target, since Airtable is currently both the report store and the audit
  trail, meaning both purposes compete for the same rate-limit budget as
  volume grows.
- **AI latency.** Every report's request path includes a synchronous
  round-trip to OpenAI, whose latency is outside this system's control;
  at volume, that latency is incurred by every single request in sequence
  rather than being absorbed by concurrent processing.
- **No horizontal scaling.** Nothing in the repository configures or
  documents running more than one instance of the FastAPI service behind a
  load balancer.
- **One OpenAI request per upload.** Confirmed in `src/ai/anomaly_detector.py`
  and `src/ai/prompt_builder.py` — there is no batching of multiple files'
  data into fewer LLM calls, so OpenAI request volume scales 1:1 with
  upload volume.
- **In-memory processing.** `src/ingestion/reader.py` reads an entire
  file's rows into memory as part of `run_pipeline`. This is unproven
  beyond the row counts in `data/sample/`, and nothing in the codebase
  streams or chunks large files.
- **No distributed caching.** There is no cache of any kind (no Redis, no
  in-process cache beyond `@lru_cache` on process-local `Settings` in
  `src/config.py`) — repeated or similar uploads are always fully
  reprocessed and always incur a fresh OpenAI call.

Each of these is the same trade-off already named in
`docs/performance-optimization.md` and `docs/batch-processing.md`: correct
and simple now, at the cost of throughput headroom that hasn't yet been
needed.

---

## Enterprise Scalability Strategy

**Everything in this section is a proposed architecture. None of it is
implemented.** Each recommendation is framed as an extension of the
existing pipeline (`Read → Validate → Clean → Dedupe → KPI Engine → AI →
Store → Notify`, per `docs/architecture.md`), not a replacement for it —
the same principle `docs/batch-processing.md` applies to its own proposed
architecture.

- **Horizontal FastAPI scaling** *(Future Enhancement)* — run multiple
  instances of the existing, unmodified FastAPI application behind a load
  balancer, so request volume is spread across processes instead of
  bottlenecked on one.
- **Load balancers** *(Future Enhancement)* — the component that makes
  horizontal FastAPI scaling possible, distributing incoming `/analyze`
  requests (or a future batch-upload endpoint, per `docs/batch-processing.md`)
  across available instances.
- **Worker pools** *(Future Enhancement)* — as in `docs/batch-processing.md`'s
  Enterprise Batch Processing Architecture, a pool of workers pulling jobs
  from a queue rather than processing inline in the request path; the
  pipeline code itself (`run_pipeline`, `generate_kpis`,
  `generate_anomaly_report`) would not need to change, only how and how
  often it's invoked.
- **Queue-based processing** *(Future Enhancement)* — decoupling "a file
  was received" from "a file was processed," the same architecture
  described in `docs/batch-processing.md`, which is also the natural
  mechanism for absorbing bursts of upload volume without dropping or
  rejecting requests.
- **Distributed processing** *(Future Enhancement)* — running the pipeline
  across multiple machines rather than one, once volume exceeds what a
  single host's worker pool can handle.
- **Database migration** *(Future Enhancement)* — moving off Airtable, as
  already recommended in `docs/design_review.md` §2–3, toward a
  transactional store (e.g. PostgreSQL) with real concurrency guarantees
  and no per-base rate ceiling.
- **Scalable storage** *(Future Enhancement)* — a storage layer sized and
  indexed for historical KPI/audit data retention at volume, not just
  MVP-scale record counts.
- **Asynchronous workloads** *(Future Enhancement)* — converting `/analyze`
  (or its batch equivalent) to `async def` and moving blocking I/O (the
  OpenAI call in particular) off the request thread, consistent with
  `docs/performance-optimization.md`'s "Asynchronous request handling"
  recommendation.
- **Stateless services** *(Future Enhancement)* — ensuring the FastAPI
  layer holds no in-process state that would prevent any instance from
  handling any request, which is what makes horizontal scaling behind a
  load balancer viable in the first place. The current implementation is
  already close to this — `Settings` (`src/config.py`) is the only
  process-level cached state, and it is read-only configuration, not
  per-request data — but this has not been verified under a genuinely
  multi-instance deployment.
- **Independent scaling of AI workers** *(Future Enhancement)* — since the
  OpenAI call is the slowest and most externally rate-limited step in the
  pipeline (`docs/performance-optimization.md`'s "Current Bottlenecks"),
  scaling the workers that make that call separately from the workers doing
  validation/KPI calculation would let the system add AI throughput without
  over-provisioning the cheaper, faster pipeline stages.

---

## Infrastructure Scaling

**Every item in this section is a Future Enhancement.** None is
implemented or configured anywhere in this repository today.

- **Multiple application instances** *(Future Enhancement)* — the concrete
  prerequisite for horizontal FastAPI scaling above; improves scalability
  by removing the single-process ceiling on concurrent request handling.
- **Containerization** *(Future Enhancement)* — packaging the FastAPI
  service (and, if separated, worker processes) as containers. No
  `Dockerfile` exists in this repository currently; this would need to be
  authored, not just enabled. Improves scalability by making "run another
  instance" a reproducible, automatable operation rather than a manual
  process-management task.
- **Kubernetes or Docker Swarm** *(Future Enhancement)* — an orchestration
  layer for running and scaling those containers, handling instance
  placement, restarts, and (with autoscaling, below) automatic capacity
  changes. Improves scalability by turning "add capacity" into a
  declarative, automated operation.
- **Cloud object storage** *(Future Enhancement)* — a durable store for raw
  uploaded files, addressing the "no raw-file archive/staging zone" gap
  `docs/design_review.md` §2 already flags, and giving the system a place
  to hold files awaiting processing at volume without depending on local
  disk or in-memory state.
- **Managed databases** *(Future Enhancement)* — a managed PostgreSQL (or
  similar) instance as the replacement data store discussed under Database
  migration above, improving scalability by removing Airtable's row/rate
  ceilings and adding real transactional guarantees for concurrent writes.
- **Redis** *(Future Enhancement)* — as already named in
  `docs/performance-optimization.md` and `docs/batch-processing.md`, both
  as a queue backend and as a cache for OpenAI responses/KPI results.
  Improves scalability by reducing duplicate work and giving the queue
  layer a fast, shared coordination point across multiple worker
  instances.
- **Autoscaling** *(Future Enhancement)* — automatically adding or removing
  application/worker instances based on load, so infrastructure cost
  tracks actual demand rather than being sized for peak volume at all
  times.
- **Distributed queues** *(Future Enhancement)* — a queue technology (see
  [Future Enhancements](#future-enhancements) below) that itself runs
  across multiple nodes, so the queue doesn't become a new single point of
  failure once everything else is scaled out.

---

## Data Scalability

Recommendations here are kept realistic and scoped to what this system's
data actually looks like — financial transaction records, KPI snapshots,
and audit/report history — rather than generic big-data advice.

- **Database indexing** *(Future Enhancement)* — contingent on the
  database migration discussed above; indexes would target the fields
  actually queried for historical trend and anomaly lookups (e.g. client
  ID, date range), which Airtable's current table structure doesn't
  support tuning for.
- **Partitioning** *(Future Enhancement)* — splitting transaction/report
  history by time period (e.g. by month) or by client, so queries against
  recent data don't need to scan the full historical set as it grows.
- **Historical archive strategy** *(Future Enhancement)* — a defined
  retention and archival policy for older records (e.g. moving data past a
  certain age to cheaper cold storage), which does not exist today; the
  current design has no retention period specified anywhere, a gap also
  noted in `docs/design_review.md`'s Risks section.
- **Moving beyond Airtable** *(Future Enhancement)* — the same
  recommendation as `docs/design_review.md` §2–3 and the Database
  migration item above, repeated here specifically because Airtable's rate
  and row limits are the single most direct data-layer obstacle to a
  10,000+ records/day target.
- **Streaming large datasets** *(Future Enhancement)* — reading files in
  chunks rather than loading an entire file into memory at once
  (`src/ingestion/reader.py` currently does the latter), relevant once
  individual files themselves grow large rather than just growing in
  number.
- **Incremental processing** *(Future Enhancement)* — processing only new
  or changed records in a re-uploaded or updated dataset, instead of
  reprocessing a full file every time, reducing redundant KPI calculation
  and OpenAI spend.
- **Storage optimization** *(Future Enhancement)* — right-sizing how much
  transaction-level detail is retained long-term versus summarized into
  KPI snapshots, once retention volume itself becomes a cost concern.

---

## AI Scalability

Cross-references `docs/performance-optimization.md`'s AI Performance
Optimization section throughout, since AI cost and latency are shared
concerns between single-request performance and multi-request scalability.

- **Dedicated AI workers** *(Future Enhancement)* — as noted under
  "Independent scaling of AI workers" above, separating the OpenAI-calling
  step into its own worker pool so it can scale (or be rate-limited)
  independently of validation/KPI calculation.
- **Request queues** *(Future Enhancement)* — queuing OpenAI requests
  specifically, so a burst of uploads doesn't attempt to open more
  concurrent OpenAI connections than the account's rate limits allow;
  directly related to Rate-limit handling below.
- **Prompt caching** *(Future Enhancement)* — not implemented today;
  `src/ai/prompt_builder.py` builds a fresh prompt per request with no
  reuse of previously-built prompt fragments.
- **Response caching** *(Future Enhancement)* — already named in
  `docs/performance-optimization.md`'s AI Performance Optimization Future
  Enhancements; caching by a hash of prompt content to avoid re-spending
  tokens on identical or near-identical resubmitted data.
- **Batching** *(Future Enhancement)* — combining multiple files' or
  clients' data into fewer OpenAI requests where business logic allows,
  reducing per-request overhead at volume.
- **Model selection** *(Future Enhancement)* — `src/config.py` already
  makes the OpenAI model configurable per environment
  (`DEFAULT_OPENAI_MODEL = "gpt-4o-mini"`); at scale, this existing lever
  could be used deliberately to trade off cost/latency against analysis
  quality based on observed volume and budget, rather than left at a
  fixed default.
- **Cost optimization** *(Future Enhancement)* — token usage monitoring
  (also named in `docs/performance-optimization.md`) becomes a scalability
  concern, not just a cost concern, once request volume is high enough that
  unbounded per-request token usage could hit account-level spend limits
  or rate ceilings.
- **Rate-limit handling** *(Future Enhancement)* — `src/ai/openai_client.py`
  already retries `RateLimitError` with exponential backoff for a single
  request (see `docs/performance-optimization.md`'s "Retry only what's
  actually retryable"). At the volume implied by 10,000+ records/day,
  rate-limit handling becomes a system-wide concern — coordinating request
  pacing across many concurrent workers, not just retrying within one
  request — which the current per-request retry logic does not address.

---

## Monitoring Scalability

**As in `docs/performance-optimization.md` and `docs/batch-processing.md`,
existing monitoring capability is limited and per-request, not
aggregated.**

**What exists today:**

- `src/logging_config.py`'s console and rotating file logging
  (`logs/app.log`), recording each pipeline run and OpenAI retry attempt
  individually.
- `PipelineResult.errors` (`src/ingestion/pipeline.py`), a structured
  per-file count of validation failures.
- The n8n workflow's Airtable "Update Audit Trail" nodes, recording a
  `Processed`/`Failed` status per execution — the same Audit Trail
  mechanism referenced in `docs/role-based-access-design.md`,
  `docs/performance-optimization.md`, and `docs/batch-processing.md`.

None of this is aggregated into a dashboard, and none of it currently
answers a question like "how many requests did the system handle in the
last hour" without manually reading log files or Airtable records.

**Recommended metrics once the system approaches enterprise volume**
*(all Future Enhancement)*:

- Requests per minute to `/analyze` (or its future batch equivalent).
- Uploads per day, trended against the 10,000 records/day target.
- Average API response time, and its distribution (not just the average —
  tail latency matters more as concurrency increases).
- Queue depth, once a queue exists (per `docs/batch-processing.md`).
- Worker utilization, once a worker pool exists.
- API latency, isolated from AI latency, so a slowdown can be attributed to
  the right layer.
- OpenAI latency specifically, since it is already the slowest step in the
  pipeline today.
- Airtable/database latency and error rate, particularly important given
  Airtable's known rate limits.
- Infrastructure utilization (CPU/memory per instance), once more than one
  instance exists to compare.
- Processing throughput (records or files processed per unit time),
  the most direct measurement against the 10,000 records/day target.

---

## Future Enhancements

Every item below is a **Future Enhancement**. None is implemented in this
repository today.

- **Kubernetes** — container orchestration for running and autoscaling
  multiple FastAPI and worker instances.
- **Redis** — queue backend and response/KPI cache, as already discussed
  above and in `docs/performance-optimization.md`.
- **RabbitMQ** — an alternative message broker to Redis for queue-based
  processing, as also named in `docs/batch-processing.md`.
- **PostgreSQL** — the recommended replacement for Airtable as the primary
  data store, per `docs/design_review.md` §2–3.
- **Distributed workers** — worker processes spread across multiple
  machines, for volume beyond a single host's capacity.
- **Object storage** — durable, scalable storage for raw uploaded files
  (e.g. S3-compatible storage), addressing the missing raw-file archive
  gap noted in `docs/design_review.md` §2.
- **Microservices** — splitting the current single FastAPI application
  into independently deployable services (e.g. ingestion, AI analysis)
  if and when their scaling needs diverge enough to justify the added
  operational complexity; not recommended prematurely, since the current
  monolith is still appropriately simple for validated volume.
- **Multi-region deployments** — running infrastructure in more than one
  geographic region, relevant only once latency-to-users or regulatory
  data-residency requirements (`docs/design_review.md` §5's compliance
  gap) make it necessary.
- **Automatic scaling** — infrastructure that adds/removes capacity based
  on measured load rather than fixed provisioning, as also named under
  Infrastructure Scaling above.
- **Disaster recovery** — backup, failover, and recovery procedures for
  both the application and its data store, none of which are documented
  anywhere in this repository today (n8n's own hosting/uptime/backup
  ownership is also called out as undocumented in `docs/design_review.md`'s
  Risks section).

---

## Summary

The current implementation is intentionally optimized for correctness,
maintainability, and reliability at MVP scale: a single FastAPI instance,
a synchronous pipeline, and a single n8n workflow processing one file at a
time. This is the right foundation to have validated first, and it has not
yet been tested — let alone proven — against a 10,000+ records/day
workload.

The architecture described in this document is a migration path, not a
rewrite. Horizontal scaling, a queue-based worker pool, a transactional
database in place of Airtable, and independently scaled AI workers would
all sit around or extend the existing `Read → Validate → Clean → Dedupe →
KPI Engine → AI → Store → Notify` pipeline — the same pipeline already
described in `docs/architecture.md` and implemented in `src/` — rather than
replacing it. Reaching enterprise-scale throughput means changing how much
of that pipeline runs concurrently and where its data lives, not changing
what the pipeline does.
