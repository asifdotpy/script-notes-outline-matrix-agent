"""Ingest external, unstructured feedback documents.

Two real sources per the locked idea:
  - PDF coverage / script reports (producers, coverage services, Black List evals)
  - Emails from producers / agents (.eml or raw text) with notes scattered in prose

Parsing is layout-light on purpose: we extract raw note lines/paragraphs and let
the Gemini agent categorize them (note_type / character / scene_ref / severity).
This keeps the agent's reasoning load-bearing while the ingestion is deterministic.
"""
from __future__ import annotations

import re
from pathlib import Path


def parse_pdf(path: str | Path) -> list[str]:
    """Extract text blocks from a PDF coverage/notes file."""
    import pdfplumber

    blocks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if line:
                    blocks.append(line)
    return _clean(blocks)


def parse_email(path: str | Path) -> list[str]:
    """Extract the body text from a .eml or .txt producer/agent email into note lines."""
    raw = Path(path).read_text(errors="ignore")
    body = _strip_email_headers(raw)
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return _clean(lines)


def _strip_email_headers(raw: str) -> str:
    # Minimal: drop everything before the first blank line (headers), keep body.
    if "\n\n" in raw:
        return raw.split("\n\n", 1)[1]
    return raw


def _clean(lines: list[str]) -> list[str]:
    """Drop pure pagination/boilerplate, keep candidate note lines."""
    out: list[str] = []
    junk = re.compile(r"^(page\s*\d+|^\s*\d+\s*$)", re.I)
    for ln in lines:
        if len(ln) < 3:
            continue
        if junk.match(ln):
            continue
        out.append(ln)
    return out
