# Architecture Decision Records

# ADR-001: Use n8n as the Workflow Orchestration Platform

## Status
Accepted

## Date
2026-07-18

## Context

Horizon Capital Partners requires a platform that automates the ingestion,
validation, KPI calculation, anomaly detection, reporting, and notification
workflow.

The solution must be maintainable, auditable, and easy to extend as business
requirements evolve.

## Decision

Use n8n as the primary workflow orchestration platform.

## Rationale

- Visual workflows are easy to review
- Built-in integrations reduce development time
- Supports AI agents
- Easy to add retries and error handling
- Open source and self-hostable
- Well suited to business process automation

## Alternatives Considered

### Python microservices

Pros
- Maximum flexibility

Cons
- Longer development time
- More infrastructure
- Harder to visualize workflows

### Zapier / Make

Pros
- Fast to build

Cons
- Less flexible
- Vendor lock-in
- More expensive at scale

## Consequences

Positive
- Faster development
- Easier maintenance
- Better auditability

Negative
- Complex workflows can become visually large