"""
RunPod BGE Sidecar — FastAPI service to serve sentence-transformer
embeddings on GPU. Runs *inside* the existing vLLM RunPod pod so it
shares the RTX A5000 24 GB. Frees ~1 GB EC2 RAM, unlocking t3.medium.

Deploy steps (manual, by user):
  1. SSH into the RunPod pod (the same one running Qwen vLLM).
  2. Copy this file + start_sidecar.sh into /workspace/bge_sidecar/
  3. `pip install fastapi==0.118.0 uvicorn==0.34.0 sentence-transformers==3.0.1`
  4. `bash start_sidecar.sh` (runs on port 8001 internally; RunPod exposes
     this as https://<POD-ID>-8001.proxy.runpod.net)
  5. Add the URL to EC2 `.env` as `BGE_SIDECAR_URL=https://<POD-ID>-8001.proxy.runpod.net`

The sidecar warms BGE-small on startup, so first request after pod start
takes <2 s instead of EC2's ~50 s cold start.
"""
from __future__ import annotations
import logging
import os
import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

EMBED_MODEL_NAME = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = 384
MAX_TEXT_CHARS = 2000     # match EC2-side behavior
MAX_BATCH_SIZE = 64

app = FastAPI(title="VHC BGE Embedding Sidecar", version="1.0.0")

_MODEL = None
_DEVICE = "cuda"


# ─────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def warm_model():
    global _MODEL, _DEVICE
    try:
        from sentence_transformers import SentenceTransformer
        import torch
        if not torch.cuda.is_available():
            _DEVICE = "cpu"
            logger.warning("[BGE-Sidecar] CUDA NOT available — falling back to CPU")
        logger.info(f"[BGE-Sidecar] Loading {EMBED_MODEL_NAME} on {_DEVICE}…")
        t0 = time.time()
        _MODEL = SentenceTransformer(EMBED_MODEL_NAME, device=_DEVICE)
        # Warm pass so first real request is fast
        _MODEL.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)
        logger.info(f"[BGE-Sidecar] Ready in {time.time() - t0:.2f}s")
    except Exception as e:
        logger.exception(f"[BGE-Sidecar] Failed to load model: {e}")


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────
class EmbedRequest(BaseModel):
    texts: List[str]
    normalize: bool = True


class EmbedResponse(BaseModel):
    embeddings: List[Optional[List[float]]]
    dim: int
    model: str
    device: str
    took_ms: int


@app.get("/health")
async def health():
    return {
        "ok": True,
        "model_loaded": _MODEL is not None,
        "model_name": EMBED_MODEL_NAME,
        "device": _DEVICE,
        "dim": EMBED_DIM,
    }


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    if _MODEL is None:
        # Don't 500 — return retry-able 503 so EC2 can mark pending and retry.
        raise HTTPException(status_code=503, detail="model not loaded yet")

    texts = req.texts or []
    if not texts:
        return EmbedResponse(
            embeddings=[], dim=EMBED_DIM, model=EMBED_MODEL_NAME,
            device=_DEVICE, took_ms=0,
        )
    if len(texts) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"batch too large ({len(texts)} > {MAX_BATCH_SIZE})",
        )

    # Sanitize: empty strings → None embedding so caller can short-circuit.
    cleaned: List[Optional[str]] = [
        (t.strip()[:MAX_TEXT_CHARS] if (t and t.strip()) else None) for t in texts
    ]
    valid_idx = [i for i, t in enumerate(cleaned) if t]
    valid_texts = [cleaned[i] for i in valid_idx]

    t0 = time.time()
    if not valid_texts:
        return EmbedResponse(
            embeddings=[None] * len(texts), dim=EMBED_DIM, model=EMBED_MODEL_NAME,
            device=_DEVICE, took_ms=0,
        )

    try:
        vecs = _MODEL.encode(
            valid_texts,
            normalize_embeddings=req.normalize,
            show_progress_bar=False,
            batch_size=32,
        )
    except Exception as e:
        logger.exception(f"[BGE-Sidecar] encode failure: {e}")
        raise HTTPException(status_code=500, detail=f"encode failed: {e!s}")

    out: List[Optional[List[float]]] = [None] * len(texts)
    for slot, vec in zip(valid_idx, vecs):
        out[slot] = vec.tolist()

    return EmbedResponse(
        embeddings=out,
        dim=EMBED_DIM,
        model=EMBED_MODEL_NAME,
        device=_DEVICE,
        took_ms=int((time.time() - t0) * 1000),
    )
