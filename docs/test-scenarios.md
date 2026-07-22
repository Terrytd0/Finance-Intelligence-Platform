# Manual Test Scenarios

## Overview

This document records the manual functional and end-to-end scenarios executed against the Finance Intelligence Platform. These scenarios validate user-facing behaviour, API functionality, data validation, error handling, and end-to-end workflow execution through n8n.

Evidence for key scenarios, including the health endpoint and OpenAI timeout retry handling, is provided in the `screenshots/` directory.

| ID | Scenario | Type | Expected Result | Status |
|----|----------|------|-----------------|--------|
| TS-01 | CSV Upload | Functional | Report is successfully generated containing calculated KPIs and AI-generated anomaly analysis. | ✅ Passed |
| TS-02 | XLSX Upload | Error Handling | Upload is rejected because only CSV files are supported. | ✅ Passed |
| TS-03 | Duplicate Transactions | Functional | Duplicate transaction records are removed during processing. | ✅ Passed |
| TS-04 | Missing Required Values | Validation | Rows missing required fields are rejected during validation. | ✅ Passed |
| TS-05 | Lowercase Currency Codes | Data Cleaning | Currency codes are normalized to uppercase. | ✅ Passed |
| TS-06 | Leading/Trailing Whitespace | Data Cleaning | Leading and trailing whitespace is removed from applicable fields. | ✅ Passed |
| TS-07 | OpenAI Timeout | Error Handling | The HTTP Request node retries the request three times before routing execution to the failure workflow. | ✅ Passed |
| TS-08 | Health Endpoint | API | `GET /health` returns HTTP 200 with `{"status":"ok"}`. | ✅ Passed |
| TS-09 | Empty CSV | Validation | Request is rejected with a structured validation error and error identifier. | ✅ Passed |
| TS-10 | Malformed CSV | Validation | Malformed CSV is rejected with a structured processing error and error identifier. | ✅ Passed |

## Notes

- Manual testing was performed using FastAPI Swagger UI, direct API requests, and end-to-end workflow execution through n8n.
- Failure scenarios were validated by intentionally triggering invalid inputs and service failures.
- Screenshots of critical validation scenarios are included in the `assets/screenshots/` directory.