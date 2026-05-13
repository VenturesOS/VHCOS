# VHC GPU Sidecar — BGE embedder + cross-encoder reranker
# Built and pushed automatically by .github/workflows/build-sidecar.yml
# Image: ghcr.io/venturesos/vhc-bge-sidecar:latest
#
# Base: PyTorch 2.4 + CUDA 12.1 + Python 3.11 (~3 GB) — broadly compatible
# with A40/A5000/A6000/4090/L4/L40 RunPod hosts.

FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf_cache \
    TRANSFORMERS_OFFLINE=0

# Pin versions explicitly (matches what worked manually on the pod).
RUN pip install --no-cache-dir \
    "fastapi==0.118.0" \
    "uvicorn[standard]==0.34.0" \
    "sentence-transformers==3.0.1"

# Pre-download both models into the image so cold start skips
# the HuggingFace network round-trip.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
    SentenceTransformer('BAAI/bge-small-en-v1.5'); \
    CrossEncoder('BAAI/bge-reranker-base')"

WORKDIR /app
COPY embed_service.py /app/embed_service.py

EXPOSE 8001

# Long-running uvicorn — RunPod treats this as the foreground container process.
CMD ["uvicorn", "embed_service:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]
