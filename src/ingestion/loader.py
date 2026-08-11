"""Robust multi-file ingestion loader with origin tagging and OCR-fail flagging.

Wraps the deterministic parsers in pdf_parser with a structured result so callers
(and tests) can distinguish:
  - a clean extraction (status='ok', lines populated),
  - a PDF that has pages but NO extractable text layer, i.e. scanned/image-only
    (status='ocr_required' — flagged 'could not extract text', never silently
    dropped; a real OCR backend would slot in here),
  - a corrupted / unreadable file (status='error' with a clear message; no
    partial or garbage input is passed downstream).

Each result is tagged with its origin filename and a derived source_type so a
batch of mixed files stays attributable per the framework's multi-file rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .pdf_parser import parse_email, parse_pdf


@dataclass
class IngestResult:
    origin: str                 # filename (basename) the notes came from
    source_type: str            # 'pdf_coverage' | 'producer_email' | 'agent_email' | 'unknown'
    status: str                 # 'ok' | 'ocr_required' | 'error'
    lines: list[str] = field(default_factory=list)
    message: str = ""           # human-readable status/error detail

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _derive_source_type(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf_coverage"
    if "manager" in name or "agent" in name:
        return "agent_email"
    if suffix in (".eml", ".txt"):
        return "producer_email"
    return "unknown"


def _pdf_has_pages_but_no_text(path: Path) -> bool:
    """True when the PDF opens and has >=1 page but yields no extractable text.

    This is the scanned/image-only case: pdfplumber returns pages but every
    page's extract_text() is empty. We must FLAG this, not return [] silently.
    """
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        if not pdf.pages:
            return False
        for page in pdf.pages:
            if (page.extract_text() or "").strip():
                return False  # some text found -> not image-only
    return True


def ingest(path: str | Path) -> IngestResult:
    """Ingest a single feedback file into a structured, origin-tagged result."""
    p = Path(path)
    origin = p.name
    source_type = _derive_source_type(p)

    if not p.exists():
        return IngestResult(origin, source_type, "error", message=f"File not found: {p}")

    suffix = p.suffix.lower()
    try:
        if suffix == ".pdf":
            lines = parse_pdf(str(p))
            if not lines:
                # Distinguish scanned/image-only (has pages, no text) from truly broken.
                try:
                    if _pdf_has_pages_but_no_text(p):
                        return IngestResult(
                            origin, source_type, "ocr_required", lines=[],
                            message="Could not extract text: PDF appears scanned/image-only. "
                                    "OCR required — not silently dropped.",
                        )
                except Exception as exc:  # noqa: BLE001 — reopen failed => corrupted
                    return IngestResult(
                        origin, source_type, "error",
                        message=f"Corrupted or unreadable PDF: {type(exc).__name__}: {exc}",
                    )
                # Opened, has no pages / genuinely empty content.
                return IngestResult(
                    origin, source_type, "ocr_required", lines=[],
                    message="Could not extract text from PDF (empty text layer).",
                )
            return IngestResult(origin, source_type, "ok", lines=lines,
                                message=f"Extracted {len(lines)} note lines.")
        else:
            lines = parse_email(p)
            if not lines:
                return IngestResult(origin, source_type, "error",
                                    message="No note lines found in email/text file.")
            return IngestResult(origin, source_type, "ok", lines=lines,
                                message=f"Extracted {len(lines)} note lines.")
    except Exception as exc:  # noqa: BLE001 — any parser failure => clear error, no partial data
        return IngestResult(
            origin, source_type, "error",
            message=f"Failed to parse {origin}: {type(exc).__name__}: {exc}",
        )


def ingest_many(paths: list[str | Path]) -> list[IngestResult]:
    """Ingest a batch of files; each result carries its own origin + status.

    A failure on one file NEVER aborts the batch or contaminates another file's
    lines — corrupted input is isolated to its own error result.
    """
    return [ingest(p) for p in paths]
