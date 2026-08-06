"""Deploy the ADK agent to Vertex AI Agent Engine (Google Cloud Agent Platform).

Run after `gcloud auth login` + project/billing setup. The agent uses Gemini only
(Google Cloud AI), complying with the hackathon AI restriction. The ClickHouse MCP
server is launched at agent runtime via src/clickhouse/client.py, so the deployed
agent still demonstrates ACTIVE ClickHouse use.

Reference: tutorial_deploy_your_first_adk_agent_on_agent_engine.ipynb (GoogleCloudPlatform/generative-ai)
"""
from __future__ import annotations

import os

from google.cloud import aiplatform
from google.adk.agents import Agent

from src.agent.agent import build_agent


def deploy(project: str, location: str = "us-central1") -> None:
    aiplatform.init(project=project, location=location)
    agent: Agent = build_agent()
    # Agent Engine expects the agent object + its tool dependencies deployable.
    # Inline-source deploy bundles src/ so client.py (mcp-clickhouse) ships with it.
    remote = aiplatform.agent_engines.create(
        agent=agent,
        display_name="Script Notes-to-Outline Matrix Agent",
    )
    print("Deployed Agent Engine resource:", remote.resource_name)


if __name__ == "__main__":
    deploy(os.environ["GCP_PROJECT"])
