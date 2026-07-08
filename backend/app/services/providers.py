from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class OCRTextBlock:
    text: str
    page: int
    bbox: dict[str, int]
    confidence: float


class OCRProvider(Protocol):
    name: str

    def extract(self, path: Path) -> list[OCRTextBlock]: ...


class StructuredExtractionProvider(Protocol):
    name: str

    def extract_products(self, text_blocks: list[OCRTextBlock]) -> list[dict[str, object]]: ...


class DeterministicOCRProvider:
    name = "deterministic_local"

    def extract(self, path: Path) -> list[OCRTextBlock]:
        return [
            OCRTextBlock(
                text=f"SYNTHETIC source evidence from {path.name}",
                page=1,
                bbox={"x": 48, "y": 72, "w": 480, "h": 22},
                confidence=0.98,
            )
        ]


class TesseractOCRAdapter:
    name = "tesseract"

    def extract(self, path: Path) -> list[OCRTextBlock]:
        raise NotImplementedError("Install pytesseract and implement the provider in deployment.")


class EasyOCRAdapter:
    name = "easyocr"

    def extract(self, path: Path) -> list[OCRTextBlock]:
        raise NotImplementedError("Install easyocr and implement the provider in deployment.")


class CloudDocumentAIAdapter:
    name = "cloud_document_ai"

    def extract(self, path: Path) -> list[OCRTextBlock]:
        raise NotImplementedError("Configure a cloud Document AI provider in deployment.")


class OpenAICompatibleStructuredExtractor:
    name = "openai_compatible"

    def extract_products(self, text_blocks: list[OCRTextBlock]) -> list[dict[str, object]]:
        raise NotImplementedError("Configure an OpenAI-compatible client and schema-constrained output.")
