"""Agent tool definitions for the Script Notes-to-Outline Matrix Agent.

Each tool maps directly to a step in the locked idea's pipeline:
  parse_notes -> categorize -> map to scenes -> flag conflicts -> checklist,
and a ClickHouse persistence/analytics step that satisfies the hackathon's
ACTIVE RUNTIME requirement (via src.clickhouse.client, which drives mcp-clickhouse).

The agent itself (Gemini) performs the categorization/conflict reasoning from the
parsed raw text; the tools own deterministic I/O (ingestion + ClickHouse).
"""
from __future__ import annotations

from google.adk.tools import FunctionTool

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.pdf_parser import parse_pdf, parse_email
from src.clickhouse import client as ch


def parse_notes(file_path: str) -> list[str]:
    """Parse an external feedback file (PDF coverage or .eml/.txt producer/agent email)
    into a list of raw note lines. Returns the raw lines for the agent to categorize."""
    p = str(file_path)
    if p.lower().endswith(".pdf"):
        return parse_pdf(p)
    return parse_email(p)


def _s(v) -> str:
    """Coerce any value to a safe string (None -> '') for DB insertion."""
    return "" if v is None else str(v)


def write_clickhouse(script_title: str, notes: list[dict]) -> dict:
    """Persist a script's categorized notes + detected conflicts into ClickHouse via
    mcp-clickhouse and return live relational analytics.

    notes: list of {raw_text, note_type, character, scene_ref, severity, scene_id?,
    scene_heading?, source_type?, source_author?}. The notes may be partially
    structured (the LLM often emits scene/character as free text inside raw_text).
    We always derive a scene key from BOTH structured fields and the raw text so
    conflict detection never silently misses pairs that the model wrote as prose.

    This is the ACTIVE runtime ClickHouse step (ClickHouse partner track)."""
    ch.init_schema()
    project_id = ch.slugify_project(script_title)
    draft_version = 1
    for n in notes or []:
        raw = _s(n.get("raw_text"))
        if not raw.strip():
            continue  # skip empties the model may emit
        scene_num = _resolve_scene_num(n, raw)
        ch.insert_note(
            project_id=project_id,
            draft_version=draft_version,
            source_type=_s(n.get("source_type", "unknown")),
            source_author=_s(n.get("source_author", "unknown")),
            scene_number=scene_num,
            scene_heading=_s(n.get("scene_heading")),
            category=_s(n.get("note_type", "Other")),
            severity=_s(n.get("severity", "Minor")),
            raw_note_text=raw,
        )

    # Persist detected conflicts so Query 1's LEFT JOIN returns non-zero conflict counts.
    # detect_conflicts now reads scene keys from raw text too, so prose-only notes
    # (e.g. "the opening scene drags" vs "let the opening breathe") are matched.
    detected = detect_conflicts(notes)
    for c in detected:
        na = notes[c["note_a_idx"]]
        nb = notes[c["note_b_idx"]]
        scene_num = _resolve_scene_num(na, _s(na.get("raw_text"))) or _resolve_scene_num(
            nb, _s(nb.get("raw_text")))
        ch.insert_conflict(
            project_id=project_id,
            draft_version=draft_version,
            scene_number=scene_num,
            stakeholder_a=_s(na.get("source_author", "Source A")),
            note_a=_s(na.get("raw_text"))[:500],
            stakeholder_b=_s(nb.get("source_author", "Source B")),
            note_b=_s(nb.get("raw_text"))[:500],
            conflict_type="Unspecified",
        )

    return {"project_id": project_id, "draft_version": draft_version,
            "analytics": ch.analytics_for(project_id, draft_version)}


# --- scene key resolution (structured field OR prose) -----------------------
_SCENE_RE = __import__("re").compile(r"(?:scene|act|seq|sequence)\s*#{0,1}\s*(\d+)", __import__("re").IGNORECASE)
_WORD_SCENES = ("opening", "intro", "dinner", "climax", "fade", "final", "third act", "act 2", "act two", "middle")


def _resolve_scene_num(note: dict, raw: str) -> int:
    """Scene number from structured fields, else parse it out of the raw text.

    Returns an integer scene key (0 == unmapped) so notes about the same narrative
    beat — whether the model labeled it 'scene_ref: 1' or wrote 'the opening scene' —
    collide on the same grouping key and get conflict-checked together."""
    for key in ("scene_number", "scene_ref", "scene_id"):
        v = _s(note.get(key))
        if v.isdigit():
            return int(v)
    m = _SCENE_RE.search(raw or "")
    if m:
        return int(m.group(1))
    low = (raw or "").lower()
    for i, w in enumerate(_WORD_SCENES, start=1):
        if w in low:
            return 900 + i  # stable synthetic key for named-but-unnumbered beats
    return 0


_re = __import__("re")
# Standard screenplay scene heading: optional leading scene number, then INT./EXT.
# (or I/E). Examples: "INT. DINING ROOM - NIGHT", "5. INT. DINING ROOM - NIGHT",
# "EXT. COASTAL CLIFF - DAWN". Also accept explicit "SCENE n" headings.
_SLUGLINE_RE = _re.compile(
    r"^\s*(?:\d+\.\s*)?(?:INT|EXT|INT\.?/EXT|I/E)[\.\s]", _re.IGNORECASE)
_SCENE_HEADING_RE = _re.compile(r"^\s*scene\s+#?(\d+)\b", _re.IGNORECASE)


def parse_screenplay_scenes(script_text: str) -> list[dict]:
    """Parse a screenplay into an ordered list of scenes.

    Recognizes both numbered 'SCENE n' headings and standard sluglines
    (INT./EXT. ...). Scenes are numbered 1..N in the order they appear. Returns
    [{scene_number, heading}]. This is the authoritative list of scenes that
    actually EXIST in the script — the cross-check uses it to catch feedback that
    references a scene the script does not contain.
    """
    scenes: list[dict] = []
    for line in (script_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _SCENE_HEADING_RE.match(stripped)
        if m:
            scenes.append({"scene_number": int(m.group(1)), "heading": stripped})
            continue
        if _SLUGLINE_RE.match(stripped):
            scenes.append({"scene_number": len(scenes) + 1, "heading": stripped})
    # If explicit numbers were used, honor them; otherwise the positional numbers
    # assigned above already form 1..N.
    return scenes


def cross_check_script_scenes(script_text: str, notes: list[dict]) -> dict:
    """Cross-check feedback notes against the scenes that actually exist in the script.

    Board task t_4f0e8c7c. For every note we resolve its target scene and classify:
      - matched:     the note points at a real scene number in the script.
      - unmapped:    the note could not be tied to any scene (scene 0) — vague note,
                     surfaced but NOT treated as a script mismatch.
      - out_of_range: the note references a scene number the script does NOT contain
                     (e.g. 'rewrite scene 99' when the script has 7 scenes). This is a
                     genuine script-vs-notes mismatch a writer must reconcile, never
                     silently dropped or forced onto a real scene.

    Returns {n_scenes, scene_numbers, matched:[...], unmapped:[...], out_of_range:[...]},
    where each list holds {note_index, scene_number, raw_text}. Fully deterministic.
    """
    scenes = parse_screenplay_scenes(script_text)
    valid = {s["scene_number"] for s in scenes}
    result: dict = {
        "n_scenes": len(scenes),
        "scene_numbers": sorted(valid),
        "matched": [],
        "unmapped": [],
        "out_of_range": [],
    }
    for idx, n in enumerate(notes or []):
        raw = _s(n.get("raw_text"))
        scene_num = _resolve_scene_num(n, raw)
        entry = {"note_index": idx, "scene_number": scene_num, "raw_text": raw}
        if scene_num == 0:
            result["unmapped"].append(entry)
        elif scene_num in valid:
            result["matched"].append(entry)
        else:
            # A synthetic word-scene key (900+) that has no real numbered scene, or a
            # numeric reference beyond the script's range, is a mismatch.
            result["out_of_range"].append(entry)
    return result


def persist_from_raw(script_title: str, raw_lines: list[str],
                     source_type: str = "producer_email",
                     source_author: str = "Producer Email") -> dict:
    """Deterministic, LLM-free persistence path.

    Caller (web route / demo runner) passes already-parsed note lines; we categorize
    with lightweight heuristics and GUARANTEE the write to ClickHouse runs (no
    dependence on the model choosing to call a tool). Returns the same analytics dict
    as write_clickhouse so it is a drop-in for caller-driven persistence.

    Used as the authoritative persist path so the live ClickHouse story is always true,
    even when the LLM is unavailable/rate-limited or forgets to call the tool."""
    ch.init_schema()
    project_id = ch.slugify_project(script_title)
    draft_version = 1

    categorized = _heuristic_categorize(raw_lines)
    for cat in categorized:
        ch.insert_note(
            project_id=project_id,
            draft_version=draft_version,
            source_type=source_type,
            source_author=source_author,
            scene_number=cat["scene_number"],
            scene_heading="",
            category=cat["category"],
            severity=cat["severity"],
            raw_note_text=cat["raw_text"],
        )

    detected = detect_conflicts(categorized)
    for c in detected:
        na = categorized[c["note_a_idx"]]
        nb = categorized[c["note_b_idx"]]
        scene_num = na["scene_number"] or nb["scene_number"]
        ch.insert_conflict(
            project_id=project_id,
            draft_version=draft_version,
            scene_number=scene_num,
            stakeholder_a=source_author,
            note_a=na["raw_text"][:500],
            stakeholder_b=source_author,
            note_b=nb["raw_text"][:500],
            conflict_type="Unspecified",
        )

    return {"project_id": project_id, "draft_version": draft_version,
            "analytics": ch.analytics_for(project_id, draft_version),
            "note_count": len(categorized), "conflict_count": len(detected)}


# --- lightweight heuristics (no LLM) -----------------------------------------
_CAT_RE = __import__("re").compile(
    r"\b(pacing|dialogue|structure|character|logic|format|tone|plot|theme)\b",
    __import__("re").IGNORECASE)
_SEV_WORDS = {"urgent": "high", "critical": "high", "must": "high", "tighten": "high",
              "cut": "high", "fix": "high", "expand": "medium", "more": "medium",
              "raise": "medium", "loved": "low", "great": "low", "overall": "low"}


def _heuristic_categorize(raw_lines: list[str]) -> list[dict]:
    """Cheap structural parse used only for guaranteed persistence (not the LLM plan).

    Matches the schema's category set; severity inferred from cue words; scene key from
    text. This keeps a faithful, queryable matrix in ClickHouse even with no LLM."""
    out: list[dict] = []
    for line in raw_lines or []:
        text = _s(line).strip()
        if not text:
            continue
        low = text.lower()
        m = _CAT_RE.search(text)
        category = m.group(1).capitalize() if m else "Other"
        severity = "medium"
        for w, sev in _SEV_WORDS.items():
            if w in low:
                severity = sev
                break
        out.append({
            "raw_text": text,
            "note_type": category,
            "category": category,
            "severity": severity,
            "scene_number": _resolve_scene_num({}, text),
            "source_type": "producer_email",
            "source_author": "Producer Email",
            # Low-confidence flag: when no keyword cue was found we fall back to
            # 'Other'. That is a SOFT miss, never a confident wrong answer — callers
            # must surface it rather than present it as certain (board task t_464f6b3b).
            "low_confidence": m is None,
        })
    return out


def query_analytics(project_id: str, draft_version: int = 1) -> dict:
    """Return live ClickHouse relational analytics for a project: scene revision density,
    stakeholder disagreement, and draft progress. Demonstrates ClickHouse as an
    analytical engine (ClickHouse partner track)."""
    return ch.analytics_for(project_id, draft_version)


# Directional guidance cues used to decide whether two notes *oppose* each other
# on the same beat. A real conflict is opposing guidance (cut vs expand), not mere
# agreement or two different observations about one scene.
_EXPAND_CUES = ("expand", "more", "longer", "add", "raise", "give", "breathe", "develop", "deepen")
_CUT_CUES = ("cut", "tighten", "trim", "shorten", "reduce", "remove", "less", "shrink", "drop")
_SELF_CUE = ("again", "still", "as i said", "reiterate")


def _guidance(text: str) -> str:
    """Return 'expand' | 'cut' | 'neutral' based on the strongest directional cue."""
    low = (text or "").lower()
    expand = sum(1 for c in _EXPAND_CUES if c in low)
    cut = sum(1 for c in _CUT_CUES if c in low)
    if cut > expand:
        return "cut"
    if expand > cut:
        return "expand"
    return "neutral"


def detect_conflicts(notes: list[dict]) -> list[dict]:
    """Heuristic pre-flag of likely conflicting notes.

    A pair is flagged as a conflict ONLY when BOTH hold:
      (1) they resolve to the SAME scene/character key (via structured fields or the
          raw text — so prose-only notes like "the opening drags" vs "let the opening
          breathe" still collide), AND
      (2) they carry OPPOSING directional guidance (one says cut/tighten, the other
          says expand/more) on that beat — i.e. a genuine stakeholder disagreement.

    This deliberately avoids the false positives the naive "any two different lines in
    a scene" rule produced:
      - agreement (two readers both say "expand the dinner scene") is NOT a conflict;
      - a single reviewer restating their own note is NOT a self-conflict;
      - two different concerns on one scene (dialogue vs pacing) are NOT a conflict
        unless they are literally opposing on the same action.

    Returns a list of {note_a_idx, note_b_idx, reason}.
    """
    clashes: list[dict] = []
    by_key: dict[str, list[int]] = {}
    for i, n in enumerate(notes):
        key = str(_resolve_scene_num(n, _s(n.get("raw_text")))) or "general"
        by_key.setdefault(key, []).append(i)

    for key, idxs in by_key.items():
        if key == "general":
            # The catch-all bucket still needs explicit opposition to count.
            pass
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                na, nb = notes[idxs[a]], notes[idxs[b]]
                ta, tb = _s(na.get("raw_text")), _s(nb.get("raw_text"))
                # Never self-flag a reviewer restating themselves.
                if ta == tb:
                    continue
                if any(c in ta.lower() for c in _SELF_CUE) and any(c in tb.lower() for c in _SELF_CUE):
                    continue
                ga, gb = _guidance(ta), _guidance(tb)
                if ga == "neutral" or gb == "neutral":
                    continue  # no opposing direction -> not a conflict (agreement or side notes)
                if ga == gb:
                    continue  # same direction (e.g. both "expand") == agreement, not conflict
                clashes.append({
                    "note_a_idx": idxs[a], "note_b_idx": idxs[b],
                    "reason": f"Opposing guidance on '{key}': "
                              f"'{ga}' vs '{gb}'.",
                })
    return clashes


def build_checklist(notes: list[dict], conflicts: list[dict],
                    known_scenes: set[int] | None = None) -> list[dict]:
    """Assemble a scene-by-scene Draft-2 revision checklist.

    Contract (board task t_269b581e):
      - ZERO hallucination: every emitted item carries the verbatim source raw_text
        and its source note index, so it is traceable to a real ingested note.
      - Grouped by the RESOLVED integer scene number (via _resolve_scene_num), not a
        free-text field that the heuristic path never populates.
      - Upstream-first ordering: within a scene, structure/logic (story-level) come
        before pacing/character before dialogue/format (line-level); ties broken by
        severity.
      - Vague / unmapped notes (scene 0, i.e. no scene could be resolved) are surfaced
        in a separate 'Unassigned' group, never silently dropped or misassigned.
      - Notes referencing a scene number NOT in known_scenes (out-of-range) are
        flagged 'unresolvable' in their item text and grouped under 'Out-of-range',
        never dropped or merged into a real scene.

    Returns a list of {scene, scene_number, items:[{text, source_index, raw_text,
    category, severity, unresolvable}], conflicts:[...]}.
    """
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    # Upstream-first: story-level categories sort before line-level.
    cat_rank = {"structure": 0, "logic": 1, "pacing": 2, "character": 3,
                "dialogue": 4, "format": 5, "other": 6}

    def _scene_key(n: dict) -> int:
        for k in ("scene_number", "scene_ref", "scene_id"):
            v = _s(n.get(k))
            if v.isdigit():
                return int(v)
        return _resolve_scene_num(n, _s(n.get("raw_text")))

    # Bucket notes by resolved scene, tagging index for traceability.
    buckets: dict[str, list[tuple[int, dict, int]]] = {}
    for idx, n in enumerate(notes):
        scene_num = _scene_key(n)
        if scene_num == 0:
            group = "Unassigned"
        elif known_scenes is not None and scene_num not in known_scenes:
            group = "Out-of-range"
        else:
            group = str(scene_num)
        buckets.setdefault(group, []).append((idx, n, scene_num))

    # Map conflicts to the note indices they involve so we can attach per scene.
    conflict_by_idx: dict[int, list[dict]] = {}
    for c in conflicts or []:
        for key in ("note_a_idx", "note_b_idx"):
            if key in c:
                conflict_by_idx.setdefault(c[key], []).append(c)

    def _sort_key(entry: tuple[int, dict, int]) -> tuple[int, int]:
        _idx, n, _sn = entry
        cat = _s(n.get("note_type") or n.get("category") or "other").lower()
        sev = _s(n.get("severity") or "medium").lower()
        return (cat_rank.get(cat, 6), sev_rank.get(sev, 3))

    def _group_order(name: str) -> tuple[int, int]:
        # Real numbered scenes first (in order), then Unassigned, then Out-of-range.
        if name.isdigit():
            return (0, int(name))
        return ({"Unassigned": 1, "Out-of-range": 2}.get(name, 3), 0)

    checklist = []
    for group in sorted(buckets, key=_group_order):
        entries = sorted(buckets[group], key=_sort_key)
        items = []
        scene_conflicts: list[str] = []
        for idx, n, scene_num in entries:
            unresolvable = group == "Out-of-range"
            raw = _s(n.get("raw_text"))
            cat = _s(n.get("note_type") or n.get("category") or "other")
            sev = _s(n.get("severity") or "medium")
            prefix = "[UNRESOLVABLE scene ref] " if unresolvable else ""
            items.append({
                "text": f"{prefix}[{sev}] {cat}: {raw[:160]}",
                "source_index": idx,      # traceability -> notes[idx]
                "raw_text": raw,          # verbatim source, zero hallucination
                "category": cat,
                "severity": sev,
                "scene_number": scene_num,
                "unresolvable": unresolvable,
            })
            for c in conflict_by_idx.get(idx, []):
                reason = c.get("reason", "conflict")
                if reason not in scene_conflicts:
                    scene_conflicts.append(reason)
        scene_number = int(group) if group.isdigit() else None
        checklist.append({
            "scene": group,
            "scene_number": scene_number,
            "items": items,
            "conflicts": scene_conflicts,
        })
    return checklist


# ADK FunctionTool wrappers (the agent can call these at runtime).
parse_notes_tool = FunctionTool(parse_notes)
write_clickhouse_tool = FunctionTool(write_clickhouse)
query_analytics_tool = FunctionTool(query_analytics)
detect_conflicts_tool = FunctionTool(detect_conflicts)
build_checklist_tool = FunctionTool(build_checklist)
cross_check_script_scenes_tool = FunctionTool(cross_check_script_scenes)

ALL_TOOLS = [
    parse_notes_tool,
    detect_conflicts_tool,
    build_checklist_tool,
    cross_check_script_scenes_tool,
    write_clickhouse_tool,
    query_analytics_tool,
]
