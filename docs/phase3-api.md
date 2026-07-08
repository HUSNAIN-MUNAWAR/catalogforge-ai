# Phase 3 API Additions

All endpoints live under `/api/v1` and use the same JWT or scoped API-key authentication boundary as the rest of CatalogForge AI.

## Launch

| Endpoint | Purpose |
| --- | --- |
| `GET /launch/readiness` | Evaluate release gates and persist launch-readiness evidence. |
| `GET /launch/golden-demo` | Return a guided demo journey using active workspace records. |
| `GET /launch/data-contracts` | List source and destination data contracts. |
| `GET /launch/saved-views` | List shared launch and operations views. |

## Governance

| Endpoint | Purpose |
| --- | --- |
| `GET /governance/permission-matrix` | Return server-side role/permission matrix. |
| `GET /governance/audit-export` | Export redacted CSV audit records and audit the export. |

## Product and publishing

| Endpoint | Purpose |
| --- | --- |
| `GET /products/{product_id}/release-gate` | Explain approval, validation, duplicate and destination blockers. |
| `GET /publish/jobs/{job_id}/delivery-proof` | Show connector attempts, logs, idempotency key and mock delivery proof boundary. |

## API key authentication boundary

Generated API keys can be used with:

```text
X-CatalogForge-API-Key: cf_live_...
```

The API verifies active, unexpired, unrevokeed keys, resolves the key's organization, records `last_used_at`, and writes an `api_key.used` audit event. The seeded legacy demo keys are intentionally not shown as raw secrets.
