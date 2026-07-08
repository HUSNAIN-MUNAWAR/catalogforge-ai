# Phase 3 Launch Hardening

CatalogForge AI Phase 3 adds a launch-readiness layer on top of the Phase 2 product-data platform. It does not replace deterministic local workflows and does not require external OCR, LLM, destination, object-storage, email, webhook, Redis, PostgreSQL or Docker services to exercise the local demo.

## Launch Readiness Center

`GET /api/v1/launch/readiness` evaluates release gates from the active workspace. The endpoint refreshes persistent `launch_readiness_checks` rows and audits the evaluation.

Release gates:

1. Backend-enforced organization isolation.
2. Role-aware permission controls.
3. No-key deterministic local mode.
4. Immutable field evidence and lineage.
5. Validation and approval-gated publishing.
6. Destination reconciliation and retry evidence.
7. Audited evidence, report and API export controls.
8. Optional OCR, LLM, storage and connector boundaries.

The launch score is a demo-readiness metric, not a compliance certification.

## Data contracts

`GET /api/v1/launch/data-contracts` exposes workspace data contracts. Seeded contracts include:

- Shopify Mock Product Contract.
- Supplier CSV Intake Contract.

Contracts define required fields, owner role, version, policy, validation metadata and mock/production boundaries.

## Saved enterprise views

`GET /api/v1/launch/saved-views` exposes shared operations views such as Launch Blockers and Publishing Release Queue. These model how a production catalog team would save governed filters and column sets.

## Golden demo journey

`GET /api/v1/launch/golden-demo` returns a navigable real-entity sequence through intake, evidence, review, duplicate governance, change sets, mock publishing and lineage export.

## Claim boundaries

The Phase 3 UI and documentation must keep these claims explicit:

- All seeded data is synthetic.
- Mock connectors are not live external integrations.
- OCR and LLM providers are optional adapter boundaries.
- Security controls support enterprise deployment but do not imply certification.
- Local deterministic mode remains fully operational without external credentials.
