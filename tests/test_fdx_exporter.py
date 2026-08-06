"""Tests for the FDX exporter (format-interchange to Final Draft XML)."""
import sys, os
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

CHECKLIST = [
    {"scene": "5", "items": ["[high] structure: expand the dinner scene", "[med] dialogue: tighten Maya's line"], "conflicts": ["Exec A vs Exec B on subplot"]},
    {"scene": "7", "items": ["[low] pacing: fine"], "conflicts": []},
]


def test_standalone_summary_is_valid_fdx():
    out = fdx.generate_standalone_fdx_notes_summary(CHECKLIST)
    assert out.strip().startswith("<?xml")
    assert "DRAFT-2 REVISION MATRIX" in out
    # round-trips as XML
    fdx._q  # ensure module loaded
    import xml.etree.ElementTree as ET
    root = ET.fromstring(out)
    assert root.tag.endswith("FinalDraft")


def test_inject_into_existing_fdx():
    out = fdx.inject_matrix_notes_to_fdx(SAMPLE_FDX, CHECKLIST)
    assert "MATRIX NOTES" in out
    assert "FLAGGED CONFLICTS" in out
    assert "Exec A vs Exec B" in out
    import xml.etree.ElementTree as ET
    root = ET.fromstring(out)
    # scene 5 heading still present
    headings = [t.text for t in root.iter() if (t.text or "").startswith("5. INT")]
    assert headings, "scene 5 heading lost during injection"


def test_inject_empty_fdx_raises():
    import pytest
    with pytest.raises(ValueError):
        fdx.inject_matrix_notes_to_fdx("", CHECKLIST)


def test_endpoint_contract_shape():
    # the module accepts both build_checklist shape and raw-note dicts
    raw_notes = [{"raw_text": "cut two pages", "note_type": "pacing", "scene_ref": "1", "severity": "high"}]
    out = fdx.generate_standalone_fdx_notes_summary(raw_notes)
    assert "cut two pages" in out
