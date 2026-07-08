# Governed Catalog Intelligence Assistant

> **Synthetic demo disclaimer:** The workflows, vendors, documents, products, connectors, metrics, users, and outputs described here are synthetic unless a user uploads a local file. CatalogForge AI does not claim real customer data, production integrations, extraction accuracy, or compliance certification.

The Catalog Intelligence Assistant is intentionally narrow. It answers questions about the active workspace’s vendor quality, validation failures, duplicate queues, approval state, publishing state, taxonomy, and lineage. It cannot execute mutations or use sales/marketplace information that is not present.

Every response returns mode, executive summary, scope, data sources, metrics, related entities, caveats, confidence, limitations, and a suggested next action.

```mermaid
flowchart LR
  Question --> Scope[Active workspace + role scope]
  Scope --> Metrics[Persisted products/jobs/rules/audits]
  Metrics --> Answer[Governed answer with caveats]
  Answer --> Draft[Optional draft concept]
  Draft --> Confirm[Explicit user confirmation required]
```

Unsupported questions explicitly state that the data cannot be verified.
