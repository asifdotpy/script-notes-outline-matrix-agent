# Demo Script — 3-minute functional demo (NOT a cinematic trailer)

Record a real run of the agent solving a screenwriter's revision problem.
Public YouTube/Vimeo, English (or subtitled).

## 0:00–0:30 — The pain (show, don't tell)
- Screen (no voiceover needed): a screenwriter's inbox with a PDF coverage report
  + a producer email full of conflicting notes; a frustrated sticky note: "revision paralysis."
- Say: "Screenwriters get drowning in unstructured notes. Deciding how to apply them
  to Draft 2 is the painful part."

## 0:30–1:15 — The product
- Open the web app (FastAPI on Cloud Run): http://localhost:8080 (or the deployed URL).
- Upload `tests/sample_feedback.eml` (producer email) — or a PDF coverage report.
- Say: "The agent ingests EXTERNAL notes — PDFs and emails — not just in-app comments."

## 1:15–2:15 — The agent runs (live ClickHouse)
- Show the agent output: notes categorized by type / character / scene / severity.
- Highlight the CONFLICT FLAG: "cut the intro" vs "let it breathe" — surfaced automatically.
- Show the scene-by-scene Draft-2 checklist, highest-severity first.
- Say: "Every note is persisted to ClickHouse via the official mcp-clickhouse server
  at runtime — this isn't a mock." (Flash the analytics: note-category frequencies,
  conflict count, scene coverage.)

## 2:15–2:45 — Why it's real
- Show the live analytics panel backed by ClickHouse.
- Say: "Gemini does the reasoning; ClickHouse holds the structured matrix. Rules-compliant:
  it automates planning, it never writes your script for you."

## 2:45–3:00 — Close
- "Built on Google Cloud Agent Platform (ADK + Gemini) + ClickHouse, for the
  Agentic Cinema hackathon, ClickHouse partner track."

## Evidence artifacts to capture
- Screenshot: web form with uploaded file + rendered checklist.
- Screenshot: ClickHouse analytics (or a `SELECT * FROM notes_matrix` result).
- The repo URL (public) + the hosted URL in the video description.
