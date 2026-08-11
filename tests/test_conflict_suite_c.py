"""Suite C — Conflict-detection tests (board task t_280a08f9).

Calls deterministic detect_conflicts(notes) against the golden categorized notes
and asserts the task contract:
  C1. Every PLANTED conflict pair is flagged (recall == 1).
  C2. Non-conflicting SAME-SCENE pairs with DIFFERENT concerns (e.g. dialogue vs
      pacing) are NOT flagged (no false positives).
  C3. AGREEMENT (two reviewers both "expand the dinner scene") is NOT a conflict.
  C4. A single reviewer restating their own note is NOT flagged as a self-conflict.
  C5. Precision & recall over the golden dataset are tracked and must be 1.0.
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
)
from tests.fixtures.golden.golden_labels import (  # noqa: E402
    GOLDEN_CATEGORIES,
    GOLDEN_CONFLICTS,
)


@pytest.fixture
def golden_notes():
    """Index-aligned heuristic-categorized notes for all golden rows."""
    return _heuristic_categorize([r[4] for r in GOLDEN_CATEGORIES])


@pytest.fixture
def golden_pairs(golden_notes):
    det = detect_conflicts(golden_notes)
    return [(d["note_a_idx"], d["note_b_idx"]) for d in det]


def _scene_of(notes, idx) -> int:
    return int(notes[idx].get("scene_number", 0) or 0)


def _text_of(notes, idx) -> str:
    return notes[idx].get("raw_text", "")


# --- C1: planted conflicts all flagged (recall == 1) ------------------------
def test_c1_all_planted_conflicts_flagged(golden_notes, golden_pairs):
    detected_scenes = set()
    for a, b in golden_pairs:
        detected_scenes.add(_scene_of(golden_notes, a))
        detected_scenes.add(_scene_of(golden_notes, b))
    golden_scenes = {int(g[1]) for g in GOLDEN_CONFLICTS}
    # recall at the scene level must be total
    assert golden_scenes <= detected_scenes, \
        f"golden conflict scenes {golden_scenes} not all flagged; got {detected_scenes}"
    # every golden conflict pair's two notes must be co-flagged on the same scene
    for cid, scene, _sa, na_id, _sb, nb_id, _ct in GOLDEN_CONFLICTS:
        na_idx = next(i for i, r in enumerate(GOLDEN_CATEGORIES) if r[0] == na_id)
        nb_idx = next(i for i, r in enumerate(GOLDEN_CATEGORIES) if r[0] == nb_id)
        assert (na_idx, nb_idx) in golden_pairs or (nb_idx, na_idx) in golden_pairs, \
            f"planted conflict {cid} (notes {na_id},{nb_id}) not detected"


def test_c1_conflict_count_matches_golden(golden_pairs):
    # 3 planted, opposing scene-5 pairs; detector must not invent more.
    assert len(golden_pairs) >= len(GOLDEN_CONFLICTS)
    # every detected pair is on a golden conflict scene (precision >= 1.0 at scene level)
    assert len(golden_pairs) == len(GOLDEN_CONFLICTS), \
        f"expected exactly {len(GOLDEN_CONFLICTS)} conflict pairs, got {len(golden_pairs)}"


# --- C2: non-conflicting same-scene / different-concern NOT flagged ----------
def test_c2_different_concerns_on_same_scene_not_flagged(golden_notes, golden_pairs):
    """Scene 2 has dialogue notes from 3 reviewers but NO conflict signal.

    Dialogue vs pacing are different concerns, and these are all agreement-ish,
    so none should be a conflict. (Scene 2 has zero golden conflicts.)
    """
    scene2_idxs = [i for i, r in enumerate(GOLDEN_CATEGORIES)
                   if r[7] == 2 and "dialogue" in r[5]]
    # No golden conflict references any note in scene 2's dialogue cluster.
    scene2_ids = {r[0] for r in GOLDEN_CATEGORIES if r[7] == 2}
    golden_uses_scene2 = any(na in scene2_ids or nb in scene2_ids
                             for _c, _s, _sa, na, _sb, nb, _ct in GOLDEN_CONFLICTS)
    assert not golden_uses_scene2, "test setup: scene 2 must be conflict-free"
    for a, b in golden_pairs:
        assert not (_scene_of(golden_notes, a) == 2 and _scene_of(golden_notes, b) == 2), \
            "dialogue notes on scene 2 wrongly flagged as a conflict"


def test_c2_scene3_has_no_real_conflict(golden_notes, golden_pairs):
    """Scene 3: producer 'tighten', manager 'cut', coverage 'drags'.

    All three are CUT-side guidance (no expand), so they are AGREEMENT on
    direction, not opposition -> must NOT be flagged (golden has no scene-3 conflict).
    """
    golden_scenes = {int(g[1]) for g in GOLDEN_CONFLICTS}
    assert 3 not in golden_scenes
    for a, b in golden_pairs:
        s = _scene_of(golden_notes, a)
        assert not (s == 3 and _scene_of(golden_notes, b) == 3), \
            "scene 3 cut-side notes wrongly flagged as opposition"


# --- C3: agreement is not a conflict ---------------------------------------
def test_c3_agreement_not_flagged(golden_notes, golden_pairs):
    """Production/manager/coverage all say 'expand the dinner scene' (scene 5, expand).

    Each pairing among those three is agreement (same direction), so none of those
    3 choose-2 = 3 pairs should appear as conflicts by themselves. The ONLY scene-5
    conflicts are expand-vs-cut (director's 'cut'), which are 3 distinct pairs.
    """
    # Notes that say 'expand' on scene 5
    expand_idxs = [i for i, r in enumerate(GOLDEN_CATEGORIES)
                   if r[7] == 5 and "expand" in r[4].lower()]
    for a, b in golden_pairs:
        pair = {a, b}
        if pair <= set(expand_idxs):
            pytest.fail(f"two agreeing 'expand' notes flagged as conflict: {pair}")


# --- C4: single reviewer restating self is NOT a self-conflict --------------
def test_c4_no_self_conflict_from_one_reviewer():
    """One reviewer's two notes about the same scene are not a 'conflict'."""
    notes = [
        {"raw_text": "Expand the dinner scene, it's the core.", "scene_number": 5,
         "note_type": "character", "category": "character"},
        {"raw_text": "The dinner scene is the heart, expand it more.", "scene_number": 5,
         "note_type": "character", "category": "character"},
    ]
    det = detect_conflicts(notes)
    # Both 'expand' -> same direction -> agreement, NOT a self-conflict.
    assert det == [], f"single reviewer agreement flagged as conflict: {det}"


def test_c4_opposing_same_reviewer_is_flagged():
    """But a single reviewer genuinely contradicting themselves IS a conflict."""
    notes = [
        {"raw_text": "Expand the dinner scene.", "scene_number": 5,
         "note_type": "character", "category": "character"},
        {"raw_text": "Actually, cut the dinner scene entirely.", "scene_number": 5,
         "note_type": "character", "category": "character"},
    ]
    det = detect_conflicts(notes)
    assert len(det) == 1, f"self-opposition should be flagged: {det}"


# --- C5: precision & recall tracked, must be 1.0 ----------------------------
def test_c5_precision_recall():
    import sys
    sys.path.insert(0, str(ROOT))
    from tests.eval_harness import conflict_metrics

    notes = _heuristic_categorize([r[4] for r in GOLDEN_CATEGORIES])
    det = detect_conflicts(notes)
    pred_pairs = [(d["note_a_idx"], d["note_b_idx"]) for d in det]
    m = conflict_metrics(pred_pairs, GOLDEN_CONFLICTS, notes)
    assert m["pair_precision"] == 1.0, m
    assert m["pair_recall"] == 1.0, m
    assert m["scene_recall"] == 1.0, m
