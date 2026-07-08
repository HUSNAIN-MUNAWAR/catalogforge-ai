# Testing

> **Synthetic demo disclaimer:** The workflows, vendors, documents, products, connectors, metrics, users, and outputs described here are synthetic unless a user uploads a local file. CatalogForge AI does not claim real customer data, production integrations, extraction accuracy, or compliance certification.

## Backend coverage
The Phase 2 test suite verifies: login, workspace isolation, viewer restrictions, CSV/XLSX import, column mapping, source evidence, product correction/versioning, approval/readiness, duplicate governance, idempotent publishing, retry, rollback simulation, reconciliation, report generation/export, security headers, pipeline health, and governed assistant behavior.

```bash
cd backend
pytest -q
ruff check .
mypy app
```

## Frontend
```bash
cd frontend
npm run typecheck
npm run lint
npm run build
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

Browser tests require an available browser executable and a running or Playwright-managed frontend. Full end-to-end API mutation tests can be run by starting the API and setting `NEXT_PUBLIC_API_URL`.
