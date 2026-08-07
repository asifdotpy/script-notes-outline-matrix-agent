"""Deploy the ADK agent to Vertex AI Agent Engine (Google Cloud Agent Platform).

Run after `gcloud auth` and Application Default Credentials are set (the deploy uses
GOOGLE_APPLICATION_CREDENTIALS or `gcloud auth application-default login`). The agent uses
Gemini only via Vertex AI (Google Cloud AI), complying with the hackathon AI restriction.

On success it writes the deployed resource name into .env as AGENT_ENGINE_ID so the web
app (src/web/app.py) calls the remote Agent Engine instead of the in-process runner.

Reference: tutorial_deploy_your_first_adk_agent_on_agent_engine.ipynb
           (GoogleCloudPlatform/generative-ai)
"""
from __future__ import annotations

import os

import vertexai
from vertexai import agent_engines

from src.agent.agent import build_agent

PROJECT = os.environ.get("GCP_PROJECT", "acinema-hack-0807")
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
STAGING_BUCKET = os.environ.get("STAGING_BUCKET", "acinema-hack-staging-0807")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")
REQ_PATH = os.path.join(ROOT, "requirements.txt")


def _requirements_list() -> list[str]:
    """Parse requirements.txt into bare pip specifiers (no '-r', no comments/blank lines).

    Agent Engine's `requirements` arg wants a list of package strings, not a '-r file'
    line (that form is rejected at build time: 'Expected package name at the start')."""
    specs: list[str] = []
    with open(REQ_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            specs.append(line)
    return specs


def deploy(project: str = PROJECT, location: str = LOCATION,
           staging_bucket: str = STAGING_BUCKET) -> str:
    vertexai.init(project=project, location=location,
                  staging_bucket=f"gs://{staging_bucket}")
    agent = build_agent()
    # Agent Engine deploys the ADK agent plus its tooling. extra_packages must be a
    # RELATIVE path (here "src", relative to the deploy cwd = repo root) so the uploaded
    # tarball flattens to /code/src and `import src...` resolves inside the container.
    # Passing an absolute path (e.g. ROOT) tars the full home prefix, so src ends up at
    # /code/home/asif1/.../src and import fails ("No module named 'src'").
    # requirements pins the same deps the agent needs at runtime (bare specifiers, not '-r file').
    remote = agent_engines.create(
        agent_engine=agent,
        display_name="Script Notes-to-Outline Matrix Agent",
        requirements=_requirements_list(),
        extra_packages=["src"],
    )
    resource_name = remote.resource_name
    print("Deployed Agent Engine resource:", resource_name)
    _write_agent_engine_id(resource_name)
    return resource_name


def _write_agent_engine_id(resource_name: str) -> None:
    """Persist the deployed resource name to .env as AGENT_ENGINE_ID (best-effort)."""
    if not os.path.exists(ENV_PATH):
        print(f"[skip] .env not found at {ENV_PATH}; set AGENT_ENGINE_ID manually.")
        return
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = []
    replaced = False
    for line in lines:
        if line.startswith("AGENT_ENGINE_ID="):
            new_lines.append(f"AGENT_ENGINE_ID={resource_name}\n")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"AGENT_ENGINE_ID={resource_name}\n")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"[written] AGENT_ENGINE_ID={resource_name} -> .env")


if __name__ == "__main__":
    deploy()
