"""Shared pytest fixtures/configuration for the Agentic Cinema test suites.

Forces the embedded chDB backend (free, no ClickHouse Cloud account/credits) for
any test that touches ClickHouse, and ensures the golden-dataset fixtures exist.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"

# Fixtures the golden dataset generator emits. They are gitignored (*.pdf/*.eml),
# so they only exist locally after `generate_golden_dataset.py` runs. CI checks out
# the repo WITHOUT them — generate them on demand so the suites never hit
# FileNotFoundError on a fresh checkout.
_REQUIRED_FIXTURES = [
    "coverage_report.pdf",
    "coverage_scanned.pdf",
    "feedback_corrupted.pdf",
    "producer_email.eml",
    "manager_email.eml",
    "director_email.eml",
    "golden_labels.py",
    "golden_labels.json",
]


@pytest.fixture(autouse=True)
def _force_chdb():
    """Every test that imports src.clickhouse must use free, file-backed chDB."""
    os.environ.setdefault("CHDB_ENABLED", "true")
    os.environ.setdefault("CLICKHOUSE_ENABLED", "false")
    os.environ.setdefault("CHDB_DATA_PATH", "/tmp/agentic_cinema_chdb_test")
    os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "true"
    yield


@pytest.fixture(autouse=True, scope="session")
def _ensure_golden_fixtures():
    """Generate the golden fixtures if any are missing (e.g. on a fresh CI checkout)."""
    if any(not (GOLDEN_DIR / name).exists() for name in _REQUIRED_FIXTURES):
        gen_path = GOLDEN_DIR / "generate_golden_dataset.py"
        spec = importlib.util.spec_from_file_location("generate_golden_dataset", gen_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()  # builds every fixture into GOLDEN_DIR
    yield


@pytest.fixture
def golden_dir() -> Path:
    return GOLDEN_DIR
