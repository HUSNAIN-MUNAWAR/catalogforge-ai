from __future__ import annotations

import csv
import json
import mimetypes
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

try:  # Optional local PDF text support; demo has deterministic fallback when absent.
    import fitz
except Exception:  # pragma: no cover
    fitz = None

MAX_FILE_SIZE = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf", ".txt", ".json", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".zip"}


class IntakeValidationError(ValueError):
    pass


@dataclass
class FileInspection:
    mime_type: str
    extension: str
    size: int
    checksum: str
    source_type: str
    duplicate_hint: bool = False


def source_type_from_extension(extension: str) -> str:
    return {
        ".csv": "CSV",
        ".xlsx": "XLSX",
        ".xls": "XLS",
        ".pdf": "PDF catalog",
        ".txt": "Text document",
        ".json": "JSON feed",
        ".zip": "ZIP batch boundary",
        ".png": "Image",
        ".jpg": "Image",
        ".jpeg": "Image",
        ".webp": "Image",
        ".svg": "Image batch",
    }.get(extension.lower(), "Unknown")


def _signature_mime(data: bytes, extension: str) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.lstrip().startswith(b"{") or data.lstrip().startswith(b"["):
        return "application/json"
    if extension == ".csv":
        return "text/csv"
    if extension == ".svg":
        return "image/svg+xml"
    return None


def inspect_file(path: Path) -> FileInspection:
    if not path.exists():
        raise IntakeValidationError("Uploaded file was not persisted.")
    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise IntakeValidationError(f"Unsupported file type '{extension or 'unknown'}'.")
    size = path.stat().st_size
    if size <= 0:
        raise IntakeValidationError("File is empty.")
    if size > MAX_FILE_SIZE:
        raise IntakeValidationError("File exceeds the local demo limit of 25 MB.")
    sample = path.read_bytes()[:4096]
    signature = _signature_mime(sample, extension)
    guessed = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    mime_type = signature or guessed
    # XLSX is a ZIP container; reject renamed text files masquerading as a spreadsheet.
    if extension in {".xlsx", ".xls"} and not sample.startswith(b"PK\x03\x04"):
        raise IntakeValidationError("Spreadsheet MIME verification failed; upload a valid XLSX/XLS file.")
    if extension == ".pdf" and not sample.startswith(b"%PDF"):
        raise IntakeValidationError("PDF MIME verification failed.")
    if extension == ".zip":
        # Phase 2 intentionally leaves archive extraction behind a safe scanning boundary.
        raise IntakeValidationError("ZIP intake is a supported architecture boundary but is disabled in local demo mode for archive safety.")
    return FileInspection(
        mime_type=mime_type,
        extension=extension,
        size=size,
        checksum=sha256(path.read_bytes()).hexdigest(),
        source_type=source_type_from_extension(extension),
    )


def normalize_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def proposed_column_mapping(columns: list[str]) -> dict[str, str]:
    aliases = {
        "title": {"title", "productname", "name", "itemname", "description"},
        "sku": {"sku", "vendorsku", "itemcode", "productcode", "code"},
        "brand": {"brand", "manufacturer", "vendor"},
        "category": {"category", "producttype", "department", "taxonomy"},
        "price": {"price", "msrp", "retail", "sellingprice", "unitprice"},
        "inventory": {"inventory", "stock", "quantity", "qty", "onhand"},
        "barcode": {"barcode", "gtin", "upc", "ean"},
        "material": {"material", "fabric", "composition"},
        "color": {"color", "colour"},
        "weight": {"weight", "shippingweight"},
        "dimensions": {"dimensions", "size", "dimension"},
    }
    mapping: dict[str, str] = {}
    for column in columns:
        normalized = normalize_column(column)
        for target, candidates in aliases.items():
            if normalized in candidates and target not in mapping:
                mapping[target] = column
    return mapping


def preview_rows(path: Path, max_rows: int = 8) -> tuple[list[str], list[dict[str, Any]], dict[str, str]]:
    extension = path.suffix.lower()
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    if extension == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            for row in reader:
                rows.append({str(k): v for k, v in row.items()})
                if len(rows) >= max_rows:
                    break
    elif extension in {".xlsx", ".xls"}:
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        raw = list(sheet.iter_rows(values_only=True))
        if raw:
            columns = [str(x or "").strip() or f"Column {index + 1}" for index, x in enumerate(raw[0])]
            for raw_row in raw[1 : max_rows + 1]:
                rows.append({columns[index]: raw_row[index] if index < len(raw_row) else None for index in range(len(columns))})
    elif extension == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("products") or payload.get("items") or [payload]
        if not isinstance(payload, list):
            raise IntakeValidationError("JSON feed must contain an array or a products/items array.")
        records = [item for item in payload if isinstance(item, dict)]
        columns = sorted({str(key) for item in records for key in item})
        rows = records[:max_rows]
    elif extension == ".pdf":
        text = extract_pdf_text(path)
        columns = ["source_text"]
        rows = [{"source_text": line[:300]} for line in text.splitlines() if line.strip()][:max_rows]
    else:
        columns = ["source_text"]
        rows = [{"source_text": "Local deterministic representation; no structured rows available."}]
    return columns, rows, proposed_column_mapping(columns)


def extract_pdf_text(path: Path) -> str:
    if fitz is None:
        return ""
    try:
        with fitz.open(path) as pdf:
            return "\n".join(page.get_text("text") for page in pdf)
    except Exception:
        return ""
