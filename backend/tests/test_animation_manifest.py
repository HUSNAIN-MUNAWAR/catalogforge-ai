from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "animation" / "catalogforge_intake_sequence.json"
REEL = ROOT / "frontend" / "public" / "animation" / "catalogforge-intake-reel.html"


def test_animation_generator_reproduces_manifest_and_reel() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_animation_sequence.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "candidates:" in result.stdout

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    reel = REEL.read_text(encoding="utf-8")
    assert manifest["model"]["name"] == "catalogforge-deterministic-extraction"
    assert manifest["source"]["sha256"]
    assert manifest["scenario"]["candidate_count"] == 12
    assert len(manifest["events"]) == 7
    assert "prefers-reduced-motion" in reel
    assert "synthetic fixture" in reel.lower()
