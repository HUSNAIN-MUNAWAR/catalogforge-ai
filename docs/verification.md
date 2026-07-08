# Verification

Verification notes from the current CatalogForge AI launch-hardening pass.

## Backend

Executed successfully:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ..\.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
.............                                                            [100%]
```

The backend suite covers login, workspace switching, tenant isolation, intake, extraction, review, duplicate governance, change sets, publish flows, launch readiness, audit export, and API-key boundaries.

Executed successfully:

```bash
cd backend
..\.venv\Scripts\python.exe -m compileall -q app tests
```

## Migration check

Migration verification against a fresh SQLite file was attempted with:

```bash
cd backend
DATABASE_URL=sqlite:///./phase3_migration_test.db
PYTHONPATH=.
alembic upgrade head
```

The Windows execution environment did not return a clean Alembic completion signal before process cleanup. Direct inspection of the generated SQLite file confirmed that the migration-created tables exist, including:

- `launch_readiness_checks`
- `data_contracts`
- `saved_entity_views`

Because the Alembic wrapper did not complete cleanly in this environment, this check should be treated as partially verified rather than fully passed.

## Frontend

Frontend dependency installation was attempted with:

```bash
cd frontend
npm install --no-audit --no-fund
```

The install was blocked by registry download timeouts in the execution environment, including `ETIMEDOUT` responses while fetching packages such as `next`, `react`, `react-dom`, `framer-motion`, and `@next/swc-win32-x64-msvc`.

Because dependencies could not be installed reliably here, the following frontend checks were not completed in this pass:

- `npm run lint`
- `npm run typecheck`
- `npm run build`
- `npm run test:e2e`
- screenshot regeneration through Playwright

The repository still includes real existing screenshot assets under `assets/screenshots/`.

## Runtime API check

The local machine already had another service occupying port `8000`, so a direct port-`8000` API smoke check would have been misleading. A safer startup form was documented in the README and `Makefile`:

```bash
cd backend
python -m uvicorn app.main:app --app-dir . --reload --port 8000
```

This avoids ambiguous local module resolution when multiple editable projects expose a top-level `app` package.

## Docker

Docker verification could not be executed because Docker is not installed in this environment.

## Claim policy

Do not claim:

- real OCR accuracy
- real LLM extraction
- live Shopify, WooCommerce, ERP, PIM, or marketplace sync
- live webhook, Slack, email, or object-storage delivery
- real customer data
- compliance certification

CatalogForge AI remains a synthetic, deterministic local demo unless contributors intentionally add live integrations and document them accordingly.
