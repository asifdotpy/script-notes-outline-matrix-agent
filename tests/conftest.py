"""Shared pytest fixtures/configuration for the Agentic Cinema test suites.

Forces the embedded chDB backend (free, no ClickHouse Cloud account/credits) for
any test that touches ClickHouse, and exposes the golden-dataset directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"


@pytest.fixture(autouse=True)
def _force_chdb():
    """Every test that imports src.clickhouse must use free, file-backed chDB."""
    os.environ.setdefault("CHDB_ENABLED", "true")
    os.environ.setdefault("CLICKHOUSE_ENABLED", "false")
    os.environ.setdefault("CHDB_DATA_PATH", "/tmp/agentic_cinema_chdb_test")
    os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "true"
    yield


@pytest.fixture
def golden_dir() -> Path:
    return GOLDEN_DIR
