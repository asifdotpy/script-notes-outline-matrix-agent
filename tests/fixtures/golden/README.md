# Golden Test Dataset — "The Last Lighthouse"

Synthetic screenplay + 4 labeled external feedback docs used by the eval harness
and test suites A–E. Regenerate with `python generate_golden_dataset.py`.

## Files
- `script_the_last_lighthouse.txt` — 7-scene synthetic screenplay.
- `producer_email.eml` / `manager_email.eml` — two stakeholder emails (.eml/.txt).
- `coverage_report.pdf` — PDF coverage report (rendered via fpdf2).
- `feedback_corrupted.pdf` — truncated/garbage bytes (tests parser robustness / OCR-fail flag).
- `golden_labels.py` / `golden_labels.json` — deterministic golden labels.

## Golden labels
- **23 notes** across categories ['character', 'dialogue', 'format', 'logic', 'other', 'pacing', 'structure'].
- **3 planted conflict pairs** (scene 3: trim/cut disagreement).
- Category distribution: {'structure': 3, 'dialogue': 3, 'pacing': 6, 'logic': 2, 'character': 4, 'other': 4, 'format': 1}

## Conflict design
The clearest cross-stakeholder contradiction is **scene 3**: the producer says
"tighten" (keep, shorten) and the manager says "cut entirely", while coverage
flags it as merely dragging (pacing) — two materially different dispositions on
the same scene. Scene 5 (expand the dinner) is *agreement* across all three
readers and is intentionally NOT a conflict, to test false-positive resistance.
