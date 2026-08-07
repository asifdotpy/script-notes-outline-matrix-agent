# Agentic Cinema — Script Notes-to-Outline Matrix Agent

## What it solves (problem → system)

Screenwriters drown in **contradictory, unstructured feedback** from many stakeholders —
producers, executives, script coaches, peers. One reader says "cut the opening," another
says "let it breathe." By Draft 2, those conflicts are either missed (causing rework) or
resolved ad hoc with no audit trail.

**This agent turns messy feedback into a structured, queryable revision matrix:**
it ingests a PDF coverage report or a producer/agent email, categorizes every note
(structure / character / dialogue / pacing / logic / format), flags stakeholder
**conflicts**, builds a scene-by-scene Draft-2 checklist, and **persists everything to
ClickHouse at runtime** via the official `mcp-clickhouse` MCP server. The web UI then
serves live analytics and an `.fdx` (Final Draft) export.

It is built on **Gemini via Google Cloud Vertex AI (Agent Engine)** and uses
**ClickHouse** as a live runtime datastore — satisfying the hackathon's AI + partner
(Google Cloud / ClickHouse) requirements.

---

## Concrete example (real run, captured this session)

### Input — `tests/sample_feedback.eml` (19 lines, "Notes on Draft 1 of The Tunnel")

A producer's email containing, among others, these notes:

> 5. The opening scene drags. You need to cut at least two pages from the intro.
> 7. Actually, I loved the slow build in the opening. Don't rush it; let it breathe.
> 9. The dinner scene between Maya and Daniel needs more tension. Raise the stakes there.
> 11. We should expand the dinner scene — it's the emotional core, give it room.
> 13. Daniel's motivation in Act 2 is unclear. Tighten his arc.
> 15. Format: scene numbers are missing in the middle section. Fix the slug lines.

### What the agent produces

Running `python run_agent_demo.py tests/sample_feedback.eml "The Tunnel — Draft 1"`
on **Vertex AI (Gemini 2.5 Flash)** + **ClickHouse Cloud**:

```
[ingested] 9 raw note lines from sample_feedback.eml

===== AGENT OUTPUT =====

# scenes with notes: 1
# stakeholder disagreement rows: 5
# draft progress rows: 1

Draft-2 revision plan (persisted in ClickHouse via mcp-clickhouse):
See the live analytics panel / notes_matrix view for the full matrix.

[persisted] 9 notes + 3 conflicts written to ClickHouse (project 'the-tunnel-draft-1').
```

### Live data persisted to ClickHouse (query of the real tables)

`notes_raw` (project `the-tunnel-draft-1`), categorized by the agent:

| category  | severity | note (truncated)                                  |
|-----------|----------|---------------------------------------------------|
| pacing    | high     | The opening scene drags. You need to cut …        |
| pacing    | medium   | Actually, I loved the slow build in the opening…  |
| dialogue  | high     | The dinner scene between Maya and Daniel needs…   |
| structure | medium   | We should expand the dinner scene — it's the…     |
| format    | high     | Format: scene numbers are missing in the middle…  |
| other     | high     | Daniel's motivation in Act 2 is unclear…          |

`notes_conflicts` — the contradictions the agent surfaced:

1. **Opening contradiction** — `A: "The opening scene drags. You need to cut at least
   two pages from the intro."` vs `B: "Actually, I loved the slow build in the opening.
   Don't rush it; let it breathe."`
2. **Dinner scene contradiction** — `A: "The dinner scene … needs more tension."` vs
   `B: "We should expand the dinner scene — it's the emotional core, give it room."`

(The third conflict row in the table is a false positive — two non-contradictory
pleasantries — see Limitations.)

### Why this matters

Without the agent, a writer manually reads 9 notes and *hopes* to notice that note 5 and
note 7 directly contradict each other. The agent makes that contradiction a **first-class,
queryable row** in ClickHouse, so the Draft-2 plan can explicitly resolve it ("Opening:
producer wants a trim; you loved the slow build — decide: trim 1 page or keep?") instead
of the writer discovering the clash in a notes meeting.

---

## Architecture (hackathon-aligned)

- **Ingestion** (`src/ingestion`): `pdfplumber` for PDF coverage, email parser for `.eml`.
- **Agent** (`src/agent`, ADK + **Gemini on Vertex AI Agent Engine**): orchestrates
  parse → categorize → conflicts → checklist → persist.
- **Storage** (`src/clickhouse`): official `mcp-clickhouse` MCP server; schema in
  `schema.sql`. Dev runs on free embedded chDB; prod uses **ClickHouse Cloud** (this run).
- **Web** (`src/web`, FastAPI): upload → agent runs (remote Agent Engine in prod) →
  categorized notes, conflicts, checklist, analytics; `.fdx` export.

### Live deployment (verified this session)

- Project `acinema-hack-0807` on Google Cloud, linked to the $100 Agentic Cinema hackathon
  credit (no 429 free-tier cap; Vertex Gemini draws from the credit).
- Agent deployed to **Vertex AI Agent Engine** — resource
  `projects/572921285869/locations/us-central1/reasoningEngines/3590223773304881152`.
  A live `stream_query` returned `REMOTE_OK` / `LIVE`, confirming the hosted agent answers.
- ClickHouse Cloud persistence verified: notes + conflicts written and re-queried.

---

## Limitations (honest scope)

- The agent **categorizes and flags conflicts; it does not write creative script text**
  (compliant with the hackathon's "admin/planning only" rule).
- **Conflict detection is heuristic.** It caught the two real contradictions above, but
  also produced one false positive (two pleasantries flagged as a conflict). Scene-number
  mapping is weak (mostly 0 / synthetic 901/903 rather than real slug lines).
- **Re-runs append rows** — the live `the-tunnel-draft-1` table currently holds 16 note
  rows and 3 conflict rows from repeated demo runs this session, because persistence is
  append-only (no upsert/dedup yet). A production build would key on a stable note hash.
- **ClickHouse Cloud query latency**: one analytics query timed out at 30s on a cold
  connection during the run (the agent fell back to the persisted summary; not fatal, but
  worth a retry/timeout bump).
- **Web agent call is slow** (~1-2 min) because it awaits the remote Agent Engine per
  request; fine for a demo, would need streaming/async UI polish for production traffic.
  (Fixed this session: the `/analyze` endpoint previously crashed with
  `asyncio.run() cannot be called from a running event loop` and dropped the agent text;
  it now `await`s the coroutine and falls back to a ClickHouse-derived summary when the
  deployed agent ends on the `write_clickhouse` tool call.)

---

## How to run

```bash
# Local, free (chDB):
cp .env.example .env            # CHDB_ENABLED=true, GOOGLE_GENAI_USE_VERTEXAI=true
uv pip install -r requirements.txt
python run_agent_demo.py tests/sample_feedback.eml "The Tunnel — Draft 1"

# Web UI (calls deployed Agent Engine when AGENT_ENGINE_ID is set):
uvicorn src.web.app:app --port 8080   # open http://localhost:8080
```

## Deploy the agent to Vertex AI Agent Engine

```bash
export GOOGLE_APPLICATION_CREDENTIALS=.sa-key.json GCP_PROJECT=acinema-hack-0807
python -m deploy.deploy_agent        # writes AGENT_ENGINE_ID to .env
```
