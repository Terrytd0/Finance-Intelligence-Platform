# Design Review

## Reviewer

Claude Code (acting as Principal AI Automation Engineer / Technical Lead)

## Date

2026-07-18

## Scope

Documents reviewed: `README.md`, `docs/architecture.md`,
`docs/business_requirements.md`, `docs/decisions.md`. No implementation
exists yet (`workflows/`, `assets/`, `examples/` contain only placeholders),
so this is a pre-build architecture approval review, not a code review.

---

## 1. Business Understanding

**Does the proposed solution address the business problem?**

Mostly, yes. The pipeline (ingest → validate → clean → calculate KPIs →
AI analysis → store → notify → audit) maps directly onto the manual steps
analysts describe doing today, and the linear design makes it easy to
explain to a non-technical stakeholder why a number came out the way it did.
That directly serves the stated goal of cutting 2–3 hours of manual work
down to minutes.

**Missing or unclear requirements:**

- **"Automated ingestion" vs. manual upload.** `docs/business_requirements.md`
  and the README both promise "automated ingestion," but
  `docs/architecture.md` step 1 is "User uploads a financial spreadsheet."
  A manual upload is not automated ingestion — it still requires a human to
  find the file, and to remember to do it. If the client's expectation is
  hands-off automation, the design needs a real source connection (SFTP
  drop, email attachment watcher, accounting/ERP API pull) or the
  requirement needs to be corrected to "semi-automated, upload-triggered."
  **Fix:** pick one and state it explicitly in `business_requirements.md`.
- **No definition of "anomaly."** Nothing specifies what makes a KPI
  anomalous (threshold, rolling average, standard deviation, prior-period
  comparison). Without a testable definition, "AI anomaly detection" is not
  a requirement that can be verified. **Fix:** add a concrete rule (e.g.,
  "flag any KPI that deviates more than X% from its trailing 3-month
  average") to the business requirements.
- **No human sign-off before distribution.** Reports go straight to
  stakeholders after AI processing. For a finance client, some form of
  review/approval gate before external-looking numbers go out is normally a
  hard requirement, not a "future enhancement." **Fix:** either promote
  "Approval workflows" out of Future Enhancements into V1 scope, or have the
  client explicitly accept the risk of unreviewed AI-generated summaries.
- **No accuracy/error-rate target.** "Maintaining accuracy" is stated as a
  goal but never quantified, so there's no way to know if the system is
  meeting it. **Fix:** define an acceptable KPI calculation error rate and a
  process for catching AI summary errors (spot-checks, sampling, etc.).
- **No data volume or scale assumptions.** "Scalable" is listed as an NFR
  with nothing to scale against (files/day, rows/file, number of client
  entities). This makes the Airtable/n8n choices impossible to validate (see
  §2 and §3). **Fix:** get the client's rough current and 12-month volume
  and record it in `business_requirements.md`.
- **No role/access model**, despite multiple humans presumably touching
  uploads, reports, and notifications. RBAC is deferred to "Future
  Enhancements," but *some* access boundary is needed on day one to avoid an
  unauthenticated free-for-all. See §5.

---

## 2. Architecture

**Is it logical?** Yes — a single linear pipeline is the right shape for
this problem. It's easy to reason about, easy to explain to the client, and
matches the CLAUDE.md preference for explainability over cleverness.

**Scalability concerns:**

- **Airtable is the biggest scaling risk in the design.** Airtable enforces
  per-base record caps and API rate limits (a handful of requests/second per
  base). A platform meant to retain historical KPI data for trend/anomaly
  detection, and later support "multi-company" (already listed as a Future
  Enhancement), will hit these ceilings. `docs/decisions.md` doesn't contain
  an ADR for Airtable at all, even though `architecture.md` already treats
  it as decided — only n8n has a documented decision record. **Fix:** write
  an ADR for the storage layer that states Airtable is MVP-only, names the
  concrete threshold (rows, requests/sec, or company count) that triggers
  migration to a real database (e.g., Postgres), and treats that migration
  as a planned piece of work, not an afterthought.
- **n8n's own scaling story is undocumented.** Self-hosted n8n needs a plan
  for queue mode / worker scaling as workflow volume grows; nothing in the
  docs addresses this, so "scalable workflow architecture" (claimed in the
  README's Key Features) isn't yet backed by a plan.
- **No concurrency/backpressure handling** is described for simultaneous
  uploads (multiple files/companies at once hitting Airtable's and OpenAI's
  rate limits). Retries are mentioned, but not backoff behavior on 429s.

**Unnecessary components:** None — the pipeline is already minimal;
Validation and Cleaning are two separate steps but that's reasonable for
testability, not bloat.

**Missing components:**

- **No dedicated, tamper-evident audit log store.** `architecture.md` claims
  "audit logs are immutable," but the diagram never shows where they live.
  If they live in Airtable rows, they are not immutable — anyone with base
  edit access can change or delete them, which contradicts the stated
  security property. **Fix:** either use an append-only log destination
  (e.g., a write-once table/store, or hash-chained log entries) or scope
  down the claim to what's actually enforced.
- **No raw-file archive/staging zone.** If the goal is "trace every figure
  back to its source" (README Success Criteria), the original uploaded file
  needs to be retained somewhere immutable — it isn't currently part of the
  diagram.
- **No dead-letter/escalation path.** "Failed steps are retried
  automatically," but there's no answer for what happens after retries are
  exhausted — silently dropped data would be worse than the manual process
  it replaces.
- **No pipeline health monitoring**, distinct from the business
  notifications (email/Slack to stakeholders). If the n8n workflow itself
  stops triggering, nothing currently detects that.

---

## 3. Technology Choices

**n8n** — reasonable choice for an MVP automation platform: visual
workflows, built-in retries, self-hostable, decent integration library. The
existing ADR-001 is a good template — it states context, alternatives
(Python microservices, Zapier/Make), and honest trade-offs (visual
complexity at scale). No objection here.

**OpenAI** — appropriate for the *narrative* half of the AI step (turning
KPI numbers into a readable executive summary, explaining *why* a number
moved) — this is squarely what LLMs are good at. It is **not** appropriate
as the mechanism for *detecting* the anomaly itself. LLMs are not reliable
numeric anomaly detectors — they can miss real anomalies or "detect" ones
that aren't statistically meaningful, and their reasoning isn't reproducible
in the way an auditable finance pipeline needs.
**Recommendation:** split the "AI" box in the architecture diagram into two
steps: (1) a deterministic anomaly check inside the KPI Engine (e.g.,
threshold or rolling-average based — the same rule §1 recommends defining),
and (2) OpenAI used only to *explain* whatever the deterministic step
already flagged, plus write the summary. This keeps the system explainable
and auditable (a rule can be tested and cited; an LLM judgment can't) and
directly serves the "Reliability" and "Explainability" principles in
CLAUDE.md.

**Airtable** — acceptable as a fast MVP data store, and the ADR (if written)
should say so explicitly, but it's the weakest long-term piece of the stack:
no real transactional guarantees, limited audit/versioning natively, and
rate/row limits that don't fit "scalable" or "multi-company" ambitions.
**Recommendation:** treat it as intentionally disposable and name its
replacement (Postgres/Supabase is a natural fit given the relational KPI/
audit data) in a follow-up ADR now, rather than deciding under pressure
later.

**Would I recommend different technology today?** No wholesale change — the
combination is right for an MVP. The two concrete swaps I'd make are: (1)
statistical/rule-based anomaly detection instead of LLM-based, and (2) a
documented, budgeted trigger for moving off Airtable.

---

## 4. Risks

**What could fail:**

- AI-generated executive summary contains a wrong or hallucinated
  conclusion, and it reaches an executive with no human check first (see
  §1's missing approval gate).
- Airtable rate limit or outage blocks writes mid-pipeline, since it's both
  the data store and (implicitly) part of the audit trail.
- n8n instance itself goes down (self-hosted, no documented HA/backup plan)
  — single point of failure for the entire platform.
- Retries are not confirmed to be idempotent — an automatic retry after a
  partial failure could create duplicate Airtable records or duplicate
  stakeholder notifications.
- Real-world spreadsheet edge cases (merged cells, locale-specific number
  formats like `1.234,56`, hidden sheets, extra header rows) breaking
  Validation/Cleaning — not addressed anywhere in the docs.
- Currency standardization is listed as a Cleaning step, but no FX rate
  source is named — stale or missing rates silently produce wrong KPIs.

**Assumptions being made:**

- Uploaded spreadsheets roughly match the expected schema (manual upload is
  trusted input).
- OpenAI's output is accurate enough to reach executives without a
  human-in-the-loop check.
- Airtable can carry production financial data at whatever the client's real
  volume turns out to be (volume was never captured — see §1).
- n8n hosting/uptime/backups are handled by "someone," but this isn't
  assigned anywhere in the docs.
- "Auditability" is satisfied by logging steps, without defining retention
  period, who can query the logs, or how immutability is actually enforced.

**Operational issues likely in production:**

- Large n8n workflows become visually unwieldy to debug — the ADR already
  flags this as a known negative but proposes no mitigation (e.g.,
  sub-workflows, naming conventions).
- OpenAI + Airtable costs both scale with volume/seats with no budget
  governance mentioned.
- No workflow versioning/promotion process (dev → prod) is described for
  n8n, so it's unclear how a change gets tested before it touches real
  client data.

---

## 5. Security

- **Client financial data is sent to a third-party LLM (OpenAI) with no
  stated data-handling policy** — no mention of a zero-data-retention
  agreement, redaction of sensitive fields (account numbers, counterparties)
  before the API call, or which OpenAI data-processing terms apply. For an
  investment-management client, this needs to be resolved before any real
  data flows through the pipeline. **Fix:** add a data-classification pass
  before the AI step, and document the OpenAI data-retention terms being
  relied on.
- **"API keys stored as environment variables"** is a floor, not a
  ceiling — no mention of rotation, least-privilege scoping, or using n8n's
  built-in encrypted credential store (which is preferable to raw env vars
  for anything wired into a workflow node). **Fix:** use n8n credentials
  storage explicitly and document a rotation cadence.
- **"Audit logs are immutable" is asserted but not enforced anywhere in the
  design** (see §2). This is a security claim the current architecture
  cannot back up if logs live in an editable Airtable table. **Fix:** name
  the actual mechanism (append-only store, hash chaining, or a
  write-once log service).
- **No authentication model for the upload trigger.** If ingestion is a
  public-facing webhook, it needs auth, file-size limits, and file-type
  validation to avoid malicious uploads; none of this is mentioned.
- **No access control on notification distribution lists.** A
  misconfigured Slack channel or email group could leak confidential
  financials outside the intended audience — nothing in the docs describes
  how recipient lists are managed or reviewed.
- **No compliance framing** (SOC 2 / data residency / retention policy)
  for a client in financial services, where this is often a contractual
  requirement, not a nice-to-have.

---

## 6. Maintainability

The documentation habits here are genuinely good — `architecture.md`,
`decisions.md`, and `business_requirements.md` are clear, readable, and
follow a consistent structure. That's the right foundation for a
maintainable project and worth preserving.

**Gaps:**

- **Decision records are inconsistent with what's already been decided.**
  `architecture.md` presents n8n, OpenAI, Airtable, and Gmail/Slack as
  settled technology choices, but `decisions.md` only contains an ADR for
  n8n. The README, meanwhile, says the technology stack is "to be
  finalized." Three different documents currently disagree about whether
  the stack is locked in. **Fix:** write ADR-002 (OpenAI) and ADR-003
  (Airtable/notifications) with the same rigor as ADR-001, and update the
  README once they're accepted so all four documents agree.
- **Nothing to extend yet.** `workflows/`, `examples/`, and `assets/` are
  empty placeholders, so "will another engineer be able to extend this"
  can only be answered for the design, not the implementation. Once
  workflows exist, they'll need a stated export/versioning convention (how
  n8n JSON exports live in `workflows/`, how changes get reviewed) since
  visual-workflow diffs are much harder to code-review than plain text.
- **No sample data or schema contract.** `examples/` is empty; a sample
  CSV/Excel file with the expected columns would make the ingestion
  contract concrete for whoever builds Validation, and would double as a
  test fixture.

**Suggested improvements:**

- Add the missing ADRs (OpenAI, Airtable) before implementation starts.
- Add a short "how to add a new report type" note to `architecture.md`,
  since "Version 1" language implies more report types are expected later.
- Add at least one example input file and one example generated report to
  `examples/` to anchor the design in something concrete.

---

## 7. Overall Recommendation

The pipeline shape is sound, the documentation discipline is above average
for this stage, and the technology choices are defensible for an MVP. What's
missing is not a different architecture — it's a set of concrete decisions
that matter specifically because this system handles financial data destined
for executives: a human review gate before distribution, a real mechanism
for audit-log immutability, a documented plan for OpenAI data handling, and
ADRs for the two technology choices (OpenAI, Airtable) that are currently
undocumented despite being treated as final. None of these require
redesigning the pipeline; they require closing gaps before real client data
flows through it.

**APPROVED WITH RECOMMENDATIONS**
