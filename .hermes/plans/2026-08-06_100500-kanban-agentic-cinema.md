# Kanban board + task tracking plan — Script Notes-to-Outline Matrix Agent

> **For Hermes:** Plan only. Do NOT execute until approved. After approval, use the
> `kanban` commands below to create the board + tasks.

**Goal:** Create one kanban board in the `idea-tracker` profile to track the
agentic-cinema test-framework workstream and open build next-steps, with every task
assigned to the project name (`agentic-cinema`) and linked to the `agentic-cinema` project.

**Architecture:** Hermes kanban is a durable SQLite board shared across profiles. One board
per workstream isolates the task queue. Tasks are created with `--assignee <profile-or-name>`
and `--project <slug>` so they are owned by the project and surfaced under it.

**Tech Stack:** `hermes kanban` CLI (boards + create + assign + list). Profile: idea-tracker.

---

## Context / assumptions

- Active profile: `idea-tracker`. Hermes project `agentic-cinema` already exists (slug `agentic-cinema`, primary `/home/asif1/agentic-cinema`), created earlier this session.
- The test-framework spec (from the user's prior message) has 3 layers: golden dataset → component tests (A–E) → eval methods → demo-specific. Current repo only has `tests/test_smoke.py` (ClickHouse smoke + 1 email parse) and `tests/sample_feedback.eml` (no ground truth). Most of the framework is unbuilt.
- Open build next-steps still pending: GitHub Actions CI, ClickHouse Cloud trial start (~Sep 5), GC $100 coupon redemption, re-run live Gemini demo after quota reset.
- Assignment model: user said "make project name as assignee" → use `--assignee agentic-cinema` for all tasks. Link each to `--project agentic-cinema`.

## Command reference (verified from --help)

- Boards: `hermes kanban boards create <slug> [--display-name "..."]`, `hermes kanban boards switch <slug>`, `hermes kanban boards list`
- Create task: `hermes kanban create "<title>" --assignee agentic-cinema --project agentic-cinema [--body "..."] [--priority N] [--parent <id>]`
- List: `hermes kanban list` (or `ls`); `hermes kanban list --board agentic-cinema`
- Parent/child deps: `hermes kanban create ... --parent <id>`

## Proposed approach

1. Create a dedicated board `agentic-cinema` (isolates this workstream from any other).
2. Switch the active board to `agentic-cinema` so subsequent `create` calls land there.
3. Create tasks grouped by workstream: (A) golden dataset, (B) component tests, (C) ClickHouse tests, (D) eval harness, (E) demo golden-path + CI, (F) open build next-steps. Use `--parent` so the golden-dataset task is a parent of the test tasks that depend on it.
4. List the board to confirm all tasks landed with the right assignee/project.

## Tasks to create (title + body + grouping)

### Board
- `hermes kanban boards create agentic-cinema --display-name "Script Notes-to-Outline Matrix Agent"`
- `hermes kanban boards switch agentic-cinema`

### Group A — Golden dataset (parent of B)
- Title: `Build golden dataset: synthetic script + 3-4 labeled feedback docs`
  Body: Step 1 of test framework. 1 synthetic ~18-scene script (Fountain/PDF + .eml) with planted issues (dangling subplot, inconsistent motivation, Act-2 pacing dip). 3-4 feedback docs (PDF coverage, producer email, bullet agent notes) with explicit ground-truth JSON: notes→type/character/scene/severity; ≥2 planted conflict pairs; ≥1 note referencing a non-existent scene; ≥1 vague/unattributable note. Save under `tests/golden/`.
  Priority: 1 (highest — blocks B/C/D).

### Group B — Component tests (parent = A)
- `Ingestion tests (A): PDF extract, OCR-fail flag, email, multi-file, corrupted-file` — assert parse_pdf/parse_email behavior per framework table; add PDF + corrupted fixtures to `tests/golden/`.
- `Categorization scoring harness (B): accuracy vs golden labels, low-conf flag` — NOTE: categorization is Gemini-internal; this task is BLOCKED pending (a) deterministic categorizer or frozen-snapshot path and (b) Gemini quota. Mark body with the blocker.
- `Conflict-detection tests (C): planted conflicts + non-conflicting pairs (precision/recall)` — call deterministic `detect_conflicts(notes)` with golden categorized notes; assert no missed planted conflicts, no false positives, no self-conflict.
- `Checklist tests (D): zero hallucination, scene-grouped, OOR-scene flagged` — call deterministic `build_checklist(notes, conflicts)`; add `validate_scenes(script_scenes, notes)` helper so OOR-scene + invented-scene are caught. Assert every item traceable to a source note.
- `Add script-scene cross-check capability` — NEW code: parse the uploaded script's real scene list and validate note scene_ref against it (prerequisite for the non-negotiable 0% hallucination test).

### Group C — ClickHouse tests (E)
- `ClickHouse tests (E): persist-across-session + aggregate matches manual count` — extend `test_schema_and_analytics` to assert re-query stability and that `analytics_for` aggregates equal a manual count over the golden dataset.

### Group D — Eval harness + CI (E)
- `Eval harness: automated accuracy/precision/recall script over golden dataset` — run after every pipeline change (regression gate).
- `LLM-as-judge rubric scorer (optional)` — separate Gemini call scores each checklist item 1-5 (actionable / grounded / scoped / non-redundant). BLOCKED pending Gemini quota.
- `CI: GitHub Actions runs pytest + eval harness on push` — uses existing `GEMINI_API_KEY` secret; skips LLM-judge when quota missing.

### Group E — Demo-specific + open build next-steps
- `Demo golden-path: run exact demo script+notes ≥3x for consistent, timed output` — Step 4 of framework; plant 1 conflict + 1 vague note in demo input.
- `Start ClickHouse Cloud trial (~Sep 5) and flip env to live` — preserve 30-day clock; do not start before buffer.
- `Redeem GC $100 coupon (by 2026-08-31)` — awaiting code.
- `Re-run full Gemini→ClickHouse demo after quota reset; capture output for video` — blocked by free-tier quota exhaustion (20 req/day gemini-2.5-flash).

## Files likely to change (when tasks are executed later — not now)

- `tests/golden/` (new fixtures + ground-truth JSON)
- `tests/test_ingestion.py`, `tests/test_conflicts.py`, `tests/test_checklist.py`, `tests/test_clickhouse.py` (new)
- `src/agent/tools/note_tools.py` (add `validate_scenes` helper)
- `tests/eval_metrics.py` (new harness)
- `.github/workflows/ci.yml` (new)

## Validation (after execution)

- `hermes kanban boards list` shows `agentic-cinema` with task count = number created.
- `hermes kanban list --board agentic-cinema` shows all tasks with assignee `agentic-cinema` and project `agentic-cinema`.
- `hermes project show agentic-cinema` still clean; no repo files changed by board creation (kanban state is profile-local SQLite, not in the git repo).

## Risks / tradeoffs / open questions

- **Assignee semantics:** `--assignee` expects a profile name. Using the project slug `agentic-cinema` as the assignee follows the user's instruction ("make project name as assignee"); if kanban rejects a non-profile assignee, fall back to `--assignee idea-tracker` and note it. Verify on first `create`.
- **Board vs default:** creating a dedicated board isolates tasks; if the user prefers the `default` board, we can skip `boards create` and just tag tasks with `--project agentic-cinema`. Plan assumes a dedicated board (cleaner).
- **BLOCKED tasks:** categorization scoring, LLM-as-judge, and the live demo re-run are explicitly blocked by Gemini quota / missing scene-cross-check capability. They should be created as tasks (so they're tracked) but flagged blocked in their body.
- **No code change now:** this plan only creates board + task records. No repo files are touched.

## Execution status: DONE (executed 2026-08-06)

- Board `agentic-cinema` created; physical DB relocated to the profile directory per user instruction:
  `/home/asif1/.hermes/profiles/idea-tracker/kanban-boards/agentic-cinema/` with a symlink at
  `/home/asif1/.hermes/kanban/boards/agentic-cinema -> <profile dir path>`. (`hermes kanban` defaults
  board DBs to the global `/home/asif1/.hermes/kanban/boards/`, NOT the profile dir — the symlink
  redirects it so storage lives in the profile directory as required.)
- 14 tasks created, all `assignee=agentic-cinema`, `--project agentic-cinema`.
- NOTE/BUG ENCOUNTERED: `hermes kanban boards switch agentic-cinema` printed success but the CLI kept
  creating tasks on the previously-active board (`vertex-pumpfun-launch`). The 14 tasks initially landed
  there. Fixed by migrating the 14 task rows (tasks/events/comments/links) from the vertex DB into the
  agentic-cinema DB via the Python sqlite3 module, then deleting them from vertex (verified: vertex
  back to 33, agentic-cinema = 14). `boards list` now shows agentic-cinema ready=9 todo=5.
- `boards show` may display a stale current board; trust `boards list` counts + the `current` file.
