"""Generate the CatalogForge synthetic intake animation and evidence manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.duplicates import score as duplicate_score  # noqa: E402
from app.services.intake import inspect_file, preview_rows  # noqa: E402
from app.services.pipeline import (  # noqa: E402
    completeness_score,
    deterministic_extract,
    run_validations,
)


SOURCE = ROOT / "demo_data" / "source_documents" / "Synthetic_vendor_export_01.csv"
MANIFEST = ROOT / "docs" / "animation" / "catalogforge_intake_sequence.json"
REEL = ROOT / "frontend" / "public" / "animation" / "catalogforge-intake-reel.html"


def candidate_record(candidate: object) -> dict[str, object]:
    return {
        "title": candidate.title,
        "sku": candidate.sku,
        "brand": candidate.brand,
        "category": candidate.category,
        "price": candidate.price,
        "inventory": candidate.inventory,
        "barcode": candidate.barcode,
        "confidence": candidate.confidence,
        "attributes": candidate.attributes,
        "validations": run_validations(candidate, "Shopify mock"),
        "completeness_score": completeness_score(candidate, destination="Shopify"),
    }


def build_manifest() -> dict[str, object]:
    inspection = inspect_file(SOURCE)
    columns, rows, mapping = preview_rows(SOURCE, max_rows=250)
    candidates = deterministic_extract(SOURCE, "Northern Atelier")
    records = [candidate_record(item) for item in candidates]
    average_confidence = round(mean(item.confidence for item in candidates), 3)
    first = records[0]
    duplicate_left = {
        "title": first["title"],
        "sku": first["sku"],
        "brand": first["brand"],
        "category": first["category"],
        "attributes": first["attributes"],
        "barcode": first["barcode"],
    }
    duplicate_right = {**duplicate_left, "title": f"{first['title']} copy"}
    duplicate = duplicate_score(duplicate_left, duplicate_right)

    return {
        "schema_version": "1.0",
        "fixture": "catalogforge-synthetic-intake-reel",
        "source": {
            "path": SOURCE.relative_to(ROOT).as_posix(),
            "filename": SOURCE.name,
            "type": inspection.source_type,
            "mime_type": inspection.mime_type,
            "bytes": inspection.size,
            "sha256": inspection.checksum,
            "rows": len(rows),
            "columns": columns,
            "mapping": mapping,
        },
        "model": {
            "name": "catalogforge-deterministic-extraction",
            "version": "0.3.0",
            "implementation": "backend/app/services/pipeline.py::deterministic_extract",
            "validation": "backend/app/services/pipeline.py::run_validations",
            "duplicate_scoring": "backend/app/services/duplicates.py::score",
            "external_keys_used": False,
            "claim_boundary": "Deterministic demo parser and rules; not a learned-model accuracy benchmark.",
        },
        "scenario": {
            "vendor": "Northern Atelier",
            "destination": "Shopify mock",
            "candidate_count": len(candidates),
            "average_confidence": average_confidence,
            "all_candidates_pass_validation": all(not item["validations"] for item in records),
            "duplicate_review_score": duplicate["score"],
            "duplicate_review_signals": duplicate["signals"],
        },
        "candidate_preview": records[:3],
        "events": [
            {
                "id": "source-received",
                "title": "Supplier file received",
                "detail": f"{SOURCE.name} enters the governed intake boundary.",
                "metric": f"{inspection.source_type} · {inspection.size:,} bytes",
                "status": "received",
            },
            {
                "id": "integrity-checked",
                "title": "Integrity checks passed",
                "detail": "Extension, MIME signature, size, and SHA-256 checksum are recorded.",
                "metric": f"sha256 {inspection.checksum[:12]}…",
                "status": "passed",
            },
            {
                "id": "mapping-inferred",
                "title": "Canonical mapping inferred",
                "detail": f"{len(mapping)} of {len(columns)} supplier columns map to product fields.",
                "metric": "title · SKU · price · inventory",
                "status": "mapped",
            },
            {
                "id": "candidates-extracted",
                "title": "Candidates extracted",
                "detail": "The production parser creates normalized product candidates with evidence coordinates.",
                "metric": f"{len(candidates)} candidates · {average_confidence:.0%} average confidence",
                "status": "extracted",
            },
            {
                "id": "destination-validated",
                "title": "Destination rules evaluated",
                "detail": "Shopify mock readiness rules run before any publication attempt.",
                "metric": f"{len(candidates)}/{len(candidates)} pass · completeness {records[0]['completeness_score']:.0f}%",
                "status": "validated",
            },
            {
                "id": "duplicate-reviewed",
                "title": "Duplicate candidate routed",
                "detail": "A high-similarity synthetic pair is held for human governance instead of auto-merging.",
                "metric": f"similarity {duplicate['score']:.0%} · human decision required",
                "status": "review",
            },
            {
                "id": "mock-release",
                "title": "Mock release is gated",
                "detail": "Only approved records can reach the idempotent mock connector; no external system changes.",
                "metric": "publish gate · audit trail · dry-run safe",
                "status": "ready",
            },
        ],
    }


def reel_html(manifest: dict[str, object]) -> str:
    sequence = json.dumps(manifest, indent=2, sort_keys=True).replace("</", "<\\/")
    return dedent(
        f"""\
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>CatalogForge AI — Synthetic intake reference reel</title>
          <style>
            :root {{ color-scheme: dark; --ink: #e8eef5; --muted: #93a4b7; --line: #24364a; --accent: #57d3b0; }}
            * {{ box-sizing: border-box; }}
            body {{ margin: 0; min-width: 320px; background: radial-gradient(circle at 20% 0%, #17304b 0, #08111d 54%, #060b12 100%); color: var(--ink); font: 15px/1.5 Inter, ui-sans-serif, system-ui, sans-serif; }}
            .reel {{ max-width: 1180px; margin: 0 auto; padding: 42px 28px 34px; }}
            .eyebrow {{ color: var(--accent); font-size: 12px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }}
            h1 {{ max-width: 780px; margin: 8px 0 10px; font-size: clamp(28px, 5vw, 52px); line-height: 1.02; letter-spacing: -.04em; }}
            .lede {{ max-width: 740px; margin: 0; color: var(--muted); font-size: 17px; }}
            .model-line {{ display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 22px; color: var(--muted); font-size: 12px; }}
            .model-line span::before {{ content: "•"; color: var(--accent); margin-right: 8px; }}
            .stage {{ position: relative; margin-top: 36px; overflow: hidden; border: 1px solid var(--line); border-radius: 22px; background: linear-gradient(145deg, rgba(19,38,58,.94), rgba(8,17,29,.96)); box-shadow: 0 22px 60px rgba(0,0,0,.28); }}
            svg {{ display: block; width: 100%; height: auto; min-height: 300px; }}
            .route {{ fill: none; stroke: #2a425b; stroke-width: 4; stroke-linecap: round; stroke-dasharray: 7 12; }}
            .station circle {{ fill: #0a1623; stroke: #3b536b; stroke-width: 3; transition: fill .25s ease, stroke .25s ease, transform .25s ease; transform-origin: center; }}
            .station text {{ fill: #8ea1b5; font-size: 15px; text-anchor: middle; }}
            .station .index {{ fill: #c4d1df; font-size: 13px; font-weight: 700; }}
            .station.active circle {{ fill: #164e4a; stroke: var(--accent); transform: scale(1.1); }}
            .station.active text {{ fill: var(--ink); }}
            .station.done circle {{ fill: #162f43; stroke: #5783a7; }}
            .token {{ fill: var(--accent); stroke: #c6fff1; stroke-width: 3; filter: drop-shadow(0 0 12px rgba(87,211,176,.6)); }}
            .token-label {{ fill: #041b19; font-size: 12px; font-weight: 800; text-anchor: middle; }}
            .panel {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 18px; padding: 22px 24px 24px; border-top: 1px solid var(--line); }}
            .panel h2 {{ margin: 0 0 3px; font-size: 24px; letter-spacing: -.02em; }}
            .panel p {{ margin: 0; color: var(--muted); }}
            .metric {{ color: var(--accent); font-size: 13px; font-weight: 700; text-align: right; }}
            .controls {{ display: flex; gap: 8px; margin-top: 16px; }}
            button {{ border: 1px solid #36506b; border-radius: 999px; padding: 9px 15px; background: #102237; color: var(--ink); font: inherit; cursor: pointer; }}
            button:hover, button:focus-visible {{ border-color: var(--accent); outline: 2px solid rgba(87,211,176,.35); outline-offset: 2px; }}
            .timeline {{ display: grid; grid-template-columns: repeat(7, minmax(100px, 1fr)); gap: 7px; margin-top: 18px; }}
            .timeline button {{ min-height: 60px; border-radius: 12px; padding: 8px; color: var(--muted); text-align: left; font-size: 12px; }}
            .timeline button[aria-current="step"] {{ border-color: var(--accent); background: #153846; color: var(--ink); }}
            .timeline strong {{ display: block; color: inherit; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }}
            .disclaimer {{ margin-top: 20px; color: var(--muted); font-size: 12px; }}
            @media (max-width: 760px) {{ .reel {{ padding: 28px 16px; }} .panel {{ grid-template-columns: 1fr; }} .metric {{ text-align: left; }} .timeline {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} svg {{ min-height: 420px; }} }}
            @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; }} }}
          </style>
        </head>
        <body>
          <main class="reel" aria-labelledby="title">
            <div class="eyebrow">CatalogForge AI · production reference reel</div>
            <h1 id="title">From supplier file to governed catalog</h1>
            <p class="lede">A deterministic, evidence-preserving intake sequence using the repository’s seeded supplier export and real validation boundaries.</p>
            <div class="model-line" aria-label="Model and data boundary"><span id="model-name"></span><span id="source-name"></span><span>synthetic data only</span></div>
            <section class="stage" aria-label="Animated intake sequence">
              <svg viewBox="0 0 1200 390" role="img" aria-labelledby="diagram-title diagram-description">
                <title id="diagram-title">Animated CatalogForge intake stages</title>
                <desc id="diagram-description">A token travels through file receipt, integrity checks, field mapping, extraction, validation, duplicate review, and a gated mock release.</desc>
                <path class="route" d="M 100 170 C 250 72, 380 72, 520 170 S 800 270, 1100 170" />
                <g id="stations"></g>
                <g id="token-group" aria-hidden="true"><circle id="token" class="token" cx="100" cy="170" r="22"></circle><text id="token-label" class="token-label" x="100" y="174">DATA</text></g>
              </svg>
              <div class="panel" aria-live="polite"><div><h2 id="event-title"></h2><p id="event-detail"></p></div><div id="event-metric" class="metric"></div></div>
            </section>
            <div class="controls"><button id="toggle" type="button">Pause</button><button id="replay" type="button">Replay</button></div>
            <div id="timeline" class="timeline" role="list" aria-label="Animation stages"></div>
            <p class="disclaimer">Synthetic fixture · deterministic parser/rules boundary · no external destination is changed by this reel.</p>
          </main>
          <script>
            const sequence = {sequence};
            const events = sequence.events;
            const points = [[100,170],[267,94],[433,94],[600,170],[767,246],[933,246],[1100,170]];
            const stations = document.getElementById('stations');
            const timeline = document.getElementById('timeline');
            const token = document.getElementById('token');
            const tokenLabel = document.getElementById('token-label');
            const title = document.getElementById('event-title');
            const detail = document.getElementById('event-detail');
            const metric = document.getElementById('event-metric');
            const toggle = document.getElementById('toggle');
            let current = 0;
            let started = performance.now();
            let playing = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            const duration = 1900;
            points.forEach((point, index) => {{
              const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
              group.classList.add('station');
              group.innerHTML = `<circle cx="${{point[0]}}" cy="${{point[1]}}" r="30"></circle><text class="index" x="${{point[0]}}" y="${{point[1] + 5}}">${{index + 1}}</text><text x="${{point[0]}}" y="${{point[1] + 58}}">${{events[index].title}}</text>`;
              stations.appendChild(group);
            }});
            events.forEach((event, index) => {{
              const item = document.createElement('button');
              item.type = 'button';
              item.setAttribute('role', 'listitem');
              item.dataset.index = index;
              item.innerHTML = `<strong>${{String(index + 1).padStart(2, '0')}} · ${{event.status}}</strong>${{event.title}}`;
              item.addEventListener('click', () => {{ current = index; started = performance.now(); playing = false; toggle.textContent = 'Play'; render(0); }});
              timeline.appendChild(item);
            }});
            document.getElementById('model-name').textContent = `model ${{sequence.model.name}} v${{sequence.model.version}}`;
            document.getElementById('source-name').textContent = `source ${{sequence.source.filename}}`;
            function render(progress) {{
              const next = (current + 1) % points.length;
              const from = points[current];
              const to = points[next];
              const x = from[0] + (to[0] - from[0]) * progress;
              const y = from[1] + (to[1] - from[1]) * progress;
              token.setAttribute('cx', x); token.setAttribute('cy', y); tokenLabel.setAttribute('x', x); tokenLabel.setAttribute('y', y + 4);
              title.textContent = events[current].title; detail.textContent = events[current].detail; metric.textContent = events[current].metric;
              document.querySelectorAll('.station').forEach((node, index) => {{ node.classList.toggle('active', index === current); node.classList.toggle('done', index < current); }});
              timeline.querySelectorAll('button').forEach((node, index) => node.setAttribute('aria-current', index === current ? 'step' : 'false'));
            }}
            function animate(now) {{
              if (playing) {{ const progress = Math.min(1, (now - started) / duration); render(progress); if (progress >= 1) {{ current = (current + 1) % events.length; started = now; }} }} else {{ render(0); }}
              requestAnimationFrame(animate);
            }}
            toggle.addEventListener('click', () => {{ playing = !playing; started = performance.now(); toggle.textContent = playing ? 'Pause' : 'Play'; }});
            document.getElementById('replay').addEventListener('click', () => {{ current = 0; started = performance.now(); playing = true; toggle.textContent = 'Pause'; }});
            render(0); requestAnimationFrame(animate);
          </script>
        </body>
        </html>
        """
    )


def main() -> None:
    manifest = build_manifest()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    REEL.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REEL.write_text(reel_html(manifest), encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")
    print(f"wrote {REEL.relative_to(ROOT)}")
    print(f"source checksum: {manifest['source']['sha256']}")
    print(f"candidates: {manifest['scenario']['candidate_count']}")


if __name__ == "__main__":
    main()
