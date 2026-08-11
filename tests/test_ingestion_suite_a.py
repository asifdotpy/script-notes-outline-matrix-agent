"""Suite A — Ingestion tests (board task t_b89d9889).

Asserts the framework table's ingestion contract against the golden dataset:
  A1. Clean PDF -> full text extracted.
  A2. Scanned/image-only PDF -> either OCRs or FLAGS 'could not extract';
      never silently dropped.
  A3. Plain-text/.eml email -> parsed into the same note-line shape as PDF.
  A4. Multiple files ingested in one batch and tagged by origin.
  A5. Corrupted file -> clear error; no partial/garbage input proceeds downstream.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.loader import ingest, ingest_many  # noqa: E402
from src.ingestion.pdf_parser import parse_email, parse_pdf  # noqa: E402

G = ROOT / "tests" / "fixtures" / "golden"
CLEAN_PDF = G / "coverage_report.pdf"
SCANNED_PDF = G / "coverage_scanned.pdf"
CORRUPTED_PDF = G / "feedback_corrupted.pdf"
PRODUCER_EML = G / "producer_email.eml"
MANAGER_EML = G / "manager_email.eml"


# --- A1: clean PDF full-text extraction -------------------------------------
def test_a1_clean_pdf_extracts_full_text():
    res = ingest(CLEAN_PDF)
    assert res.ok, f"clean PDF should ingest OK, got {res.status}: {res.message}"
    assert res.source_type == "pdf_coverage"
    assert len(res.lines) >= 15, "expected the full coverage report, not a fragment"
    joined = " ".join(res.lines).lower()
    # Key content from every section of the report must survive extraction.
    assert "coverage report" in joined
    assert "dinner scene" in joined          # STRENGTHS
    assert "opening (scene 1) is too slow" in joined  # WEAKNESSES
    assert "on the nose" in joined           # POLISH


def test_a1_parse_pdf_and_loader_agree():
    """The loader must not alter the deterministic parser's output."""
    assert ingest(CLEAN_PDF).lines == parse_pdf(str(CLEAN_PDF))


# --- A2: scanned / image-only PDF must be FLAGGED, never silently dropped ----
def test_a2_scanned_pdf_is_flagged_not_silently_dropped():
    res = ingest(SCANNED_PDF)
    # Either it OCR'd (ok + lines) or it flagged the failure — never a silent empty ok.
    assert res.status in ("ok", "ocr_required")
    if res.status == "ok":
        assert res.lines, "status ok must mean real extracted text"
    else:
        assert res.lines == [], "flagged extraction must not emit partial text"
        assert "could not extract" in res.message.lower(), \
            f"OCR failure must be explicit, got: {res.message}"
    # The critical guarantee: never a silent success with zero content.
    assert not (res.status == "ok" and not res.lines), \
        "scanned PDF silently dropped — no flag, no content"


def test_a2_raw_parser_alone_would_be_silent_loader_fixes_it():
    """Documents WHY the loader exists: parse_pdf alone returns [] with no signal."""
    raw = parse_pdf(str(SCANNED_PDF))
    assert raw == [], "fixture is image-only, so the raw parser yields nothing"
    # The loader converts that silence into an explicit, actionable flag.
    assert ingest(SCANNED_PDF).status == "ocr_required"


# --- A3: email parsed into the same shape as PDF -----------------------------
def test_a3_email_parsed_like_pdf():
    eml = ingest(PRODUCER_EML)
    pdf = ingest(CLEAN_PDF)
    assert eml.ok and pdf.ok
    # Same shape: list[str] of non-empty note lines.
    assert isinstance(eml.lines, list) and all(isinstance(x, str) for x in eml.lines)
    assert all(x.strip() for x in eml.lines), "no empty/whitespace lines"
    assert type(eml.lines) is type(pdf.lines)
    # Headers stripped, body notes retained.
    joined = " ".join(eml.lines).lower()
    assert "subject:" not in joined, "email headers must be stripped"
    assert "the opening scene is too slow" in joined
    assert "expand the dinner scene" in joined


def test_a3_email_loader_matches_parse_email():
    assert ingest(PRODUCER_EML).lines == parse_email(PRODUCER_EML)


# --- A4: multi-file batch, tagged by origin ---------------------------------
def test_a4_multi_file_ingest_tagged_by_origin():
    results = ingest_many([CLEAN_PDF, PRODUCER_EML, MANAGER_EML])
    assert len(results) == 3
    origins = [r.origin for r in results]
    assert origins == ["coverage_report.pdf", "producer_email.eml", "manager_email.eml"]
    # Each result carries its own source_type; emails are distinguished.
    by_origin = {r.origin: r for r in results}
    assert by_origin["coverage_report.pdf"].source_type == "pdf_coverage"
    assert by_origin["producer_email.eml"].source_type == "producer_email"
    assert by_origin["manager_email.eml"].source_type == "agent_email"
    assert all(r.ok for r in results)
    # No cross-contamination: each file's lines are distinct sets.
    assert by_origin["producer_email.eml"].lines != by_origin["manager_email.eml"].lines


def test_a4_notes_remain_attributable_after_batch():
    """Every ingested line can be traced back to exactly one origin file."""
    results = ingest_many([PRODUCER_EML, MANAGER_EML])
    tagged = [(r.origin, ln) for r in results for ln in r.lines]
    assert tagged, "batch produced no lines"
    for origin, line in tagged:
        assert origin in ("producer_email.eml", "manager_email.eml")
        assert line.strip()


# --- A5: corrupted file -> clear error, no garbage downstream ---------------
def test_a5_corrupted_file_errors_clearly():
    res = ingest(CORRUPTED_PDF)
    assert res.status == "error", "corrupted PDF must not report success"
    assert res.lines == [], "no partial/garbage lines may proceed"
    assert res.message, "error must carry a human-readable reason"
    assert not res.ok


def test_a5_corrupted_file_does_not_abort_the_batch():
    """One bad file must not take down the whole ingestion run."""
    results = ingest_many([CLEAN_PDF, CORRUPTED_PDF, PRODUCER_EML])
    assert len(results) == 3
    statuses = {r.origin: r.status for r in results}
    assert statuses["coverage_report.pdf"] == "ok"
    assert statuses["feedback_corrupted.pdf"] == "error"
    assert statuses["producer_email.eml"] == "ok"
    # The good files still yield their full content.
    good = [r for r in results if r.ok]
    assert sum(len(r.lines) for r in good) >= 30


def test_a5_missing_file_is_an_error_not_a_crash():
    res = ingest(G / "does_not_exist.pdf")
    assert res.status == "error"
    assert "not found" in res.message.lower()
