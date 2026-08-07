# Script Notes-to-Outline Matrix Agent

**Agentic Cinema: The Blockbuster Hackathon — ClickHouse partner track.**

An agentic tool for screenwriters that ingests *external, unstructured* feedback
(PDF coverage reports, producer/agent emails) plus a screenplay, then:

1. **Categorizes** every note by type (structure / character / dialogue / pacing / logic / format), character, and scene.
2. **Flags conflicting** notes (e.g. one reader says "cut the dinner scene", another says "expand it").
3. **Builds a scene-by-scene Draft-2 revision checklist** — highest-severity items first, conflicts called out per scene.
4. **Persists** the notes-matrix + conflict flags into **ClickHouse** via the official
   `mcp-clickhouse` MCP server, and serves **live analytics** (note-category frequencies,
   conflict rates, scene coverage).

Rules-compliant: automates admin/planning only — it **does not** auto-write creative script text.
Built on **Gemini via Google Cloud Vertex AI (Agent Engine)**; ClickHouse is used at **runtime** (not just named).

## Architecture
- **Ingestion** (`src/ingestion`): `pdfplumber` for PDF coverage, email parser for `.eml`/`.txt`.
- **Agent** (`src/agent`, ADK + Gemini on **Vertex AI**): orchestrates parse → categorize → conflicts → checklist → persist.
- **Storage** (`src/clickhouse`): official `mcp-clickhouse` MCP server; schema in `schema.sql`.
  Dev runs on free embedded **chDB**; the live submission flips to **ClickHouse Cloud** via env vars only.
- **Web** (`src/web`, FastAPI on **Cloud Run**): upload → agent runs → categorized notes, conflicts, checklist, analytics.
  In production the web calls the agent **deployed on Vertex AI Agent Engine** (`AGENT_ENGINE_ID`);
  locally it uses an in-process ADK runner. Both use Vertex Gemini.

## Quickstart (local, free — no cloud account needed)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # defaults to embedded chDB (CHDB_ENABLED=true)
python -m src.clickhouse.client   # applies schema, prints OK
uvicorn src.web.app:app --port 8080   # open http://localhost:8080
```

### Gemini / ADK (the reasoning layer)
The agent uses **Gemini via Google ADK on Vertex AI** (the only permitted AI vendor per the rules).
This build runs on Vertex by default, backed by the hackathon GCP credits:

```bash
GOOGLE_GENAI_USE_VERTEXAI=true
GCP_PROJECT=acinema-hack-0807        # your hackathon GCP project
GCP_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=.sa-key.json   # ADC key (gitignored)
```

Vertex auth uses **Application Default Credentials** (a service-account key, or
`gcloud auth application-default login`) — no Gemini API key is needed, and the
hackathon credits apply, so the `429 RESOURCE_EXHAUSTED` Developer-API cap does not apply.
`run_agent_demo.py tests/sample_feedback.eml` exercises the full flow end-to-end.
To host the live agent, deploy to Vertex AI Agent Engine (see `deploy/deploy_agent.py`);
the web app then calls that remote via `AGENT_ENGINE_ID` in `.env`.

## Live submission (ClickHouse Cloud)
In `.env`, comment out the chDB block and set `CLICKHOUSE_HOST/PORT/USER/PASSWORD/SECURE`
to your ClickHouse Cloud service (the `mcp-clickhouse` server picks these up automatically).
`CLICKHOUSE_ALLOW_WRITE_ACCESS=true` is required; destructive ops (`CLICKHOUSE_ALLOW_DROP`) stay `false`.

## Demo video
See `docs/demo_script.md` for the 3-minute functional-demo walkthrough (upload → checklist → live analytics).

## Repo layout
```
src/agent/        ADK agent + tools
src/clickhouse/   mcp-clickhouse client + schema.sql
src/ingestion/    PDF + email parsers
src/web/          FastAPI app + templates
deploy/           Agent Engine + Cloud Run configs
tests/            pytest
docs/             demo script
references/       vendor repos (mcp-clickhouse) — excluded from submission
```

## License
Apache-2.0 (see `LICENSE`).
