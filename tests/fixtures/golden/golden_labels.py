"""Golden labels for the Agentic Cinema test dataset.

Imported by the eval harness (tests/eval_harness.py) and the test suites
A-E. Deterministic — do not hand-edit; regenerate via
generate_golden_dataset.py.
"""
from __future__ import annotations

GOLDEN_CATEGORIES = [
    ('n01', 'producer_email.eml', 'producer_email', 'Margaret', 'The opening scene is too slow. We lose the audience in the first two minutes. Cut about a third of scene 1 and get to Ella climbing faster.', 'structure', 'high', 1),
    ('n02', 'manager_email.eml', 'agent_email', 'Dev', "The opening scene is too slow. I'd actually open even later, mid-climb.", 'structure', 'high', 1),
    ('n03', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'Structure: the opening (scene 1) is too slow and risks losing the audience.', 'structure', 'high', 1),
    ('n04', 'producer_email.eml', 'producer_email', 'Margaret', 'Dialogue in scene 2 is on the nose. Make it sharper and less expository.', 'dialogue', 'high', 2),
    ('n05', 'manager_email.eml', 'agent_email', 'Dev', 'Dialogue in scene 2 is on the nose. Agreed with Margaret, sharpen it.', 'dialogue', 'high', 2),
    ('n06', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'Dialogue in scene 2 is on the nose.', 'dialogue', 'high', 2),
    ('n07', 'producer_email.eml', 'producer_email', 'Margaret', 'Scene 3 drags. Tighten the harbor questioning — it runs long.', 'pacing', 'medium', 3),
    ('n08', 'manager_email.eml', 'agent_email', 'Dev', 'Cut scene 3 entirely. The harbor questioning slows the middle.', 'pacing', 'high', 3),
    ('n09', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'Pacing: scene 3 drags and scene 6 is overlong.', 'pacing', 'medium', 3),
    ('n10', 'manager_email.eml', 'agent_email', 'Dev', 'The logic of the archives reveal in scene 4 is murky. How does she know the light was off? Make the clue concrete.', 'logic', 'medium', 4),
    ('n11', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'Logic: the scene 4 archives reveal lacks a concrete clue.', 'logic', 'medium', 4),
    ('n12', 'producer_email.eml', 'producer_email', 'Margaret', 'Expand the dinner scene. Scene 5 is the emotional core and right now it feels rushed. Give the harbormaster more to do.', 'character', 'high', 5),
    ('n13', 'manager_email.eml', 'agent_email', 'Dev', 'Expand the dinner scene. Scene 5 needs more room to breathe; the confrontation is the heart of the movie.', 'character', 'high', 5),
    ('n14', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'The emotional core in the dinner scene (scene 5) lands. Expand it; the confrontation between Ella and the harbormaster is the best writing here.', 'character', 'high', 5),
    ('n15', 'producer_email.eml', 'producer_email', 'Margaret', 'The storm sequence in scene 6 is too long. Trim it by a minute.', 'pacing', 'medium', 6),
    ('n16', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'Pacing: scene 3 drags and scene 6 is overlong.', 'pacing', 'medium', 6),
    ('n17', 'producer_email.eml', 'producer_email', 'Margaret', "Love the ending. Scene 7 is perfect, don't change it.", 'other', 'low', 7),
    ('n18', 'manager_email.eml', 'agent_email', 'Dev', 'I loved scene 7. Keep it exactly as is.', 'other', 'low', 7),
    ('n19', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'The ending (scene 7) is quietly powerful. Do not change it.', 'other', 'low', 7),
    ('n20', 'coverage_report.pdf', 'pdf_coverage', 'Coverage #4421', 'Format: scene headings are inconsistent in a few places.', 'format', 'low', 0),
    ('n21', 'director_email.eml', 'agent_email', 'Nadia', "Cut the dinner scene. Scene 5 stops the film dead — I'd remove it entirely and fold the reveal into the archives.", 'character', 'high', 5),
    ('n22', 'director_email.eml', 'agent_email', 'Nadia', 'Tighten scene 6. The storm is gorgeous but overlong.', 'pacing', 'medium', 6),
    ('n23', 'director_email.eml', 'agent_email', 'Nadia', 'Scene 7 is the reason I want to make this. Keep it untouched.', 'other', 'low', 7),
]

GOLDEN_CONFLICTS = [
    ('c01', 5, 'Nadia (director_email)', 'n21', 'Margaret (producer_email)', 'n12', 'Structural'),
    ('c02', 5, 'Nadia (director_email)', 'n21', 'Dev (agent_email)', 'n13', 'Structural'),
    ('c03', 5, 'Nadia (director_email)', 'n21', 'Coverage #4421 (pdf_coverage)', 'n14', 'Structural'),
]

CATEGORY_COUNTS = {'structure': 3, 'dialogue': 3, 'pacing': 6, 'logic': 2, 'character': 4, 'other': 4, 'format': 1}

SCRIPT_TITLE = "The Last Lighthouse — Draft 1"
EXPECTED_PROJECT_ID = "the-last-lighthouse-draft-1"

VALID_CATEGORIES = ["structure", "character", "dialogue", "pacing", "logic", "format", "other"]
VALID_SEVERITIES = ["high", "medium", "low"]

