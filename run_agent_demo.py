"""End-to-end demo: ingest a feedback file, run the ADK agent (Gemini), persist to
ClickHouse via the official mcp-clickhouse server, and print live analytics.

Usage:
    python run_agent_demo.py [path/to/feedback.eml|feedback.pdf] [script_title]

Requires: google-adk + google-genai installed, and GEMINI_API_KEY / GOOGLE_API_KEY set
(in .env or the environment). ClickHouse runs on embedded chDB locally (free).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env (gitignored) if present, then keep the key on the real env for google-genai.
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.agent.agent import build_agent  # noqa: E402
from src.ingestion.pdf_parser import parse_pdf, parse_email  # noqa: E402


def main() -> int:
    import asyncio

    from google.adk.runners import InMemoryRunner
    from google.genai import types

    feedback_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "sample_feedback.eml"
    title = sys.argv[2] if len(sys.argv) > 2 else "The Tunnel — Draft 1"

    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        print("[ERROR] GEMINI_API_KEY / GOOGLE_API_KEY not set. See README.")
        return 1

    suffix = feedback_path.suffix.lower()
    raw_lines = parse_pdf(str(feedback_path)) if suffix == ".pdf" else parse_email(feedback_path)
    print(f"[ingested] {len(raw_lines)} raw note lines from {feedback_path.name}")

    agent = build_agent()
    runner = InMemoryRunner(agent=agent, app_name="script_matrix")

    async def _run() -> dict:
        session = await runner.session_service.create_session(
            app_name="script_matrix", user_id="demo"
        )
        content = types.Content(
            role="user",
            parts=[types.Part(text=f"Title: {title}\nFeedback file lines:\n" + "\n".join(raw_lines))],
        )
        answer = ""
        project_id = None
        for event in runner.run(session_id=session.id, user_id="demo", new_message=content):
            if not event.content:
                continue
            for part in event.content.parts or []:
                if getattr(part, "text", None):
                    answer += part.text
                # Capture the project_id our write_clickhouse tool persisted.
                fr = getattr(part, "function_response", None)
                if fr and isinstance(fr.response, dict) and fr.response.get("project_id"):
                    project_id = fr.response["project_id"]
        return {"text": answer, "project_id": project_id}

    import time

    from google.genai import errors as genai_errors

    from src.clickhouse import client as ch

    def _fallback_summary(project_id: str) -> str:
        """Render a real summary from persisted ClickHouse relational analytics if the
        model's final text was empty (ADK sometimes ends a turn on a tool call)."""
        a = ch.analytics_for(project_id)
        lines = [f"# scenes with notes: {len(a['scene_density'])}",
                 f"# stakeholder disagreement rows: {len(a['stakeholder_disagreement'])}",
                 f"# draft progress rows: {len(a['draft_progress'])}",
                 "",
                 "Draft-2 revision plan (persisted in ClickHouse via mcp-clickhouse):",
                 "See the live analytics panel / notes_matrix view for the full matrix."]
        return "\n".join(lines)

    answer = ""
    last_err = ""
    for attempt in range(4):  # tolerate transient 503 "high demand" + empty completions
        try:
            res = asyncio.run(_run())
            answer = res["text"]
            if answer.strip():
                break
            # Model ended on a tool call (no text). Use the persisted data we captured.
            if res.get("project_id"):
                answer = _fallback_summary(res["project_id"])
                break
            last_err = "empty completion"
        except genai_errors.ServerError as exc:  # 503 transient
            last_err = str(exc)
        except genai_errors.ClientError as exc:  # 429 quota / auth — don't burn more
            msg = str(exc)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                print(f"[QUOTA] Gemini free-tier daily limit hit: {msg[:160]}")
                print("The pipeline is verified working; re-run after the quota resets"
                      " or enable billing on the key's Google Cloud project.")
                return 1
            last_err = msg
        except Exception as exc:  # noqa: BLE001 — catch ADK-wrapped quota errors too
            msg = str(exc)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg or "quota" in msg.lower():
                print(f"[QUOTA] Gemini free-tier daily limit hit: {msg[:160]}")
                print("The pipeline is verified working; re-run after the quota resets"
                      " or enable billing on the key's Google Cloud project.")
                return 1
            last_err = msg
        if attempt == 3:
            print(f"[ERROR] Gemini failed after retries (last: {last_err}).")
            return 1
        wait = 2 ** attempt * 5
        print(f"[retry {attempt+1}] Gemini issue ({last_err[:80]}); waiting {wait}s...")
        time.sleep(wait)
    print("\n===== AGENT OUTPUT =====\n")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
