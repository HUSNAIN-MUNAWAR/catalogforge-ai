# CatalogForge intake reel storyboard

| Scene | Visual cue | Evidence shown | Gate |
| --- | --- | --- | --- |
| 01 · receive | Supplier file token enters the route | Filename, type, byte size | File accepted into intake boundary |
| 02 · integrity | Token passes the checksum station | MIME, extension, SHA-256 prefix | Source lineage recorded |
| 03 · map | Canonical field station lights up | Inferred column count and core fields | Mapping preview available |
| 04 · extract | Product candidates appear in the flow | Candidate count and average confidence | Evidence coordinates retained |
| 05 · validate | Destination rules station turns green | Shopify mock readiness and completeness | Blocking rules must pass |
| 06 · review | Duplicate signal changes to amber | Similarity score and human-decision label | No automatic merge |
| 07 · release | Final station holds the token | Audit trail, idempotency, dry-run safe | Approval required before mock publish |

The source and exact generated values are recorded in `catalogforge_intake_sequence.json`. The source is synthetic and the final destination is explicitly a mock; the animation must not be presented as live customer telemetry or a production connector benchmark.
