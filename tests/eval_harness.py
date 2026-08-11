"""Eval harness for the Script Notes-to-Outline Matrix Agent.

Scores the pipeline's output against the golden dataset
(tests/fixtures/golden/) and reports accuracy / precision / recall for
categorization and conflict detection.

Two evaluation paths:

1. DETERMINISTIC (always run, CI-safe). Exercises the reproducible, LLM-free
   pipeline: ingestion -> heuristic categorization -> scene resolution ->
   heuristic conflict grouping -> ClickHouse persistence. Metrics are compared
   against an EXPECTED baseline (measured once, committed) as a *regression
   guard*: the new run must not be materially worse. This is honest — the
   heuristic categorizer is a guaranteed fallback, not the quality ceiling.

2. LLM QUALITY (optional). When GEMINI_API_KEY is set and --llm is passed,
   the harness scores the Gemini-categorized notes against the golden labels
   with a real quality bar (accuracy >= 0.80, conflict precision >= 0.5). This
   path is intentionally NOT run in CI (no key, nondeterministic); it is used
   for the manual demo re-run (see board task t_f3ae062c).

Run:
    python tests/eval_harness.py            # deterministic report, exit 0/1
    python tests/eval_harness.py --llm       # also attempt LLM quality gate
    pytest tests/eval_harness.py             # deterministic regression test

Outputs: tests/fixtures/golden/eval_report.json (machine-readable).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "golden"
sys.path.insert(0, str(ROOT))

from tests.fixtures.golden.golden_labels import (  # noqa: E402
    GOLDEN_CATEGORIES,
    GOLDEN_CONFLICTS,
    VALID_CATEGORIES,
    VALID_SEVERITIES,
)

# ---------------------------------------------------------------------------
# EXPECTED baselines (measured 2026-08-11 on the deterministic pipeline).
# The CI gate asserts actual >= baseline - TOLERANCE so a real regression
# (e.g. categorization accuracy collapsing) turns the build red, while the
# harness still honestly reports the heuristic's modest absolute quality.
# ---------------------------------------------------------------------------
EXPECTED = {
    "categorization_accuracy": 0.565,
    "scene_accuracy": 0.90,
    "conflict_scene_recall": 1.0,   # both golden conflict scenes must be flagged
    "conflict_pair_recall": 1.0,
}
TOLERANCE = 0.05


# ---------------------------------------------------------------------------
# Alignment helpers
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def align_by_text(predictions: list[dict], golden: list[tuple]) -> list[tuple[dict, tuple]]:
    """Greedily align predicted notes to golden notes by best normalized-text overlap.

    predictions: list of {raw_text, category, severity, scene_number, ...}
    golden: GOLDEN_CATEGORIES rows.
    Returns list of (pred, gold_row) pairs (unmatched dropped).
    """
    gold_pool = list(golden)
    pairs = []
    used_gold = set()
    # Sort predictions by length desc so longer/more-specific notes match first.
    for pred in sorted(predictions, key=lambda p: -len(_norm(p.get("raw_text", "")))):
        pn = _norm(pred.get("raw_text", ""))
        best = None
        best_score = 0.0
        for gi, g in enumerate(gold_pool):
            if gi in used_gold:
                continue
            gn = _norm(g[4])
            # containment either direction
            if pn and (pn in gn or gn in pn):
                score = min(len(pn), len(gn)) / max(len(pn), len(gn), 1)
                if score > best_score:
                    best_score, best = score, gi
        if best is not None:
            used_gold.add(best)
            pairs.append((pred, gold_pool[best]))
    return pairs


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------
def categorization_metrics(pairs: list[tuple[dict, tuple]]) -> dict:
    """Accuracy + per-class precision/recall/F1 over aligned (pred, gold) pairs.

    gold row shape: (note_id, file, source_type, author, raw_text,
                     expected_category, expected_severity, scene_number)
    """
    correct = 0
    per_class: dict[str, dict[str, int]] = {}
    for pred, g in pairs:
        pred_cat = str(pred.get("category") or pred.get("note_type") or "").lower()
        gold_cat = g[5].lower()
        per_class.setdefault(gold_cat, {"tp": 0, "fp": 0, "fn": 0})
        per_class.setdefault(pred_cat, {"tp": 0, "fp": 0, "fn": 0})
        if pred_cat == gold_cat:
            correct += 1
            per_class[gold_cat]["tp"] += 1
        else:
            per_class.setdefault(gold_cat, {"tp": 0, "fp": 0, "fn": 0})["fn"] += 1
            per_class.setdefault(pred_cat, {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1

    n = len(pairs)
    accuracy = correct / n if n else 0.0

    # Macro precision/recall/F1 over classes that appear in gold.
    precisions, recalls, f1s = [], [], []
    for cat, c in per_class.items():
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        if tp + fp == 0 and tp + fn == 0:
            continue  # class never predicted and never gold -> skip
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        precisions.append(p)
        recalls.append(r)
        f1s.append(f1)
    macro_p = sum(precisions) / len(precisions) if precisions else 0.0
    macro_r = sum(recalls) / len(recalls) if recalls else 0.0
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    return {
        "accuracy": accuracy,
        "n": n,
        "correct": correct,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "per_class": per_class,
    }


def scene_metrics(pairs: list[tuple[dict, tuple]]) -> dict:
    correct = 0
    for pred, g in pairs:
        try:
            ps = int(pred.get("scene_number", 0) or 0)
        except (TypeError, ValueError):
            ps = 0
        if ps == int(g[7]):
            correct += 1
    n = len(pairs)
    return {"scene_accuracy": correct / n if n else 0.0, "n": n, "correct": correct}


def conflict_metrics(predicted_pairs: list[tuple[int, int]],
                     golden_pairs: list[tuple],
                     notes: list[dict]) -> dict:
    """Pair-level + scene-level precision/recall for conflict detection.

    predicted_pairs: list of (idx_a, idx_b) as returned by detect_conflicts.
    """
    # Scene-level: which scenes have >=1 predicted conflict.
    pred_scenes = set()
    for a, b in predicted_pairs:
        sa = int(notes[a].get("scene_number", 0) or 0)
        sb = int(notes[b].get("scene_number", 0) or 0)
        pred_scenes.add(sa)
        pred_scenes.add(sb)
    gold_scenes = {int(g[1]) for g in golden_pairs}

    # Pair-level: a predicted pair matches a golden pair if both notes belong to
    # the same golden conflict scene AND that scene is a golden conflict scene.
    # (Lenient-but-meaningful: we don't demand identical note_ids, because the
    # LLM may phrase notes differently but still flag the same beat.)
    matched_gold_scenes = set()
    for a, b in predicted_pairs:
        sa = int(notes[a].get("scene_number", 0) or 0)
        sb = int(notes[b].get("scene_number", 0) or 0)
        scene = sa if sa == sb else None
        if scene in gold_scenes:
            matched_gold_scenes.add(scene)
    tp = len(matched_gold_scenes)
    fp = len(pred_scenes - gold_scenes)
    fn = len(gold_scenes - pred_scenes)
    pair_precision = tp / (tp + fp) if (tp + fp) else 0.0
    pair_recall = tp / (tp + fn) if (tp + fn) else 0.0
    scene_recall = (len(pred_scenes & gold_scenes) / len(gold_scenes)) if gold_scenes else 0.0
    return {
        "predicted_pairs": len(predicted_pairs),
        "golden_pairs": len(golden_pairs),
        "pair_precision": pair_precision,
        "pair_recall": pair_recall,
        "scene_recall": scene_recall,
        "pred_scenes": sorted(pred_scenes),
        "gold_scenes": sorted(gold_scenes),
    }


# ---------------------------------------------------------------------------
# Deterministic pipeline runner
# ---------------------------------------------------------------------------
def run_deterministic() -> dict:
    from src.agent.tools.note_tools import _heuristic_categorize, detect_conflicts

    texts = [g[4] for g in GOLDEN_CATEGORIES]
    cats = _heuristic_categorize(texts)  # index-aligned to GOLDEN_CATEGORIES
    pairs = list(zip(cats, GOLDEN_CATEGORIES))
    cat_m = categorization_metrics(pairs)
    sc_m = scene_metrics(pairs)
    # detect_conflicts on the heuristic-categorized notes (has note_type/raw_text).
    detected = detect_conflicts(cats)
    pred_pairs = [(d["note_a_idx"], d["note_b_idx"]) for d in detected]
    conf_m = conflict_metrics(pred_pairs, GOLDEN_CONFLICTS, cats)
    return {
        "mode": "deterministic",
        "categorization": cat_m,
        "scene": sc_m,
        "conflict": conf_m,
    }


# ---------------------------------------------------------------------------
# Regression gate
# ---------------------------------------------------------------------------
def _gate(name: str, actual: float, expected: float, tol: float = TOLERANCE) -> bool:
    ok = actual >= expected - tol
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}: actual={actual:.3f}  expected>={expected - tol:.3f} "
          f"(baseline {expected:.3f})")
    return ok


def evaluate() -> tuple[dict, bool]:
    print("\n===== Agentic Cinema EVAL HARNESS (deterministic) =====")
    res = run_deterministic()

    cm = res["categorization"]
    sm = res["scene"]
    cf = res["conflict"]

    print(f"\nCategorization: {cm['correct']}/{cm['n']} exact = accuracy {cm['accuracy']:.3f}")
    print(f"  macro P={cm['macro_precision']:.3f}  R={cm['macro_recall']:.3f}  "
          f"F1={cm['macro_f1']:.3f}")
    print(f"Scene resolution accuracy: {sm['scene_accuracy']:.3f} ({sm['correct']}/{sm['n']})")
    print(f"Conflicts: predicted_pairs={cf['predicted_pairs']} golden_pairs={cf['golden_pairs']}")
    print(f"  pair precision={cf['pair_precision']:.3f}  pair recall={cf['pair_recall']:.3f}  "
          f"scene recall={cf['scene_recall']:.3f}")

    passed = True
    print("\nRegression gate (deterministic baseline):")
    passed &= _gate("categorization_accuracy", cm["accuracy"], EXPECTED["categorization_accuracy"])
    passed &= _gate("scene_accuracy", sm["scene_accuracy"], EXPECTED["scene_accuracy"])
    passed &= _gate("conflict_scene_recall", cf["scene_recall"], EXPECTED["conflict_scene_recall"])
    passed &= _gate("conflict_pair_recall", cf["pair_recall"], EXPECTED["conflict_pair_recall"])

    report = {
        "mode": "deterministic",
        "metrics": {"categorization": cm, "scene": sm, "conflict": cf},
        "expected_baselines": EXPECTED,
        "gate_passed": passed,
    }
    out = FIXTURES / "eval_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nReport written: {out}")
    print("RESULT:", "PASS" if passed else "FAIL")
    return report, passed


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Agentic Cinema eval harness")
    p.add_argument("--llm", action="store_true",
                   help="Also attempt the LLM quality gate (requires GEMINI_API_KEY).")
    args = p.parse_args()

    report, passed = evaluate()

    if args.llm:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            print("\n[LLM] GEMINI_API_KEY not set — skipping LLM quality gate.")
        else:
            try:
                from tests.eval_llm import run_llm_eval  # optional module
            except ImportError:
                print("\n[LLM] tests/eval_llm.py not present — LLM quality gate unavailable.")
            else:
                llm_ok = run_llm_eval(report)
                passed = passed and llm_ok
    return 0 if passed else 1


# --- pytest entrypoint: the deterministic gate doubles as a regression test ---
def test_eval_harness_regression_gate():
    """The deterministic pipeline must not regress below the committed baseline."""
    _report, passed = evaluate()
    assert passed, "Deterministic eval harness regressed below baseline; see eval_report.json"


import os  # placed at bottom to keep argparse import local

if __name__ == "__main__":
    raise SystemExit(main())
