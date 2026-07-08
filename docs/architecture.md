# Architecture

> **Synthetic demo disclaimer:** The workflows, vendors, documents, products, connectors, metrics, users, and outputs described here are synthetic unless a user uploads a local file. CatalogForge AI does not claim real customer data, production integrations, extraction accuracy, or compliance certification.

CatalogForge AI uses a Next.js client, a versioned FastAPI API, SQLAlchemy persistence, Alembic migrations, local demo storage, durable-job records, and adapter boundaries for OCR, LLMs, object storage, workers, and channel connectors.

```mermaid
flowchart TB
  Web[Next.js 15 workspace] --> API[/api/v1 FastAPI/]
  API --> Auth[JWT + workspace membership]
  API --> DB[(PostgreSQL / SQLite demo)]
  API --> Storage[Local storage / S3 boundary]
  API --> Jobs[Durable jobs + inline worker]
  Jobs --> Extract[Deterministic extraction]
  Extract --> Govern[Validation, duplicates, review]
  Govern --> Publish[Mock destination adapters]
  Publish --> Audit[Audit, lineage, reports]
```

The local path intentionally executes jobs inline for repeatability. A worker process exists as a deployment boundary and can later claim queued durable jobs from Redis or a queue framework. All critical resource reads are scoped by `organization_id` at the backend query layer.

## Request lifecycle

```mermaid
sequenceDiagram
  participant U as Workspace user
  participant W as Next.js
  participant A as FastAPI
  participant D as Database
  U->>W: Select organization / action
  W->>A: Bearer token + X-CatalogForge-Workspace
  A->>D: Resolve membership + organization scope
  D-->>A: Scoped entities
  A-->>W: Response + X-Request-ID
  W-->>U: Live status / mutation feedback
```

See also [multi-tenancy](multi-tenancy.md), [intake pipeline](intake-pipeline.md), and [deployment](deployment.md).
