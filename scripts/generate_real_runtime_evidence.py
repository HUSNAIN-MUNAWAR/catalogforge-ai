"""Capture a real CatalogForge parser run as an inspectable MP4 and report.

The repository's local path is deterministic extraction and rules, not a
learned model. This runner makes that boundary explicit while preserving the
actual source checksum, every extracted candidate, every validation result,
and the duplicate-scoring output that drive the animation.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.duplicates import score as duplicate_score  # noqa: E402
from app.services.intake import inspect_file, preview_rows  # noqa: E402
from app.services.pipeline import (  # noqa: E402
    completeness_score,
    deterministic_extract,
    run_validations,
)


SOURCE = ROOT / "demo_data" / "source_documents" / "Synthetic_vendor_export_01.csv"
OUTPUT_ROOT = ROOT / "docs" / "animation" / "runtime-evidence"
VIDEO_PATH = OUTPUT_ROOT / "catalogforge-runtime.mp4"
POSTER_PATH = OUTPUT_ROOT / "catalogforge-runtime-poster.png"
CANDIDATES_PATH = OUTPUT_ROOT / "catalogforge-candidates.csv"
SUMMARY_PATH = OUTPUT_ROOT / "catalogforge-runtime-summary.json"
FRAMES_PER_EVENT = 5
FPS = 5


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_record(candidate: object) -> dict[str, object]:
    validations = run_validations(candidate, "Shopify mock")
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
        "evidence": candidate.evidence,
        "validations": validations,
        "blocking_validation_count": sum(1 for item in validations if item["blocking"]),
        "completeness_score": completeness_score(candidate, destination="Shopify"),
    }


def build_run() -> dict[str, object]:
    inspection = inspect_file(SOURCE)
    columns, rows, mapping = preview_rows(SOURCE, max_rows=250)
    candidates = deterministic_extract(SOURCE, "Northern Atelier")
    records = [candidate_record(candidate) for candidate in candidates]
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
    validation_count = sum(len(record["validations"]) for record in records)
    blocking_count = sum(record["blocking_validation_count"] for record in records)
    events = [
        {
            "id": "source-received",
            "title": "Supplier file received",
            "detail": f"{SOURCE.name} entered the local intake boundary.",
            "metric": f"{inspection.source_type} / {inspection.size} bytes",
        },
        {
            "id": "integrity-checked",
            "title": "Integrity checked",
            "detail": "The executed intake inspection recorded the MIME type and SHA-256.",
            "metric": f"sha256 {inspection.checksum[:16]}",
        },
        {
            "id": "mapping-inferred",
            "title": "Columns mapped",
            "detail": "The actual parser inferred canonical product fields from the CSV header.",
            "metric": f"{len(mapping)} of {len(columns)} columns mapped",
        },
        {
            "id": "candidates-extracted",
            "title": "Candidates extracted",
            "detail": "deterministic_extract returned the candidate records preserved in the CSV.",
            "metric": f"{len(records)} candidates / {sum(record['confidence'] for record in records) / len(records):.0%} mean confidence",
        },
        {
            "id": "rules-evaluated",
            "title": "Rules evaluated",
            "detail": "The real validation function ran against every extracted candidate.",
            "metric": f"{validation_count} findings / {blocking_count} blocking",
        },
        {
            "id": "duplicate-scored",
            "title": "Duplicate candidate scored",
            "detail": "The repository duplicate scorer compared an actual candidate with a derived review pair.",
            "metric": f"similarity {duplicate['score']:.1%} / human review",
        },
        {
            "id": "mock-release-gated",
            "title": "Mock release gated",
            "detail": "The local destination is a mock connector; no external system was changed.",
            "metric": "Shopify mock / external keys false",
        },
    ]
    return {
        "source": {
            "path": str(SOURCE.relative_to(ROOT)),
            "filename": SOURCE.name,
            "type": inspection.source_type,
            "mime_type": inspection.mime_type,
            "bytes": inspection.size,
            "sha256": inspection.checksum,
            "rows": len(rows),
            "columns": columns,
            "mapping": mapping,
        },
        "algorithm": {
            "extraction": "backend/app/services/pipeline.py::deterministic_extract",
            "validation": "backend/app/services/pipeline.py::run_validations",
            "duplicate_scoring": "backend/app/services/duplicates.py::score",
            "learned_model": None,
            "checkpoint": None,
            "external_keys_used": False,
            "duplicate_signal_note": "The duplicate scorer's image_embedding value is a fixed synthetic abstraction; no embedding model executed.",
            "claim_boundary": "Deterministic parser and rules over synthetic demo data; not a learned-model accuracy benchmark.",
        },
        "runtime": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "device": "cpu",
        },
        "candidates": records,
        "scenario": {
            "vendor": "Northern Atelier",
            "destination": "Shopify mock",
            "candidate_count": len(records),
            "validation_finding_count": validation_count,
            "blocking_validation_count": blocking_count,
            "all_candidates_pass_validation": all(not record["validations"] for record in records),
            "duplicate": duplicate,
        },
        "events": events,
    }


def display(text: object) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def put_text(canvas: np.ndarray, text: str, x: int, y: int, scale: float = 0.58, color: tuple[int, int, int] = (220, 232, 236), thickness: int = 1) -> None:
    cv2.putText(canvas, display(text), (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def evidence_lines(run: dict[str, object], event_index: int) -> list[str]:
    source = run["source"]
    scenario = run["scenario"]
    candidates = run["candidates"]
    mapping = source["mapping"]
    if event_index == 0:
        return [f"file: {source['filename']}", f"type: {source['type']}", f"rows: {source['rows']}", f"bytes: {source['bytes']}"]
    if event_index == 1:
        return [f"mime: {source['mime_type']}", f"sha256: {source['sha256'][:28]}...", "checksum is from the actual input file"]
    if event_index == 2:
        return [f"{key} <- {value}" for key, value in list(mapping.items())[:8]]
    if event_index == 3:
        return [f"{idx + 1:02d}  {item['sku']:<10} {str(item['title'])[:32]}  conf {item['confidence']:.2f}" for idx, item in enumerate(candidates[:8])]
    if event_index == 4:
        findings = [item for candidate in candidates for item in candidate["validations"]]
        lines = [f"all candidates pass: {scenario['all_candidates_pass_validation']}", f"findings: {scenario['validation_finding_count']}", f"blocking: {scenario['blocking_validation_count']}"]
        lines.extend(f"{item['rule']}: {item['severity']}" for item in findings[:4])
        return lines
    if event_index == 5:
        duplicate = scenario["duplicate"]
        return [f"score: {duplicate['score']:.3f}", "signals from executed scorer:", *[f"{key}: {value:.2f}" for key, value in duplicate["signals"].items() if key != "image_embedding"], "image_embedding: fixed 0.88 abstraction", "no embedding model executed"]
    return ["destination: Shopify mock", "external keys: false", "publish gate: local only", "no external system changed"]


def render_frame(run: dict[str, object], event_index: int, frame_number: int, frame_count: int) -> np.ndarray:
    canvas = np.full((720, 1280, 3), (7, 16, 28), dtype=np.uint8)
    event = run["events"][event_index]
    put_text(canvas, "CatalogForge AI - REAL LOCAL RUNTIME", 40, 48, 0.98, (235, 242, 246), 2)
    put_text(canvas, f"event {event_index + 1}/7  |  frame {frame_number}/{frame_count}", 40, 80, 0.56, (143, 163, 180))
    cv2.rectangle(canvas, (34, 108), (820, 660), (31, 53, 73), 2)
    cv2.rectangle(canvas, (852, 108), (1240, 660), (31, 53, 73), 2)
    put_text(canvas, event["title"], 60, 158, 0.82, (91, 218, 177), 2)
    put_text(canvas, event["detail"], 60, 194, 0.52, (210, 222, 230))
    put_text(canvas, f"executed metric: {event['metric']}", 60, 226, 0.58, (91, 218, 177), 1)
    for index, line in enumerate(evidence_lines(run, event_index)):
        put_text(canvas, line, 66, 280 + index * 34, 0.58, (221, 231, 235))

    algorithm = run["algorithm"]
    scenario = run["scenario"]
    panel = [
        "EXECUTED PATH",
        "deterministic parser + rules",
        f"learned model: {algorithm['learned_model']}",
        f"checkpoint: {algorithm['checkpoint']}",
        "",
        "INPUT CONTRACT",
        f"synthetic source: {str(run['source']['filename'])[:16]}...",
        f"rows processed: {run['source']['rows']}",
        f"candidates: {scenario['candidate_count']}",
        "",
        "CLAIM BOUNDARY",
        "No accuracy claim is made.",
        "No live connector was called.",
        "Values shown come from this run.",
    ]
    for index, line in enumerate(panel):
        put_text(canvas, line, 882, 158 + index * 31, 0.56 if index not in {0, 5, 10} else 0.62, (220, 232, 236) if index not in {0, 5, 10} else (91, 218, 177), 1 if index not in {0, 5, 10} else 2)
    put_text(canvas, "synthetic demo input | local execution trace | no fabricated metrics", 40, 695, 0.52, (143, 163, 180))
    return canvas


def main() -> None:
    run = build_run()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(VIDEO_PATH), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (1280, 720))
    if not writer.isOpened():
        raise RuntimeError(f"unable to open video writer for {VIDEO_PATH}")
    first_frame: np.ndarray | None = None
    frame_count = len(run["events"]) * FRAMES_PER_EVENT
    frame_number = 0
    try:
        for event_index in range(len(run["events"])):
            for _ in range(FRAMES_PER_EVENT):
                frame_number += 1
                frame = render_frame(run, event_index, frame_number, frame_count)
                first_frame = first_frame if first_frame is not None else frame.copy()
                writer.write(frame)
    finally:
        writer.release()
    if first_frame is None:
        raise RuntimeError("no runtime frames were produced")
    cv2.imwrite(str(POSTER_PATH), first_frame)

    candidate_fields = ["index", "title", "sku", "brand", "category", "price", "inventory", "barcode", "confidence", "blocking_validation_count", "completeness_score", "source_row"]
    with CANDIDATES_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer_csv = csv.DictWriter(handle, fieldnames=candidate_fields)
        writer_csv.writeheader()
        for index, candidate in enumerate(run["candidates"], start=1):
            writer_csv.writerow({
                "index": index,
                "title": candidate["title"],
                "sku": candidate["sku"],
                "brand": candidate["brand"],
                "category": candidate["category"],
                "price": candidate["price"],
                "inventory": candidate["inventory"],
                "barcode": candidate["barcode"],
                "confidence": candidate["confidence"],
                "blocking_validation_count": candidate["blocking_validation_count"],
                "completeness_score": candidate["completeness_score"],
                "source_row": candidate["evidence"]["row"],
            })

    report = {
        "run_type": "catalogforge_real_local_runtime_video",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": "py -3.12 -u scripts/generate_real_runtime_evidence.py",
        **run,
        "outputs": {
            "video": str(VIDEO_PATH.relative_to(ROOT)),
            "poster": str(POSTER_PATH.relative_to(ROOT)),
            "candidates_csv": str(CANDIDATES_PATH.relative_to(ROOT)),
            "sha256": {
                str(path.relative_to(ROOT)): file_sha256(path)
                for path in (VIDEO_PATH, POSTER_PATH, CANDIDATES_PATH)
            },
        },
        "interpretation": [
            "The video is generated from one local execution of the repository parser, validators, and duplicate scorer.",
            "The input fixture is synthetic by repository design; it is not real customer data.",
            "There is no learned model or checkpoint in this local path, so confidence values are parser outputs, not model accuracy.",
            "The duplicate scorer reports a fixed synthetic image_embedding abstraction; no embedding model executed.",
            "The older HTML reel is retained as a legacy synthetic presentation and is not counted as runtime evidence.",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"video": str(VIDEO_PATH), "poster": str(POSTER_PATH), "summary": str(SUMMARY_PATH), "candidates": len(run["candidates"])}, indent=2))


if __name__ == "__main__":
    main()
