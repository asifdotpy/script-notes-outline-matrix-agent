"""Public agent entrypoint (importable + adk-cli friendly).

Run locally:  adk run src.agent
Deploy:       gcloud / Agent Engine inline-source deploy (see deploy/deploy_agent.py)
"""
from __future__ import annotations

from .agent import build_agent

root_agent = build_agent()
