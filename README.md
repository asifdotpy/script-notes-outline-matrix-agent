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
Built on **Gemini via Google ADK on Vertex AI (Agent Engine)**; ClickHouse is used at **runtime** (not just named).

## What it does (features)

- **Ingestion of external feedback** — `pdfplumber` for PDF coverage reports, an email parser
  for `.eml`/`.txt` producer/agent notes. Not just in-app comments.
- **Note categorization** — every note tagged by type, character, scene, and severity.
- **Conflict detection** — contradictory stakeholder notes surfaced as first-class conflict rows
  (e.g. "cut the intro" vs "let it breathe").
- **Draft-2 revision checklist** — scene-by-scene, severity-ordered, conflicts highlighted per scene.
- **Runtime ClickHouse persistence** — `notes_raw` + `notes_conflicts` tables via the official
  `mcp-clickhouse` server, with relational analytics (category breakdowns, conflict ratios,
  scene-by-scene note density).
- **Web UI (FastAPI)** — upload → agent runs → categorized notes, conflicts, checklist, analytics,
  plus **`.fdx` (Final Draft) export** of the revision notes.
- **Gemini on Vertex AI Agent Engine** — the agent is deployed to Google Cloud Agent Platform and
  called by the web app in production; verified live this build.

## Architecture

- **Ingestion** (`src/ingestion`): `pdfplumber` for PDF coverage, email parser for `.eml`/`.txt`.
- **Agent** (`src/agent`, ADK + Gemini on **Vertex AI**): orchestrates parse → categorize → conflicts → checklist → persist.
- **Storage** (`src/clickhouse`): official `mcp-clickhouse` MCP server; schema in `schema.sql`.
  Dev runs on free embedded **chDB**; the live submission flips to **ClickHouse Cloud** via env vars only.
- **Web** (`src/web`, FastAPI): upload → agent runs → categorized notes, conflicts, checklist, analytics.
  In production the web calls the agent **deployed on Vertex AI Agent Engine** (`AGENT_ENGINE_ID`);
  locally it uses an in-process ADK runner. Both use Vertex Gemini.
- **Deploy** (`deploy/`): `deploy_agent.py` deploys the agent to Vertex AI Agent Engine;
  `cloud_run.yaml` documents the Cloud Run deploy for the web surface.

## Quickstart (local, free — no cloud account needed)

```bash
# install (uv or pip)
uv sync                 # or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env    # defaults to embedded chDB (CHDB_ENABLED=true)

python -m src.clickhouse.client     # applies schema, prints OK
uvicorn src.web.app:app --port 8080  # open http://localhost:8080
```

`run_agent_demo.py tests/sample_feedback.eml` exercises the full flow end-to-end on the CLI.

### Gemini / ADK (the reasoning layer)

The agent uses **Gemini via Google ADK on Vertex AI** (the only permitted AI vendor per the rules).
This build runs on Vertex by default, backed by the hackathon GCP credits:

```bash
GOOGLE_GENAI_USE_VERTEXAI=true
GCP_PROJECT=acinema-hack-0807        # your hackathon GCP project
GCP_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=.sa-key.json   # Application Default Credentials (gitignored)
```

Vertex auth uses **Application Default Credentials** (a service-account key, or
`gcloud auth application-default login`) — no Gemini API key is needed, and the
hackathon credits apply, so the `429 RESOURCE_EXHAUSTED` Developer-API cap does not apply.

### Live submission (ClickHouse Cloud)

In `.env`, set `CLICKHOUSE_ENABLED=true` and `CHDB_ENABLED=false`, then set
`CLICKHOUSE_HOST/PORT/USER/PASSWORD/SECURE` to your ClickHouse Cloud service
(the `mcp-clickhouse` server picks these up automatically).
`CLICKHOUSE_ALLOW_WRITE_ACCESS=true` is required; destructive ops (`CLICKHOUSE_ALLOW_DROP`) stay `false`.

## Deploy

**Agent → Vertex AI Agent Engine:**

```bash
export GOOGLE_APPLICATION_CREDENTIALS=.sa-key.json GCP_PROJECT=acinema-hack-0807
python -m deploy.deploy_agent     # writes AGENT_ENGINE_ID to .env; web app then calls the remote agent
```

**Web → Cloud Run** (documented in `deploy/cloud_run.yaml`):

```bash
gcloud run deploy script-matrix-web \
  --source . --platform managed --region us-central1 --allow-unauthenticated \
  --set-env-vars CLICKHOUSE_MCP_AUTH_DISABLED=true
# plus ClickHouse Cloud vars (CLICKHOUSE_HOST/PORT/USER/PASSWORD/SECURE) + CLICKHOUSE_ALLOW_WRITE_ACCESS=true
```

## Demo video

See `docs/demo_script.md` for the 3-minute functional-demo walkthrough (upload → checklist → live analytics).

## Repo layout

```
src/agent/        ADK agent + tools
src/clickhouse/   mcp-clickhouse client + schema.sql
src/ingestion/    PDF + email parsers
src/web/          FastAPI app + templates
deploy/           Agent Engine + Cloud Run configs
tests/            sample fixtures + pytest
docs/             demo script, pitch, provisioning checklist
references/       vendor repos (mcp-clickhouse) — excluded from submission
```

## License

Apache-2.0 (see `LICENSE`).
