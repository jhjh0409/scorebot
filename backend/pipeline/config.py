"""
Configuration settings for the hiring agent application.
"""

import os

# Development mode enables local caching of parse/GitHub results (cache/) so
# rubric iterations don't re-spend LLM calls. Defaults on for local work;
# the Dockerfile turns it off for deployments (ephemeral disk, stale data).
DEVELOPMENT_MODE = os.getenv("DEVELOPMENT_MODE", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
