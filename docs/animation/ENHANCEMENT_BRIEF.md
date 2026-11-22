# CatalogForge intake animation enhancement

## Purpose

Give the repository a production-reference visual for the core promise: a messy supplier file becomes a governed, reviewable catalog record before anything reaches a channel.

## Model boundary

The reel is generated from the same deterministic code used by the demo API:

- `backend/app/services/intake.py` validates file signature, extension, size, and SHA-256 checksum.
- `backend/app/services/pipeline.py::deterministic_extract` maps supplier fields into normalized candidates and preserves source evidence coordinates.
- `backend/app/services/pipeline.py::run_validations` evaluates destination readiness.
- `backend/app/services/duplicates.py::score` produces a duplicate-review signal; it never auto-merges records.
- `backend/app/services/publisher.py::publish_mock` is represented as an approval-gated, idempotent mock destination.

This is a deterministic rules/parser reference, not a learned-model accuracy claim. The reel labels that boundary directly so it is safe to use in a README, product walkthrough, or demo recording.

## Reproducible artifacts

Run:

```bash
py -3.12 scripts/generate_animation_sequence.py
```

The command reads the committed synthetic fixture `demo_data/source_documents/Synthetic_vendor_export_01.csv` and writes:

- `docs/animation/catalogforge_intake_sequence.json` — source checksum, model references, candidate preview, and scene events.
- `frontend/public/animation/catalogforge-intake-reel.html` — dependency-free animated reference reel with pause, replay, and stage selection controls.

Serve `frontend/public` through the existing frontend dev server or any static server to view the reel. No network calls, API keys, or external destinations are required.
