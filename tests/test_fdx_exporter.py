"""Tests for the FDX exporter (native <ScriptNote> format interchange to Final Draft)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.exporters import fdx


SAMPLE_FDX = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" SchemaVersion="1">
  <Content>
    <Paragraph>
      <Type>Scene Heading</Type>
      <Text>5. INT. DINING ROOM - NIGHT</Text>
    </Paragraph>
    <Paragraph>
      <Type>Action</Type>
      <Text>Maya and Daniel argue.</Text>
    </Paragraph>
    <Paragraph>
      <Type>Scene Heading</Type>
      <Text>7. EXT. ROOFTOP - DAY</Text>
    </Paragraph>
  </Content>
</FinalDraft>"""

CHECKLIST_A = [
    {"scene": "5", "items": ["[high] structure: expand the dinner scene"], "conflicts": ["Exec A vs Exec B on subplot"]},
    {"scene": "7", "items": ["[low] pacing: fine"], "conflicts": []},
]

RICH_CHECKLIST = [
    {"scene_num": 5, "category": "Character", "conflict_flagged": True,
     "summary_note": "cut the subplot", "action_item": "reconcile exec notes"},
]


def test_standalone_summary_is_valid_fdx_with_scriptnote():
    out = fdx.generate_standalone_fdx_notes_summary(CHECKLIST_A)
    assert out.strip().startswith("<?xml")
    assert "ScriptNote" in out, "must use native <ScriptNote>, not Action paragraphs"
    assert "REVISION NOTE" in out
    import xml.etree.ElementTree as ET
    root = ET.fromstring(out)
    assert root.tag.endswith("FinalDraft")
    # ScriptNote is present and non-printing (no 'Action' paragraph carrying our notes)
    assert any(el.tag.endswith("ScriptNote") for el in root.iter())


def test_inject_uses_native_scriptnote_not_action():
    out = fdx.inject_matrix_notes_to_fdx(SAMPLE_FDX, CHECKLIST_A)
    assert "ScriptNote" in out
    assert "FLAGGED CONFLICTS" in out
    assert "Exec A vs Exec B" in out
    import xml.etree.ElementTree as ET
    root = ET.fromstring(out)
    # scene 5 heading preserved
    assert any((t.text or "").startswith("5. INT") for t in root.iter() if t.text)
    # notes are attached as ScriptNote children of the heading, not as Action paragraphs
    notes = [el for el in root.iter() if el.tag.endswith("ScriptNote")]
    assert notes, "no <ScriptNote> emitted"
    # None of our note text should appear inside a printable Action/Dialogue paragraph
    for p in root.iter():
        if p.tag.endswith("Paragraph"):
            ptype = p.find("Type")
            if ptype is not None and ptype.text in ("Action", "Dialogue"):
                txt = " ".join(t.text or "" for t in p.iter("Text"))
                assert "Exec A vs Exec B" not in txt


def test_rich_shape_accepted():
    out = fdx.inject_matrix_notes_to_fdx(SAMPLE_FDX, RICH_CHECKLIST)
    assert "ScriptNote" in out
    assert "FLAGGED CONFLICTS" in out
    assert "Category: Character" in out


def test_inject_empty_fdx_raises():
    import pytest
    with pytest.raises(ValueError):
        fdx.inject_matrix_notes_to_fdx("", CHECKLIST_A)


def test_parse_agent_text_to_checklist():
    text = "Scene 5: expand the dinner scene. Scene 14: cut the subplot — execs conflict on this."
    parsed = fdx.parse_agent_text_to_checklist(text)
    assert parsed[0]["scene_num"] == 5
    assert parsed[1]["scene_num"] == 14
    assert parsed[1]["conflict_flagged"] is True
    # fallback when no scene markers
    fb = fdx.parse_agent_text_to_checklist("just some vague notes")
    assert fb[0]["scene_num"] == 1
