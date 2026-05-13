"""
VHC RunPod GPU Sidecar — Feb 2026 (Phase 54.20)

Self-contained FastAPI service that runs on the same RunPod pod as
vLLM (Qwen14B) and serves two endpoints:

  POST /embed     — bi-encoder embeddings for talent-graph / cache
                    Model: BAAI/bge-small-en-v1.5 (384-dim)
  POST /rerank    — cross-encoder rerank for candidate-mandate match
                    Model: BAAI/bge-reranker-base
  GET  /health    — liveness probe

Both models are baked into the Docker image so cold starts skip the
HuggingFace download and warm-up takes ~10 s on an A5000.
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
RERANK_MODEL_NAME = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-base")
EMBED_DIM = 384
MAX_TEXT_CHARS = 2000
MAX_BATCH_SIZE = 64
MAX_RERANK_PAIRS = 128

app = FastAPI(title="VHC GPU Sidecar", version="2.0.0")

_EMBED_MODEL = None
_RERANK_MODEL = None
_DEVICE = "cuda"


@app.on_event("startup")
async def warm_models() -> None:
    """Load both models on startup. Errors are logged but don't crash the
    process — /health reflects readiness, callers fall back gracefully."""
    global _EMBED_MODEL, _RERANK_MODEL, _DEVICE
    try:
        import torch
        from sentence_transformers import SentenceTransformer, CrossEncoder

        if not torch.cuda.is_available():
            _DEVICE = "cpu"
            logger.warning("[Sidecar] CUDA NOT available — using CPU")

        t0 = time.time()
        logger.info(f"[Sidecar] Loading bi-encoder {EMBED_MODEL_NAME} on {_DEVICE}…")
        _EMBED_MODEL = SentenceTransformer(EMBED_MODEL_NAME, device=_DEVICE)
        _EMBED_MODEL.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)
        logger.info(f"[Sidecar] Bi-encoder ready in {time.time() - t0:.2f}s")

        t1 = time.time()
        logger.info(f"[Sidecar] Loading cross-encoder {RERANK_MODEL_NAME} on {_DEVICE}…")
        _RERANK_MODEL = CrossEncoder(RERANK_MODEL_NAME, device=_DEVICE)
        _RERANK_MODEL.predict([("warmup query", "warmup doc")])
        logger.info(f"[Sidecar] Cross-encoder ready in {time.time() - t1:.2f}s")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[Sidecar] Model load failed: {e}")


# ─────────────────────────────────────────────────────────────────────
# Schemas
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


class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_k: Optional[int] = None  # if set, returns only top-k results


class RerankHit(BaseModel):
    index: int
    score: float


class RerankResponse(BaseModel):
    results: List[RerankHit]
    model: str
    device: str
    took_ms: int


# ─────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "ok": True,
        "embed_loaded": _EMBED_MODEL is not None,
        "rerank_loaded": _RERANK_MODEL is not None,
        # Back-compat: old EC2 health probe checks `model_loaded`.
        "model_loaded": _EMBED_MODEL is not None,
        "embed_model": EMBED_MODEL_NAME,
        "rerank_model": RERANK_MODEL_NAME,
        "device": _DEVICE,
        "dim": EMBED_DIM,
    }


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    if _EMBED_MODEL is None:
        raise HTTPException(status_code=503, detail="embed model not loaded yet")
    texts = req.texts or []
    if not texts:
        return EmbedResponse(embeddings=[], dim=EMBED_DIM, model=EMBED_MODEL_NAME, device=_DEVICE, took_ms=0)
    if len(texts) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=400, detail=f"batch too large ({len(texts)} > {MAX_BATCH_SIZE})")

    cleaned = [(t.strip()[:MAX_TEXT_CHARS] if (t and t.strip()) else None) for t in texts]
    valid_idx = [i for i, t in enumerate(cleaned) if t]
    valid_texts = [cleaned[i] for i in valid_idx]

    t0 = time.time()
    if not valid_texts:
        return EmbedResponse(embeddings=[None] * len(texts), dim=EMBED_DIM,
                             model=EMBED_MODEL_NAME, device=_DEVICE, took_ms=0)
    try:
        vecs = _EMBED_MODEL.encode(
            valid_texts,
            normalize_embeddings=req.normalize,
            show_progress_bar=False,
            batch_size=32,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[Sidecar] encode failure: {e}")
        raise HTTPException(status_code=500, detail=f"encode failed: {e!s}")

    out: List[Optional[List[float]]] = [None] * len(texts)
    for slot, vec in zip(valid_idx, vecs):
        out[slot] = vec.tolist()
    return EmbedResponse(
        embeddings=out, dim=EMBED_DIM, model=EMBED_MODEL_NAME,
        device=_DEVICE, took_ms=int((time.time() - t0) * 1000),
    )


@app.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    if _RERANK_MODEL is None:
        raise HTTPException(status_code=503, detail="rerank model not loaded yet")
    docs = req.documents or []
    if not docs:
        return RerankResponse(results=[], model=RERANK_MODEL_NAME, device=_DEVICE, took_ms=0)
    if len(docs) > MAX_RERANK_PAIRS:
        raise HTTPException(status_code=400, detail=f"too many docs ({len(docs)} > {MAX_RERANK_PAIRS})")

    q = (req.query or "").strip()[:MAX_TEXT_CHARS]
    if not q:
        raise HTTPException(status_code=400, detail="empty query")

    pairs = [(q, (d or "").strip()[:MAX_TEXT_CHARS]) for d in docs]
    t0 = time.time()
    try:
        scores = _RERANK_MODEL.predict(pairs, show_progress_bar=False, batch_size=32)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[Sidecar] rerank failure: {e}")
        raise HTTPException(status_code=500, detail=f"rerank failed: {e!s}")

    hits = [RerankHit(index=i, score=float(s)) for i, s in enumerate(scores)]
    hits.sort(key=lambda h: h.score, reverse=True)
    if req.top_k:
        hits = hits[: req.top_k]
    return RerankResponse(
        results=hits, model=RERANK_MODEL_NAME, device=_DEVICE,
        took_ms=int((time.time() - t0) * 1000),
    )
