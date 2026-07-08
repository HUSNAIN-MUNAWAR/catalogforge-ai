from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .intake import IntakeValidationError, preview_rows


@dataclass
class ExtractedCandidate:
    title: str
    sku: str
    brand: str
    category: str
    price: float
    inventory: int
    barcode: str
    confidence: float
    attributes: dict[str, Any]
    evidence: dict[str, Any]


def normalize_sku(raw: str) -> str:
    return "-".join("".join(ch for ch in raw.upper().strip() if ch.isalnum() or ch in " -_").replace("_", "-").split())


def _to_float(value: object, fallback: float = 24.0) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return fallback


def _to_int(value: object, fallback: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback


def _mapped_value(row: dict[str, Any], field_map: dict[str, str], field: str, default: object = "") -> object:
    return row.get(field_map.get(field, field), default)


def deterministic_extract(file_path: Path, vendor_name: str, mapping: dict[str, str] | None = None) -> list[ExtractedCandidate]:
    """Deterministic no-key parser for CSV/XLSX/JSON/PDF text; fallback rows keep the demo runnable."""
    mapping = mapping or {}
    items: list[ExtractedCandidate] = []
    extension = file_path.suffix.lower()
    try:
        _, rows, inferred_mapping = preview_rows(file_path, max_rows=250)
        field_map = {**inferred_mapping, **mapping}
    except (IntakeValidationError, UnicodeDecodeError, json.JSONDecodeError):
        rows, field_map = [], {}

    for index, row in enumerate(rows):
        if "source_text" in row:
            continue
        title = str(_mapped_value(row, field_map, "title") or f"{vendor_name} Catalog Item {index + 1}")
        raw_sku = str(_mapped_value(row, field_map, "sku") or f"{vendor_name[:3]}-{index + 1:04d}")
        sku = normalize_sku(raw_sku)
        price = _to_float(_mapped_value(row, field_map, "price"), 24.0)
        inventory = _to_int(_mapped_value(row, field_map, "inventory"), 0)
        attributes = {
            "material": str(_mapped_value(row, field_map, "material") or "Unspecified"),
            "color": str(_mapped_value(row, field_map, "color") or "Unspecified"),
            "weight": str(_mapped_value(row, field_map, "weight") or ""),
            "dimensions": str(_mapped_value(row, field_map, "dimensions") or ""),
        }
        items.append(
            ExtractedCandidate(
                title=title,
                sku=sku,
                brand=str(_mapped_value(row, field_map, "brand") or vendor_name),
                category=str(_mapped_value(row, field_map, "category") or "Home / Storage"),
                price=price,
                inventory=inventory,
                barcode=str(_mapped_value(row, field_map, "barcode") or ""),
                confidence=0.95 if extension in {".csv", ".xlsx", ".xls", ".json"} else 0.82,
                attributes=attributes,
                evidence={
                    "page": 1,
                    "sheet": "Catalog" if extension in {".xlsx", ".xls"} else None,
                    "row": index + 2,
                    "bbox": {"x": 72, "y": 150 + index * 24, "w": 440, "h": 18},
                    "source_text": title,
                },
            )
        )
    if not items:
        for index in range(6):
            title = f"{vendor_name} {['Woven Storage Basket', 'Linen Table Runner', 'Ceramic Pouring Bowl', 'Oak Serving Board', 'Glass Pantry Jar', 'Cotton Napkin Set'][index]}"
            items.append(
                ExtractedCandidate(
                    title=title,
                    sku=normalize_sku(f"{vendor_name[:3]} {index + 101}" if index != 2 else ""),
                    brand=vendor_name,
                    category=["Home / Storage", "Home / Table Linen", "Kitchen / Serveware", "Kitchen / Boards", "Kitchen / Storage", "Home / Table Linen"][index],
                    price=[32.0, 18.0, 420.0, 46.0, 16.0, 24.0][index],
                    inventory=[48, 80, 2, 24, 120, 96][index],
                    barcode=f"8901010203{index:02d}",
                    confidence=[0.96, 0.93, 0.72, 0.95, 0.91, 0.89][index],
                    attributes={"material": ["Seagrass", "Linen", "Ceramic", "Oak", "Borosilicate glass", "Cotton"][index], "color": "Natural", "weight": "", "dimensions": ""},
                    evidence={"page": 1 + index // 3, "bbox": {"x": 76, "y": 138 + index * 56, "w": 430, "h": 36}, "source_text": title},
                )
            )
    return items


def checksum(path: Path) -> str:
    return sha256(path.read_bytes() if path.exists() else str(path).encode()).hexdigest()


def run_validations(candidate: ExtractedCandidate, destination: str | None = None) -> list[dict[str, str | bool]]:
    results: list[dict[str, str | bool]] = []
    if not candidate.sku:
        results.append({"rule": "SKU required", "severity": "error", "message": "SKU is required before approval.", "blocking": True, "remediation": "Set a normalized SKU or request vendor clarification."})
    if candidate.price <= 0:
        results.append({"rule": "Price must be positive", "severity": "error", "message": "Price must be greater than zero.", "blocking": True, "remediation": "Confirm vendor retail price."})
    if candidate.price > 250:
        results.append({"rule": "Price anomaly", "severity": "warning", "message": f"Price ${candidate.price:.2f} is above the deterministic vendor review range.", "blocking": False, "remediation": "Confirm price against source or vendor median."})
    if candidate.inventory < 0:
        results.append({"rule": "Inventory invalid", "severity": "error", "message": "Inventory cannot be negative.", "blocking": True, "remediation": "Correct inventory quantity."})
    if len(candidate.title.strip()) < 12:
        results.append({"rule": "Title quality", "severity": "error", "message": "Product title must be at least 12 characters.", "blocking": True, "remediation": "Provide an informative title."})
    if destination and destination.lower().startswith("shopify"):
        if not candidate.attributes.get("weight"):
            results.append({"rule": "Shopify shipping weight", "severity": "error", "message": "Shipping weight is required for Shopify readiness.", "blocking": True, "remediation": "Set product shipping weight."})
        if not candidate.category:
            results.append({"rule": "Shopify product type", "severity": "error", "message": "Product type/category mapping is required for Shopify readiness.", "blocking": True, "remediation": "Map the product to a channel category."})
    return results


def completeness_score(candidate: ExtractedCandidate, unresolved_duplicate: bool = False, destination: str | None = None) -> float:
    checks = [bool(candidate.title), bool(candidate.sku), bool(candidate.category), candidate.price > 0, bool(candidate.attributes.get("weight")), bool(candidate.attributes.get("dimensions"))]
    if destination and destination.lower().startswith("shopify"):
        checks.append(bool(candidate.attributes.get("weight")))
    if unresolved_duplicate:
        checks.append(False)
    return round(sum(1 for value in checks if value) / max(1, len(checks)) * 100, 1)
