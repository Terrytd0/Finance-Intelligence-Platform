# Architecture

## Overview

The Finance Intelligence Platform is designed to automate the financial reporting workflow at Horizon Capital Partners. The system ingests spreadsheet data, validates and cleans it, calculates key financial metrics, uses AI to generate executive insights, stores the results, and distributes reports while maintaining a complete audit trail.

## Components

CSV

↓

Validation
- Verify required columns
- Check data types
- Detect missing values
- Reject malformed files

↓

Cleaning
- Remove duplicates
- Normalize dates
- Standardize currencies
- Trim whitespace

↓

KPI Engine
- Deterministic Anomaly detection
- Revenue growth
- Profit margin
- Operating expenses
- Budget vs Actual

↓

AI
- Explain KPI changes
- Explain anomalies
- Generate executive summary

↓

Data Storage (Airtable)

↓

Notifications

## Technology Mapping

| Component | Technology | Why |
|-----------|------------|------------|
| Workflow Orchestration | n8n | Visual workflows and integrations |
| AI Analysis | OpenAI | Natural language summaries and anomaly explanations |
| Data Storage | Airtable | Simple relational storage for MVP |
| Notifications | Gmail / Slack | Stakeholder communication |
| Source Data | CSV / Excel | Universal compatibility |

## Data Flow

1. User uploads a financial spreadsheet.
2. Validation ensures the file matches the expected schema.
3. Cleaning standardizes and prepares the data.
4. KPI Engine calculates financial metrics.
5. AI analyzes results and produces an executive summary.
6. Results are stored.
7. Notifications are sent.
8. Every step is logged for auditing.

## Error Handling

- Invalid files are rejected with clear error messages.
- Failed workflow steps are retried automatically.
- Errors are logged for investigation.
- Notifications are only sent after successful processing.

## Security Considerations

- Financial data is processed securely.
- Audit logs are immutable.
- API keys are stored as environment variables.
- Access is restricted to authorized users.

## Solution Architecture

             CSV / Excel
                  │
                  ▼
          Validation Service
                  │
                  ▼
           Data Cleaning
                  │
                  ▼
             KPI Engine
                  │
                  ▼
            OpenAI Analysis
             ↙          ↘
     Executive Report   Anomaly Report
                  │
                  ▼
              Airtable
                  │
         ┌────────┴────────┐
         ▼                 ▼
      Email            Slack