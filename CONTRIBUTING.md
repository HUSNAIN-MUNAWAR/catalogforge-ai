# Contributing to CatalogForge AI

Thanks for your interest in improving CatalogForge AI.

## Development setup

1. Copy `.env.example` to `.env`.
2. Install backend dependencies:

```bash
cd backend
python -m pip install -e ".[dev]"
```

3. Install frontend dependencies:

```bash
cd frontend
npm install
```

4. Apply migrations and seed demo data:

```bash
make migrate
make seed
```

## Development workflow

- Keep the seeded demo synthetic and clearly labeled.
- Preserve current architecture and evidence-first workflow design.
- Avoid claiming live third-party integrations or compliance coverage unless the code and docs support it directly.
- Prefer small, reviewable pull requests with a clear problem statement.

## Quality checks

Run the checks relevant to your change before opening a PR:

```bash
make verify-backend
cd frontend && npm run lint
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npm run test:e2e
```

## Pull requests

- Describe what changed and why.
- Include screenshots for meaningful UI updates.
- Call out any limits, mocks, or follow-up work honestly.
- Do not commit secrets, `.env`, database files, local screenshots with personal data, or dependency directories.

## Reporting issues

- Use the bug report template for reproducible defects.
- Use the feature request template for product or architecture ideas.
- For security-sensitive reports, follow `SECURITY.md`.
