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
Auth is **Web2 Google OAuth 2.0** — no web3, no wallets, no crypto.

## Build status (this submission)

- **Agent deployed live** to Vertex AI Agent Engine (`AGENT_ENGINE_ID` in `.env`); the Gemini → ClickHouse
  pipeline was run end-to-end and verified (feedback → categorized notes → conflict flags → persisted to ClickHouse).
- **Tests:** golden dataset + eval harness + suites A–E (ingestion, categorization, conflict detection,
  checklist, ClickHouse) + script-scene cross-check + Web2 OAuth login — all passing on embedded chDB.
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) runs `pytest` + the eval harness on every push/PR using
  free embedded **chDB** (no ClickHouse Cloud account needed in CI).

## How it works (at a glance)

```
   Producer email              PDF coverage                Script (Final Draft)
   or agent notes               report                       / .fdx
        │                           │                            │
        ▼                           ▼                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │  1. INGEST   Read the messy, contradictory feedback        │
   │             (PDFs + emails) — not just app comments         │
   └──────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │  2. THE AGENT (Gemini on Google Cloud Vertex AI)           │
   │     • Tags every note: Structure / Character / Dialogue /  │
   │       Pacing / Logic / Format + scene + severity           │
   │     • Flags conflicts: "cut the intro" ⚠ "let it breathe"  │
   │     • Builds a scene-by-scene Draft-2 revision checklist   │
   └──────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │  3. STORE & ANALYZE   ClickHouse (live database)           │
   │     Every note + conflict saved; charts show what to fix   │
   └──────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │  4. YOU GET   A clear checklist + export back to .fdx      │
   │             (so the writer knows exactly what to change)   │
   └──────────────────────────────────────────────────────────┘
```

**In one sentence for non-technical readers:** you drop in your notes and feedback,
the AI sorts them, spots where people disagree, and hands you a prioritized "what to
fix for Draft 2" list — with everything saved in a real database you can analyze.

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
- **Web2 Google OAuth 2.0 sign-in** — the web app is gated by standard Google Identity
  (Authorization Code flow, ID-token verification). **No web3, no wallets, no crypto** — this is a
  Web2 Google Cloud project end to end.
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

### System diagram (technical)

```
┌──────────────┐        POST /analyze (file, title)        ┌─────────────────────────┐
│  Web client  │ ────────────────────────────────────────▶ │  src/web/app.py (FastAPI) │
│ (browser /   │                                            │   • parse upload          │
│  Cloud Run)  │ ◀────────── HTML result + .fdx ─────────── │   • call agent (prod/dev) │
└──────────────┘                                            └───────────┬─────────────┘
                                                                     │ stream_query (prod)
                                                                     │  or InMemoryRunner (dev)
                                                                     ▼
                                                       ┌──────────────────────────────┐
                                                       │  ADK Agent (Gemini 2.5 Flash) │
                                                       │  src/agent/agent.py            │
                                                       │   build_agent() → tools:       │
                                                       │    • categorize_note           │
                                                       │    • detect_conflicts          │
                                                       │    • write_clickhouse ★         │
                                                       └───────────────┬────────────────┘
                                                                     │  ★ via MCP (stdio)
                                                                     ▼
                                                       ┌──────────────────────────────┐
                                                       │  mcp-clickhouse server        │
                                                       │  src/clickhouse/client.py      │
                                                       │   dev: chDB  │  prod: ClickHouse│
                                                       │              Cloud (8443/TLS)   │
                                                       └───────────────┬────────────────┘
                                                                     │ SQL
                                                                     ▼
                                                       ┌──────────────────────────────┐
                                                       │  ClickHouse  (runtime store)  │
                                                       │   notes_raw                   │
                                                       │   notes_conflicts             │
                                                       │   + relational analytics views │
                                                       └──────────────────────────────┘

Deploy topology:
  Local dev : FastAPI ──in-process ADK runner──▶ mcp-clickhouse (chDB)
  Prod      : FastAPI (Cloud Run) ──AGENT_ENGINE_ID──▶ Vertex AI Agent Engine
                                                   (same agent) ──▶ mcp-clickhouse ──▶ ClickHouse Cloud
  Auth      : Web2 Google OAuth 2.0 (Authorization Code flow, ID-token verified) — no web3, no wallets.
              Vertex AI access via Application Default Credentials (SA key / gcloud ADC); no API key.
```

## Quickstart (local, free — no cloud account needed)

```bash
# install (uv is the canonical, reproducible path; requirements.txt is also kept in sync)
uv sync                 # or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env    # defaults to embedded chDB (CHDB_ENABLED=true)

python -m src.clickhouse.client     # applies schema, prints OK
uvicorn src.web.app:app --port 8080  # open http://localhost:8080
```

`run_agent_demo.py tests/sample_feedback.eml` exercises the full flow end-to-end on the CLI.

> **Auth note:** with no Google OAuth credentials set, the web app runs **open** (no login wall) for
> local dev/demo. To enable the production sign-in gate, set the `GOOGLE_OAUTH_*` env vars below.

### Authentication (Web2 Google OAuth 2.0 — no web3)

The web app is protected by **standard Google Identity** (OAuth 2.0 Authorization Code flow). There is
**no wallet, no blockchain, and no Privy** anywhere in this project — it is a Web2 Google Cloud app.

1. In the Google Cloud console, create an **OAuth 2.0 Client ID** (type: Web application) for
   `acinema-hack-0807`, and add `http://localhost:8080/auth/google/callback` as an authorized redirect URI.
2. Put the client ID/secret in `.env`:

```bash
GOOGLE_OAUTH_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=....
# Optional: restrict sign-in to specific accounts (comma-separated)
GOOGLE_ALLOWED_EMAILS=you@studio.com,boss@studio.com
# Optional: separate secret for the server-side OAuth session cookie
SESSION_SECRET=some-long-random-string
```

3. Restart the app. Visiting any protected route redirects to Google; after consent the app sets a
   signed session cookie and proceeds. `SESSION_SECRET` (or `GOOGLE_OAUTH_CLIENT_SECRET`) signs the
   cookie; `GOOGLE_ALLOWED_EMAILS` restricts which Google accounts may enter.

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

## Testing

```bash
uv sync                       # reproducible install (also: pip install -r requirements.txt)
.venv/bin/python -m pytest -q # golden dataset, suites A–E, cross-check, Web2 OAuth login — all on chDB
.venv/bin/python tests/eval_harness.py   # accuracy/precision/recall regression gate vs golden labels
.venv/bin/python tests/run_demo_golden_path.py --repeat 3   # deterministic demo, 3× consistency check
```

CI (`.github/workflows/ci.yml`) runs the same `pytest` + eval harness on every push/PR.

## Demo video

See `docs/demo_script.md` for the 3-minute functional-demo walkthrough (upload → checklist → live analytics).

## Repo layout

```
src/agent/        ADK agent + tools
src/clickhouse/   mcp-clickhouse client + schema.sql
src/ingestion/    PDF + email parsers
src/web/          FastAPI app + templates (Web2 Google OAuth gate)
deploy/           Agent Engine + Cloud Run configs
tests/            golden dataset + fixtures + pytest (suites A–E, cross-check, auth)
docs/             demo script, pitch, provisioning checklist
references/       vendor repos (mcp-clickhouse) — excluded from submission
```

## License

Apache-2.0 (see `LICENSE`).
