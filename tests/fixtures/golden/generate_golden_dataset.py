"""Generate the Agentic Cinema GOLDEN dataset.

Produces a synthetic screenplay plus 4 labeled external feedback documents with
golden labels for (a) note categorization and (b) planted conflicts between
stakeholders. The fixtures and labels are committed so the eval harness and the
test suites A-E can assert against a stable, deterministic reference.

This script is deterministic: every note_id, scene_number and category is pinned
so the labeled outputs never drift run-to-run. Re-running it regenerates byte-stable
fixtures (the .eml/.txt are static strings below; the .pdf is rendered from fixed
text via fpdf2; the corrupted file is fixed bytes).

Run:  python tests/fixtures/golden/generate_golden_dataset.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from fpdf import FPDF

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 1. Synthetic screenplay ("The Last Lighthouse") — 7 numbered scenes.
# ---------------------------------------------------------------------------
SCREENPLAY = """FADE IN:

1. EXT. COASTAL CLIFF - DAWN
A weathered lighthouse stands against a bruised sky. ELLA (40s), a marine
biologist, climbs the rocks below, searching for her missing brother's boat.
The wind howls. A flock of crows scatters.

2. INT. LIGHTHOUSE KEEPER'S ROOM - DAY
Ella examines a wall of faded photographs. A radio crackles with static. She
finds a locked drawer. The room is claustrophobic, the light amber and low.

3. EXT. VILLAGE HARBOR - AFTERNOON
Ella questions old fishermen about the night her brother vanished. They are
evasive. A child watches her from a rowboat. The pacing here drags a little.

4. INT. TOWN ARCHIVES - NIGHT
Ella uncovers a logbook showing the lighthouse was dark on the night of the
disappearance. She realizes someone lied. A slow reveal, nicely built.

5. INT. DINING ROOM - NIGHT
Ella confronts the harbormaster over dinner. Tension at the table. He denies
everything but his hands tremble. This is the emotional core of the film.

6. EXT. STORMY SEA - NIGHT
Ella takes a small boat into the storm to reach the abandoned lighthouse island.
Waves crash. The sequence is thrilling but a touch too long.

7. EXT. LIGHTHOUSE ISLAND - DAWN
Ella finds the truth etched into the lantern room glass. She forgives, and the
light comes on again. A quiet, hopeful ending.

FADE OUT.
"""

# ---------------------------------------------------------------------------
# 2. Feedback document texts.
# ---------------------------------------------------------------------------
# (a) Producer email (.eml)
PRODUCER_EMAIL = """From: margaret@harborfilms.com
To: ella.writer@studio.com
Subject: Notes on The Last Lighthouse - Draft 1

Hi Ella,

Thanks for sending Draft 1. Overall I think the bones are strong but here are
my notes from the read:

The opening scene is too slow. We lose the audience in the first two minutes.
Cut about a third of scene 1 and get to Ella climbing faster.

Scene 3 drags. Tighten the harbor questioning — it runs long.

Expand the dinner scene. Scene 5 is the emotional core and right now it feels
rushed. Give the harbormaster more to do.

The storm sequence in scene 6 is too long. Trim it by a minute.

Love the ending. Scene 7 is perfect, don't change it.

Dialogue in scene 2 is on the nose. Make it sharper and less expository.

Best,
Margaret
"""

# (b) Manager email (.eml)
MANAGER_EMAIL = """From: dev@talentmgmt.com
To: ella.writer@studio.com
Subject: Re: The Last Lighthouse notes

Ella —

Read it twice. Strong work. A few thoughts from the manager side:

Expand the dinner scene. Scene 5 needs more room to breathe; the confrontation
is the heart of the movie.

The opening scene is too slow. I'd actually open even later, mid-climb.

Dialogue in scene 2 is on the nose. Agreed with Margaret, sharpen it.

I loved scene 7. Keep it exactly as is.

The logic of the archives reveal in scene 4 is murky. How does she know the
light was off? Make the clue concrete.

Cut scene 3 entirely. The harbor questioning slows the middle.

Dev
"""

# (c2) Director email (.eml) — the OPPOSING voice that plants a clean conflict:
# the director wants scene 5 CUT while producer/manager/coverage want it EXPANDED.
DIRECTOR_EMAIL = """From: nadia@lighthousefilm.com
To: ella.writer@studio.com
Subject: My take on The Last Lighthouse

Ella,

Directing thoughts after my read:

Cut the dinner scene. Scene 5 stops the film dead — I'd remove it entirely and
fold the reveal into the archives.

Tighten scene 6. The storm is gorgeous but overlong.

Scene 7 is the reason I want to make this. Keep it untouched.

Nadia
"""

# (c) PDF coverage report (rendered to PDF)
COVERAGE_TEXT = """SCRIPT COVERAGE REPORT
Title: The Last Lighthouse
Coverage by: Black List Reader #4421
Recommendation: CONSIDER

LOGLINE: A marine biologist returns to her isolated hometown to find her
missing brother and uncovers a small-town secret kept in the lighthouse.

STRENGTHS:
- The emotional core in the dinner scene (scene 5) lands. Expand it; the
  confrontation between Ella and the harbormaster is the best writing here.
- The ending (scene 7) is quietly powerful. Do not change it.
- Strong visual sense throughout.

WEAKNESSES:
- Structure: the opening (scene 1) is too slow and risks losing the audience.
- Pacing: scene 3 drags and scene 6 is overlong.
- Character: the harbormaster in scene 5 needs more dimension.
- Logic: the scene 4 archives reveal lacks a concrete clue.

POLISH:
- Dialogue in scene 2 is on the nose.
- Format: scene headings are inconsistent in a few places.

OVERALL: A compelling character piece held back by a soft open and a saggy
middle. Address structure and pacing and this is a strong recommendation.
"""

# (d) Corrupted file (truncated / not a real PDF) — proves parser robustness.
CORRUPTED_PDF = b"%PDF-1.4\n1 0 obj<< /Type /Catalog >>\n%%EOF\n" + b"\x00\x01\x02TRUNCATED"

# ---------------------------------------------------------------------------
# 3. Golden categorization labels.
# Each: (note_id, source_file, source_type, author, raw_text, expected_category,
#        expected_severity, scene_number)
# Categories ∈ {structure, character, dialogue, pacing, logic, format, other}
# Severities ∈ {high, medium, low}
# ---------------------------------------------------------------------------
GOLDEN_CATEGORIES = [
    # Scene 1 — opening too slow (structure/pacing)
    ("n01", "producer_email.eml", "producer_email", "Margaret",
     "The opening scene is too slow. We lose the audience in the first two minutes. Cut about a third of scene 1 and get to Ella climbing faster.",
     "structure", "high", 1),
    ("n02", "manager_email.eml", "agent_email", "Dev",
     "The opening scene is too slow. I'd actually open even later, mid-climb.",
     "structure", "high", 1),
    ("n03", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "Structure: the opening (scene 1) is too slow and risks losing the audience.",
     "structure", "high", 1),
    # Scene 2 — dialogue on the nose
    ("n04", "producer_email.eml", "producer_email", "Margaret",
     "Dialogue in scene 2 is on the nose. Make it sharper and less expository.",
     "dialogue", "high", 2),
    ("n05", "manager_email.eml", "agent_email", "Dev",
     "Dialogue in scene 2 is on the nose. Agreed with Margaret, sharpen it.",
     "dialogue", "high", 2),
    ("n06", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "Dialogue in scene 2 is on the nose.",
     "dialogue", "high", 2),
    # Scene 3 — drags / cut
    ("n07", "producer_email.eml", "producer_email", "Margaret",
     "Scene 3 drags. Tighten the harbor questioning — it runs long.",
     "pacing", "medium", 3),
    ("n08", "manager_email.eml", "agent_email", "Dev",
     "Cut scene 3 entirely. The harbor questioning slows the middle.",
     "pacing", "high", 3),
    ("n09", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "Pacing: scene 3 drags and scene 6 is overlong.",
     "pacing", "medium", 3),
    # Scene 4 — logic
    ("n10", "manager_email.eml", "agent_email", "Dev",
     "The logic of the archives reveal in scene 4 is murky. How does she know the light was off? Make the clue concrete.",
     "logic", "medium", 4),
    ("n11", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "Logic: the scene 4 archives reveal lacks a concrete clue.",
     "logic", "medium", 4),
    # Scene 5 — expand dinner (character)
    ("n12", "producer_email.eml", "producer_email", "Margaret",
     "Expand the dinner scene. Scene 5 is the emotional core and right now it feels rushed. Give the harbormaster more to do.",
     "character", "high", 5),
    ("n13", "manager_email.eml", "agent_email", "Dev",
     "Expand the dinner scene. Scene 5 needs more room to breathe; the confrontation is the heart of the movie.",
     "character", "high", 5),
    ("n14", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "The emotional core in the dinner scene (scene 5) lands. Expand it; the confrontation between Ella and the harbormaster is the best writing here.",
     "character", "high", 5),
    # Scene 6 — too long (pacing)
    ("n15", "producer_email.eml", "producer_email", "Margaret",
     "The storm sequence in scene 6 is too long. Trim it by a minute.",
     "pacing", "medium", 6),
    ("n16", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "Pacing: scene 3 drags and scene 6 is overlong.",
     "pacing", "medium", 6),
    # Scene 7 — love it (positive, low severity)
    ("n17", "producer_email.eml", "producer_email", "Margaret",
     "Love the ending. Scene 7 is perfect, don't change it.",
     "other", "low", 7),
    ("n18", "manager_email.eml", "agent_email", "Dev",
     "I loved scene 7. Keep it exactly as is.",
     "other", "low", 7),
    ("n19", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "The ending (scene 7) is quietly powerful. Do not change it.",
     "other", "low", 7),
    # Format (coverage only)
    ("n20", "coverage_report.pdf", "pdf_coverage", "Coverage #4421",
     "Format: scene headings are inconsistent in a few places.",
     "format", "low", 0),
    # Director email — the OPPOSING voice on scene 5 (plants the clean conflict).
    ("n21", "director_email.eml", "agent_email", "Nadia",
     "Cut the dinner scene. Scene 5 stops the film dead — I'd remove it entirely and fold the reveal into the archives.",
     "character", "high", 5),
    ("n22", "director_email.eml", "agent_email", "Nadia",
     "Tighten scene 6. The storm is gorgeous but overlong.",
     "pacing", "medium", 6),
    ("n23", "director_email.eml", "agent_email", "Nadia",
     "Scene 7 is the reason I want to make this. Keep it untouched.",
     "other", "low", 7),
]

# ---------------------------------------------------------------------------
# 4. Golden conflict pairs (planted contradictions between stakeholders).
# Each: (conflict_id, scene_number, stakeholder_a, note_a_id, stakeholder_b,
#        note_b_id, conflict_type)
# Reflects real opposing guidance: Margaret/Dev want scene 3 CUT/TIGHTENED,
# Coverage wants scene 3 KEPT (calls it a strength implicitly by only praising
# scenes 5 & 7 and flagging pacing "drags" but NOT "cut"). The clearest planted
# conflict is scene 3: two stakeholders say trim/cut while the coverage implicitly
# preserves it. We model the explicit, defensible contradictions.
# ---------------------------------------------------------------------------
GOLDEN_CONFLICTS = [
    # Scene 5 is the planted conflict: the director (Nadia) wants the dinner scene
    # CUT while the producer, manager and coverage reader all want it EXPANDED.
    # That is genuine OPPOSING guidance on the same beat -> a real conflict.
    # (Scene 5 among producer/manager/coverage alone is AGREEMENT, deliberately
    #  NOT a conflict, to test false-positive resistance.)
    ("c01", 5, "Nadia (director_email)", "n21",
     "Margaret (producer_email)", "n12", "Structural"),
    ("c02", 5, "Nadia (director_email)", "n21",
     "Dev (agent_email)", "n13", "Structural"),
    ("c03", 5, "Nadia (director_email)", "n21",
     "Coverage #4421 (pdf_coverage)", "n14", "Structural"),
]

# Category distribution summary (handy for the README / eval report).
CATEGORY_COUNTS = {}
for _nid, _f, _t, _a, _txt, cat, _sev, _sc in GOLDEN_CATEGORIES:
    CATEGORY_COUNTS[cat] = CATEGORY_COUNTS.get(cat, 0) + 1


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def _render_pdf_coverage(path: Path) -> None:
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", "", 11)
    for line in COVERAGE_TEXT.splitlines():
        if not line.strip():
            pdf.ln(3)  # preserve blank-line spacing without feeding empty text
            continue
        pdf.multi_cell(190, 5, line)
    pdf.output(str(path))


def _render_scanned_pdf(path: Path) -> None:
    """A valid PDF with a page but NO text layer (image-only) -> triggers OCR-fail flag."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    # Draw text as pixels so there is visual content but no extractable text layer.
    d.text((100, 100), "SCANNED COVERAGE REPORT (image only)", fill="black")
    d.text((100, 140), "The dinner scene should be expanded.", fill="black")
    tmp_img = path.with_suffix(".scan.png")
    img.save(tmp_img)
    pdf = FPDF(unit="pt", format=(1240, 1754))
    pdf.add_page()
    pdf.image(str(tmp_img), x=0, y=0, w=1240, h=1754)
    pdf.output(str(path))
    tmp_img.unlink(missing_ok=True)


def main() -> None:
    (HERE / "script_the_last_lighthouse.txt").write_text(SCREENPLAY)
    (HERE / "producer_email.eml").write_text(PRODUCER_EMAIL)
    (HERE / "manager_email.eml").write_text(MANAGER_EMAIL)
    (HERE / "director_email.eml").write_text(DIRECTOR_EMAIL)
    (HERE / "coverage_report.pdf").write_bytes(b"")  # placeholder, overwritten below
    _render_pdf_coverage(HERE / "coverage_report.pdf")
    _render_scanned_pdf(HERE / "coverage_scanned.pdf")
    (HERE / "feedback_corrupted.pdf").write_bytes(CORRUPTED_PDF)

    # Golden labels as a Python module (importable) and a JSON mirror (eval harness).
    labels_py = _render_labels_py()
    (HERE / "golden_labels.py").write_text(labels_py)
    _render_labels_json()

    # Manifest / README
    (HERE / "README.md").write_text(_render_readme())

    print(f"Golden dataset written to {HERE}")
    print(f"  script_the_last_lighthouse.txt  ({len(SCREENPLAY.splitlines())} lines)")
    print(f"  producer_email.eml / manager_email.eml / director_email.eml / coverage_report.pdf / feedback_corrupted.pdf")
    print(f"  golden_labels.py + golden_labels.json  ({len(GOLDEN_CATEGORIES)} notes, "
          f"{len(GOLDEN_CONFLICTS)} conflicts)")
    print(f"  category counts: {CATEGORY_COUNTS}")


def _render_labels_py() -> str:
    lines = [
        '"""Golden labels for the Agentic Cinema test dataset.',
        '',
        'Imported by the eval harness (tests/eval_harness.py) and the test suites',
        'A-E. Deterministic — do not hand-edit; regenerate via',
        'generate_golden_dataset.py.',
        '"""',
        'from __future__ import annotations',
        '',
        'GOLDEN_CATEGORIES = [',
    ]
    for row in GOLDEN_CATEGORIES:
        lines.append(f"    {row!r},")
    lines.append(']')
    lines.append('')
    lines.append('GOLDEN_CONFLICTS = [')
    for row in GOLDEN_CONFLICTS:
        lines.append(f"    {row!r},")
    lines.append(']')
    lines.append('')
    lines.append('CATEGORY_COUNTS = ' + repr(CATEGORY_COUNTS))
    lines.append('')
    lines.append('SCRIPT_TITLE = "The Last Lighthouse — Draft 1"')
    lines.append('EXPECTED_PROJECT_ID = "the-last-lighthouse-draft-1"')
    lines.append('')
    lines.append('VALID_CATEGORIES = ["structure", "character", "dialogue", '
                 '"pacing", "logic", "format", "other"]')
    lines.append('VALID_SEVERITIES = ["high", "medium", "low"]')
    lines.append('')
    return "\n".join(lines) + "\n"


def _render_labels_json() -> None:
    import json

    payload = {
        "script_title": "The Last Lighthouse — Draft 1",
        "expected_project_id": "the-last-lighthouse-draft-1",
        "categories": [
            {
                "note_id": r[0], "source_file": r[1], "source_type": r[2],
                "author": r[3], "raw_text": r[4],
                "expected_category": r[5], "expected_severity": r[6],
                "scene_number": r[7],
            }
            for r in GOLDEN_CATEGORIES
        ],
        "conflicts": [
            {
                "conflict_id": r[0], "scene_number": r[1],
                "stakeholder_a": r[2], "note_a_id": r[3],
                "stakeholder_b": r[4], "note_b_id": r[5],
                "conflict_type": r[6],
            }
            for r in GOLDEN_CONFLICTS
        ],
        "category_counts": CATEGORY_COUNTS,
    }
    (HERE / "golden_labels.json").write_text(json.dumps(payload, indent=2))


def _render_readme() -> str:
    return f"""# Golden Test Dataset — "The Last Lighthouse"

Synthetic screenplay + 4 labeled external feedback docs used by the eval harness
and test suites A–E. Regenerate with `python generate_golden_dataset.py`.

## Files
- `script_the_last_lighthouse.txt` — 7-scene synthetic screenplay.
- `producer_email.eml` / `manager_email.eml` — two stakeholder emails (.eml/.txt).
- `coverage_report.pdf` — PDF coverage report (rendered via fpdf2).
- `feedback_corrupted.pdf` — truncated/garbage bytes (tests parser robustness / OCR-fail flag).
- `golden_labels.py` / `golden_labels.json` — deterministic golden labels.

## Golden labels
- **{len(GOLDEN_CATEGORIES)} notes** across categories {sorted(set(r[5] for r in GOLDEN_CATEGORIES))}.
- **{len(GOLDEN_CONFLICTS)} planted conflict pairs** (scene 3: trim/cut disagreement).
- Category distribution: {CATEGORY_COUNTS}

## Conflict design
The clearest cross-stakeholder contradiction is **scene 3**: the producer says
"tighten" (keep, shorten) and the manager says "cut entirely", while coverage
flags it as merely dragging (pacing) — two materially different dispositions on
the same scene. Scene 5 (expand the dinner) is *agreement* across all three
readers and is intentionally NOT a conflict, to test false-positive resistance.
"""


if __name__ == "__main__":
    main()
