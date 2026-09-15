"""
FastAPI lifespan — critical DB init blocks startup; the rest runs in background.

Extracted from server.py in the 2026-08 split. Behaviour must remain identical:
    1. Create global httpx.AsyncClient
    2. run_critical_init() — blocks until MongoDB is up
    3. run_deferred_init() — indexes / schedulers, in background
    4. start_metrics_flusher() + ensure_metrics_indexes()
    5. Retired provider sync removed; inference uses the approved three-provider chain
    6. Talent Graph indexes (idempotent, safe every boot)
    7. BGE model + cluster cache preload (skipped when sidecar is configured)
    8. fast_search projection sanity check (warns if UI-required fields are missing)
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from config import client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: creates shared resources at startup, cleans up on shutdown."""

    # ── Startup ──
    # 1. Global httpx.AsyncClient — reused across all LLM calls (no per-request overhead)
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10, read=90, write=30, pool=10),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    )
    logger.info("[Lifespan] Global httpx.AsyncClient created")

    # 2. Critical DB initialization (blocks until MongoDB connected)
    from services.lifecycle import run_critical_init, run_deferred_init
    await run_critical_init()

    # 3. Non-critical tasks (indexes, schedulers) run in background
    asyncio.create_task(run_deferred_init(app))

    # 4. API metrics
    from middleware.api_metrics import start_metrics_flusher, ensure_metrics_indexes
    start_metrics_flusher()
    await ensure_metrics_indexes()

    # 5. Log retention pruner — bounded delete_many every 6h for the
    # telemetry collections that store timestamps as float/string (no
    # native TTL index possible without a schema migration).
    try:
        from services.log_retention import start_retention_pruner
        from config import db as _lr_db
        start_retention_pruner(_lr_db)
    except Exception as _e:
        logger.warning(f"[Lifespan] Log retention pruner not started: {_e}")

    # 6. Talent Graph indexes — safe to run on every boot
    try:
        from services.talent_graph_service import ensure_embeddings_indexes
        from config import db as _tg_db
        await ensure_embeddings_indexes(_tg_db)
    except Exception as _e:
        logger.warning(f"[Lifespan] Talent Graph index init skipped: {_e}")

    # 7. BGE embedding model + cluster-cache preload (Search Phase 1.5,
    # 2026-06-15). The first hit to /api/talent/search used to pay ~16s:
    # ~5s loading the sentence-transformers model + ~5s fetching cluster
    # blocks from Mongo + ~5s on the first vector forward pass. We now
    # preload both in background so the FIRST request is 1-3 s (just the
    # vector lookup + rerank), not 16 s.
    #
    # When BGE_SIDECAR_URL is set we skip the local preload entirely —
    # the sidecar is the production embedding path and there is no
    # in-process model to warm.
    try:
        from services.embed_client import is_remote_enabled
        if not is_remote_enabled():
            async def _warmup_search():
                try:
                    from services.talent_graph_service import (
                        embed_text as _embed,
                        prime_all_clusters as _prime,
                    )
                    from config import db as _wdb
                    # Step 1: load BGE model (blocking — runs in worker thread)
                    await asyncio.to_thread(_embed, "warmup")
                    # Step 2: prime ALL cluster blocks + the unclustered
                    # bucket so the user-facing fallback never pays a
                    # cold Mongo fetch. ~3-5 s wall-clock for 25 clusters
                    # but kills the per-query 5 s tax for every search.
                    try:
                        await _prime(_wdb)
                    except Exception as _se:
                        logger.info(f"[Lifespan] cluster cache prime skipped: {_se}")
                except Exception as _e:
                    logger.info(f"[Lifespan] BGE model preload soft-failed: {_e}")

            asyncio.create_task(_warmup_search())
            logger.info("[Lifespan] BGE model + cluster cache preload kicked off")
        else:
            logger.info("[Lifespan] BGE remote sidecar enabled — skipping local preload")
    except Exception as _e:
        logger.warning(f"[Lifespan] BGE model preload skipped: {_e}")

    # 8. Fast-search projection sanity check — guards against the class of
    # bug where fast_search.LIST_PROJECTION (include-mode) silently drops a
    # field the legacy exclude-mode projection would have returned. Bit us
    # hard on the "Q" admin badge (Phase 55.11g). Missing fields log a
    # warning at boot so it can never happen unnoticed again.
    try:
        from services.fast_search import LIST_PROJECTION as _fast_proj
        # Fields the legacy path in routes/candidates.py explicitly excludes
        # (everything else is returned). Keep in sync with `list_projection`
        # in routes/candidates.py::list_candidates.
        _legacy_excluded = {
            "_id", "embedding", "raw_text_for_enrichment", "raw_profile_text",
            "ai_full_text", "resume_latex", "naukri_data", "profile_update_audit",
        }
        # Fields the frontend candidate list card reads (grep the src tree
        # for `candidate\.\w+` under CandidateListItem to keep this current).
        _ui_required = {
            "id", "name", "email", "phone", "headline",
            "current_designation", "designation", "current_employer",
            "current_location", "location", "skills", "smart_tags",
            "source", "created_at", "updated_at",
            "ai_enrichment_source", "ai_enriched_at", "enrichment_status",
            "bulk_import_restricted", "cv_attached", "resume_url", "is_active",
        }
        _fast_included = {k for k, v in _fast_proj.items() if v == 1}
        _missing = _ui_required - _fast_included
        if _missing:
            logger.error(
                f"[Lifespan] ⚠️  fast_search.LIST_PROJECTION is missing "
                f"{len(_missing)} field(s) the UI reads: {sorted(_missing)}. "
                f"Add them to services/fast_search.py or the fast path will "
                f"silently strip them from API responses."
            )
        else:
            logger.info(
                f"[Lifespan] fast_search projection OK "
                f"({len(_fast_included)} fields, covers all UI-required)"
            )
    except Exception as _e:
        logger.warning(f"[Lifespan] fast_search projection check skipped: {_e}")

    yield  # ── App is running ──

    # ── Shutdown ──
    await app.state.http_client.aclose()
    logger.info("[Lifespan] Global httpx.AsyncClient closed")

    from services.lifecycle import shutdown_scheduler, shutdown_db
    await shutdown_scheduler()
    await shutdown_db(client)
