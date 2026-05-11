#!/bin/bash
# Start the BGE embedding sidecar inside the RunPod pod.
# Drop this + embed_service.py into /workspace/bge_sidecar/ and run.
set -e

cd "$(dirname "$0")"

# Ensure deps (cheap if already installed)
pip install --quiet fastapi==0.118.0 uvicorn==0.34.0 sentence-transformers==3.0.1 2>/dev/null || true

# Run on 0.0.0.0:8001 so RunPod proxy can expose it
exec uvicorn embed_service:app --host 0.0.0.0 --port 8001 --log-level info
