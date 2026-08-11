"""Suite D — Checklist tests (board task t_269b581e).

Calls deterministic build_checklist(notes, conflicts, known_scenes) and asserts:
  D1. ZERO hallucination: every checklist item is traceable to a real source note
      (verbatim raw_text + source_index pointing into the input notes).
  D2. Items grouped by real scene number; numbered scenes ordered ascending.
  D3. Upstream-first ordering within a scene (structure/logic before line-level),
      ties broken by severity (high before medium before low).
  D4. Vague / unmapped notes (no resolvable scene) surfaced under 'Unassigned',
      not dropped or misassigned to a real scene.
  D5. Notes referencing a NON-EXISTENT scene are flagged 'unresolvable' under
      'Out-of-range', not silently merged into a real scene.
  D6. Conflicts attached to the correct scene group.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent.tools.note_tools import (  # noqa: E402
    _heuristic_categorize,
    detect_conflicts,
    build_checklist,
)
from tests.fixtures.golden.golden_labels import GOLDEN_CATEGORIES  # noqa: E402

KNOWN_SCENES = {1, 2, 3, 4, 5, 6, 7}  # the script has 7 scenes


@pytest.fixture
def inputs():
    notes = _heuristic_categorize([r[4] for r in GOLDEN_CATEGORIES])
    conflicts = detect_conflicts(notes)
    checklist = build_checklist(notes, conflicts, known_scenes=KNOWN_SCENES)
    return notes, conflicts, checklist


# --- D1: zero hallucination ------------------------------------------------
def test_d1_every_item_traceable_to_source(inputs):
    notes, _conflicts, checklist = inputs
    for group in checklist:
        for item in group["items"]:
            src = notes[item["source_index"]]
            # verbatim raw_text must match the source note exactly
            assert item["raw_text"] == src.get("raw_text"), \
                f"item hallucinated vs source {item['source_index']}"
            # text field must contain the verbatim raw text segment
            assert item["raw_text"][:40] in item["text"]


def test_d1_no_extra_items_beyond_sources(inputs):
    notes, _conflicts, checklist = inputs
    total_items = sum(len(g["items"]) for g in checklist)
    assert total_items == len(notes), \
        f"checklist has {total_items} items for {len(notes)} notes (dropped or invented)"


# --- D2: grouped by real scene, numbered ascending --------------------------
def test_d2_grouped_by_scene_numbers(inputs):
    _notes, _conflicts, checklist = inputs
    scene_groups = [g["scene"] for g in checklist if g["scene"].isdigit()]
    # every numbered scene that has notes must appear
    assert "1" in scene_groups and "5" in scene_groups and "7" in scene_groups
    # numeric scenes ordered ascending
    nums = [int(s) for s in scene_groups]
    assert nums == sorted(nums), f"scenes not ascending: {nums}"


def test_d2_real_scenes_have_integer_field(inputs):
    _notes, _conflicts, checklist = inputs
    for g in checklist:
        if g["scene"].isdigit():
            assert g["scene_number"] == int(g["scene"])
        else:
            assert g["scene_number"] is None


# --- D3: upstream-first ordering --------------------------------------------
def test_d3_upstream_first_within_scene(inputs):
    """Within a scene, structure/logic precede pacing/character precede dialogue."""
    _notes, _conflicts, checklist = inputs
    cat_rank = {"structure": 0, "logic": 1, "pacing": 2, "character": 3,
                "dialogue": 4, "format": 5, "other": 6}
    for g in checklist:
        cats = [cat_rank.get(i["category"].lower(), 6) for i in g["items"]]
        assert cats == sorted(cats), f"scene {g['scene']} not upstream-first: {cats}"


def test_d3_severity_ties_broken_high_first():
    """Same-category items should appear high -> medium -> low."""
    notes = [
        {"raw_text": "tension low", "note_type": "structure", "category": "structure",
         "severity": "low", "scene_number": 1},
        {"raw_text": "tension high", "note_type": "structure", "category": "structure",
         "severity": "high", "scene_number": 1},
        {"raw_text": "tension med", "note_type": "structure", "category": "structure",
         "severity": "medium", "scene_number": 1},
    ]
    cl = build_checklist(notes, [], known_scenes={1})
    sev = [i["severity"] for i in cl[0]["items"]]
    assert sev == ["high", "medium", "low"], sev


# --- D4: unassigned (vague / unmapped) --------------------------------------
def test_d4_unmapped_notes_go_to_unassigned(inputs):
    """The format note (no scene) has no resolvable scene -> Unassigned, not dropped."""
    _notes, _conflicts, checklist = inputs
    groups = {g["scene"]: g for g in checklist}
    assert "Unassigned" in groups
    unassigned_raw = " ".join(i["raw_text"].lower() for i in groups["Unassigned"]["items"])
    assert "scene headings are inconsistent" in unassigned_raw, \
        "the format note must land in Unassigned, not vanish"


def test_d4_unassigned_not_mixed_into_real_scene(inputs):
    _notes, _conflicts, checklist = inputs
    for g in checklist:
        if g["scene"].isdigit():
            for item in g["items"]:
                assert "scene headings are inconsistent" not in item["raw_text"].lower()


# --- D5: out-of-range scene flagged unresolvable ----------------------------
def test_d5_nonexistent_scene_flagged_unresolvable():
    notes = [
        {"raw_text": "Scene 99 is the true climax, rewrite it.", "note_type": "structure",
         "category": "structure", "severity": "high", "scene_number": 99},
    ]
    cl = build_checklist(notes, [], known_scenes={1, 2, 3, 4, 5, 6, 7})
    groups = {g["scene"]: g for g in cl}
    assert "Out-of-range" in groups, "out-of-range scene must be its own group"
    item = groups["Out-of-range"]["items"][0]
    assert item["unresolvable"] is True
    assert "UNRESOLVABLE" in item["text"], "must be visibly flagged"
    assert item["raw_text"] == "Scene 99 is the true climax, rewrite it."


def test_d5_unresolvable_not_merged_into_real_scene():
    notes = [
        {"raw_text": "Scene 99 is the true climax.", "note_type": "structure",
         "category": "structure", "severity": "high", "scene_number": 99},
        {"raw_text": "Expand the dinner scene.", "note_type": "character",
         "category": "character", "severity": "high", "scene_number": 5},
    ]
    cl = build_checklist(notes, [], known_scenes={1, 2, 3, 4, 5, 6, 7})
    groups = {g["scene"]: g for g in cl}
    # scene 5 must NOT contain the scene-99 note
    for item in groups["5"]["items"]:
        assert "Scene 99" not in item["raw_text"]
    assert groups["Out-of-range"]["items"][0]["raw_text"].startswith("Scene 99")


# --- D6: conflicts attached to the right scene ------------------------------
def test_d6_conflicts_attached_to_scene5(inputs):
    _notes, _conflicts, checklist = inputs
    groups = {g["scene"]: g for g in checklist}
    # Scene 5 has the planted conflict (director cut vs everyone expand).
    assert groups["5"]["conflicts"], "scene 5 should carry the flagged conflict"
    assert any("Opposing" in c for c in groups["5"]["conflicts"])


def test_d6_no_conflict_on_conflict_free_scenes(inputs):
    _notes, _conflicts, checklist = inputs
    groups = {g["scene"]: g for g in checklist}
    for scene in ("1", "2", "3", "4", "6", "7"):
        assert not groups[scene]["conflicts"], \
            f"scene {scene} is conflict-free but got {groups[scene]['conflicts']}"
