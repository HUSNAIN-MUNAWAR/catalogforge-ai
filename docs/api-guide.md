# API guide

> **Synthetic demo disclaimer:** The workflows, vendors, documents, products, connectors, metrics, users, and outputs described here are synthetic unless a user uploads a local file. CatalogForge AI does not claim real customer data, production integrations, extraction accuracy, or compliance certification.

All API routes sit under `/api/v1`. Requests use bearer authentication and optionally `X-CatalogForge-Workspace` to select a membership-backed workspace. Missing membership returns a cross-tenant denial.

## Primary resources
- `auth`: login, refresh, logout, me, workspace switch
- `intake`: upload, list jobs, mapping preview, process, retry, cancel
- `documents`: metadata, preview, OCR blocks, evidence
- `products`: list, detail, update, approve/reject, versions, readiness, export
- `review`, `duplicates`, `taxonomy`, `quality`, `vendors`
- `publish`: destinations, jobs, retry, rollback, reconciliation
- `change-sets`, `reports`, `alerts`, `assistant`, `lineage`, `governance`, `pipeline`, `platform`

The OpenAPI document is available from FastAPI’s `/docs` endpoint in a running local environment. Pagination/sorting expansion is a planned API hardening area; list responses already return scoped item collections and totals where meaningful.
