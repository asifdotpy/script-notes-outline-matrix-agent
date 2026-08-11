"""Suite for script-scene cross-check (board task t_4f0e8c7c).

Calls deterministic cross_check_script_scenes(script, notes) and asserts:
  1. Every note whose scene resolves to a real numbered scene in the script is
     classified 'matched' (matched count == # notes pointing at valid scenes).
  2. Vague notes that cannot be tied to any scene (scene 0) are 'unmapped', not
     mislabeled as a script mismatch.
  3. A note referencing a scene the script DOES NOT contain (out-of-range / a
     synthetic word-scene key with no real numbered scene) is 'out_of_range' —
     surfaced as a genuine script-vs-notes mismatch, never dropped or forced onto a
     real scene. (This mirrors the 'Script vs Notes = N' flag on the Planted
     Conflicts matrix.)
  4. parse_screenplay_scenes extracts the exact scene headings from the script
     (the authoritative list of scenes that exist).
  5. The cross-check is deterministic and runs without any LLM/network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent.tools.note_tools import (  # noqa: E402
    cross_check_script_scenes,
    parse_screenplay_scenes,
)
from tests.fixtures.golden.golden_labels import GOLDEN_CATEGORIES  # noqa: E402

SCRIPT = (ROOT / "tests/fixtures/golden/script_the_last_lighthouse.txt").read_text()


@pytest.fixture
def notes():
    return [{"raw_text": r[4]} for r in GOLDEN_CATEGORIES]


# --- 4: script parsing ------------------------------------------------------
def test_4_parser_finds_all_seven_scenes():
    scenes = parse_screenplay_scenes(SCRIPT)
    assert len(scenes) == 7
    assert [s["scene_number"] for s in scenes] == [1, 2, 3, 4, 5, 6, 7]


def test_4_parser_handles_numbered_sluglines():
    # The golden script uses "N. INT./EXT. ..." numbered headings.
    scenes = parse_screenplay_scenes("1. EXT. CLIFF - DAWN\n\n2. INT. ROOM - DAY\n")
    assert [s["scene_number"] for s in scenes] == [1, 2]


def test_4_parser_handles_explicit_scene_headings():
    scenes = parse_screenplay_scenes("SCENE 3\nSome action.\n\nSCENE 7\nMore.\n")
    assert [s["scene_number"] for s in scenes] == [3, 7]


# --- 1: matched -------------------------------------------------------------
def test_1_all_valid_scene_notes_matched(notes):
    cc = cross_check_script_scenes(SCRIPT, notes)
    # 21 of 23 golden notes point at a real 1..7 scene.
    assert cc["n_scenes"] == 7
    assert len(cc["matched"]) == 21
    # every matched note's scene is genuinely in the script
    for e in cc["matched"]:
        assert e["scene_number"] in cc["scene_numbers"]


# --- 2: unmapped (vague) ----------------------------------------------------
def test_2_vague_note_is_unmapped_not_mismatch(notes):
    cc = cross_check_script_scenes(SCRIPT, notes)
    # The format note ("scene headings are inconsistent") resolves to scene 0.
    un = [e for e in cc["unmapped"] if "scene headings are inconsistent" in e["raw_text"].lower()]
    assert len(un) == 1, "format note must be unmapped, not flagged as a script mismatch"
    assert un[0]["scene_number"] == 0


# --- 3: out_of_range (script vs notes mismatch) -----------------------------
def test_3_opening_scene_flagged_out_of_range(notes):
    cc = cross_check_script_scenes(SCRIPT, notes)
    oor = [e for e in cc["out_of_range"]
           if "opening scene" in e["raw_text"].lower()]
    assert len(oor) == 1
    # The heuristic maps "opening scene" to a synthetic key (900+) that has no real
    # numbered scene 1 in the script's *numbered* scene set, so it is a mismatch.
    assert oor[0]["scene_number"] not in cc["scene_numbers"]
    assert oor[0]["scene_number"] >= 900  # synthetic word-scene key


def test_3_explicit_nonexistent_scene_is_out_of_range():
    notes = [{"raw_text": "Scene 99 is the true climax — rewrite it entirely."}]
    cc = cross_check_script_scenes(SCRIPT, notes)
    assert len(cc["out_of_range"]) == 1
    assert cc["out_of_range"][0]["scene_number"] == 99
    assert cc["out_of_range"][0]["scene_number"] not in cc["scene_numbers"]


def test_3_oor_never_forced_onto_real_scene(notes):
    cc = cross_check_script_scenes(SCRIPT, notes)
    # No out_of_range note may share a scene_number with a real script scene.
    for e in cc["out_of_range"]:
        assert e["scene_number"] not in {1, 2, 3, 4, 5, 6, 7}


# --- 5: determinism / no network --------------------------------------------
def test_5_deterministic(notes):
    a = cross_check_script_scenes(SCRIPT, notes)
    b = cross_check_script_scenes(SCRIPT, notes)
    assert a == b


def test_5_classification_exhaustive(notes):
    cc = cross_check_script_scenes(SCRIPT, notes)
    total = len(cc["matched"]) + len(cc["unmapped"]) + len(cc["out_of_range"])
    assert total == len(notes), f"every note must be classified: {total} != {len(notes)}"
