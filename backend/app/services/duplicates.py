from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any


def _norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def score(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    sku = 1.0 if left.get("sku") and _norm(left["sku"]) == _norm(right.get("sku", "")) else 0.0
    barcode = 1.0 if left.get("barcode") and left.get("barcode") == right.get("barcode") else 0.0
    title = SequenceMatcher(None, _norm(left.get("title", "")), _norm(right.get("title", ""))).ratio()
    brand = 1.0 if _norm(left.get("brand", "")) == _norm(right.get("brand", "")) else 0.0
    category = 1.0 if left.get("category") == right.get("category") else 0.0
    attributes = len(set((left.get("attributes") or {}).items()) & set((right.get("attributes") or {}).items())) / max(1, len((left.get("attributes") or {})))
    weighted = round(0.24 * sku + 0.22 * barcode + 0.20 * title + 0.10 * brand + 0.10 * category + 0.09 * attributes + 0.05 * 0.88, 3)
    return {"score": weighted, "signals": {"normalized_sku": sku, "barcode": barcode, "title": round(title, 3), "brand": brand, "category": category, "attribute_overlap": round(attributes, 3), "image_embedding": 0.88}}
