"""
Vector Embeddings Service for Semantic Search
Generates and stores embeddings for candidates and jobs.
Uses OpenAI text-embedding-3-small model.

FIXED:
- _prepare_candidate_text() reads BOTH canonical and alias field names
  via schema_normalizer helpers — no more empty embedding text for
  Type A (key_skills/profile_summary) candidates
- Embedding cache backed by Redis (via CacheService) instead of a
  module-level dict — process-safe across all Gunicorn workers
"""
import os
import hashlib
import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

EMBEDDING_MODEL      = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


class EmbeddingService:
    """Service for generating and managing vector embeddings."""

    def __init__(self):
        self.client       = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the OpenAI client."""
        if self._initialized:
            return True

        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            self.client       = AsyncOpenAI(api_key=api_key)
            self._initialized = True
            logger.info("Embedding service initialized with OpenAI API")
            return True
        else:
            logger.warning("OPENAI_API_KEY not set — embeddings disabled")
            return False

    # ── Text preparation — schema-aware ──────────────────────────────────

    def _prepare_candidate_text(self, candidate: Dict[str, Any]) -> str:
        """
        Prepare candidate data as text for embedding.

        FIXED: reads BOTH canonical (key_skills, profile_summary,
        total_experience_years, current_designation, current_company,
        current_industry) AND alias (skills, summary, experience_years,
        designation, current_employer, industry) field names via
        schema_normalizer helpers.
        """
        from services.schema_normalizer import (
            get_skills,
            get_it_skill_names,
            get_summary,
            get_experience_years,
            get_designation,
            get_employer,
            get_industry,
        )

        parts = []

        name = candidate.get("name")
        if name:
            parts.append(f"Name: {name}")

        title = get_designation(candidate)
        if title:
            parts.append(f"Title: {title}")

        skills = get_skills(candidate)
        if skills:
            parts.append(f"Skills: {', '.join(skills[:20])}")

        it_skill_names = get_it_skill_names(candidate)
        if it_skill_names:
            parts.append(f"Tech: {', '.join(it_skill_names[:10])}")

        exp_years = get_experience_years(candidate)
        if exp_years:
            parts.append(f"Experience: {exp_years} years")

        employer = get_employer(candidate)
        if employer:
            parts.append(f"Employer: {employer}")

        industry = get_industry(candidate)
        if industry:
            parts.append(f"Industry: {industry}")

        location = candidate.get("location") or candidate.get("current_city")
        if location:
            parts.append(f"Location: {location}")

        summary = get_summary(candidate)
        if summary:
            parts.append(f"Summary: {summary[:500]}")

        return " | ".join(parts)

    def _prepare_job_text(self, job: Dict[str, Any]) -> str:
        """Prepare job data as text for embedding."""
        parts = []

        if job.get("title"):
            parts.append(f"Title: {job['title']}")

        skills = job.get("skills_required") or job.get("required_skills") or []
        if skills:
            parts.append(f"Required Skills: {', '.join(skills[:15])}")

        if job.get("min_experience"):
            exp_text = str(job["min_experience"])
            if job.get("max_experience"):
                exp_text += f"-{job['max_experience']}"
            parts.append(f"Experience Required: {exp_text} years")

        if job.get("location"):
            parts.append(f"Location: {job['location']}")
        if job.get("description"):
            parts.append(f"Description: {job['description'][:500]}")
        if job.get("requirements"):
            parts.append(f"Requirements: {job['requirements'][:300]}")

        return " | ".join(parts)

    # ── Embedding generation — Redis-backed cache (process-safe) ─────────

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for text.

        FIXED: uses Redis-backed CacheService instead of module-level dict.
        All Gunicorn workers share the same cache — no more per-worker drift,
        no more 4x OpenAI API calls.
        Cache is gracefully degraded: Redis failure → skip cache, not crash.
        """
        if not self._initialized:
            if not await self.initialize():
                return None

        if not self.client:
            return None

        # Stable cache key — same text always maps to the same key
        cache_key = f"emb_text:{hashlib.sha256(text.encode()).hexdigest()[:24]}"

        # Try shared Redis cache
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            response  = await self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            embedding = response.data[0].embedding

            # Cache for 24 h — embeddings are deterministic for the same text
            self._cache_set(cache_key, embedding, ttl=86400)
            return embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None

    async def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts in a single API call."""
        if not self._initialized:
            if not await self.initialize():
                return [None] * len(texts)

        if not self.client:
            return [None] * len(texts)

        try:
            response   = await self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            embeddings = [None] * len(texts)
            for item in response.data:
                embeddings[item.index] = item.embedding
            return embeddings
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            return [None] * len(texts)

    async def generate_candidate_embedding(self, candidate: Dict[str, Any]) -> Optional[List[float]]:
        """Generate embedding for a candidate profile."""
        text = self._prepare_candidate_text(candidate)
        if not text.strip():
            return None
        return await self.generate_embedding(text)

    async def generate_job_embedding(self, job: Dict[str, Any]) -> Optional[List[float]]:
        """Generate embedding for a job posting."""
        text = self._prepare_job_text(job)
        if not text.strip():
            return None
        return await self.generate_embedding(text)

    # ── Similarity ────────────────────────────────────────────────────────

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0
        dot  = sum(a * b for a, b in zip(vec1, vec2))
        n1   = sum(a * a for a in vec1) ** 0.5
        n2   = sum(b * b for b in vec2) ** 0.5
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)

    async def find_similar_candidates(
        self,
        job_embedding: List[float],
        candidates: List[Dict[str, Any]],
        top_k: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find most similar candidates to a job based on embeddings."""
        results = []
        for candidate in candidates:
            candidate_id = candidate.get("id")
            emb_key  = f"emb_cand:{candidate_id}"
            embedding = self._cache_get(emb_key)

            if not embedding:
                embedding = await self.generate_candidate_embedding(candidate)
                if embedding:
                    self._cache_set(emb_key, embedding, ttl=86400)

            if embedding:
                similarity = self.cosine_similarity(job_embedding, embedding)
                results.append({**candidate, "semantic_score": round(similarity * 100, 2)})
            else:
                results.append({**candidate, "semantic_score": 0})

        results.sort(key=lambda x: x.get("semantic_score", 0), reverse=True)
        return results[:top_k]

    async def check_health(self) -> Dict[str, Any]:
        """Check if embedding service is working."""
        try:
            if not self._initialized:
                if not await self.initialize():
                    return {"status": "disabled", "reason": "OPENAI_API_KEY not configured"}

            test_embedding = await self.generate_embedding("test")
            if test_embedding and len(test_embedding) == EMBEDDING_DIMENSIONS:
                return {
                    "status":     "healthy",
                    "model":      EMBEDDING_MODEL,
                    "dimensions": EMBEDDING_DIMENSIONS,
                }
            return {"status": "error", "reason": "Failed to generate test embedding"}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    # ── Internal cache helpers — graceful degradation ─────────────────────

    @staticmethod
    def _cache_get(key: str) -> Optional[List[float]]:
        """
        Get from Redis-backed cache. Returns None on any failure.
        Never raises — cache failure is non-fatal.
        """
        try:
            from services.cache import cache
            return cache.get(key)
        except Exception:
            return None

    @staticmethod
    def _cache_set(key: str, value: List[float], ttl: int = 86400) -> None:
        """
        Set in Redis-backed cache. Silently fails if Redis unavailable.
        """
        try:
            from services.cache import cache
            cache.set(key, value, ttl=ttl)
        except Exception:
            pass


# Global instance
embedding_service = EmbeddingService()


# ---------------------------------------------------------------------------
# Standalone helpers
# ---------------------------------------------------------------------------

async def process_candidate_embedding(
    candidate_id: str,
    candidate_data: Dict[str, Any],
    db,
) -> bool:
    """Process and store embedding for a single candidate."""
    try:
        embedding = await embedding_service.generate_candidate_embedding(candidate_data)
        if embedding:
            await db.candidate_bank.update_one(
                {"id": candidate_id},
                {"$set": {
                    "embedding":             embedding,
                    "embedding_updated_at":  datetime.now(timezone.utc).isoformat(),
                }},
            )
            logger.info(f"Embedding stored for candidate: {candidate_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to process embedding for candidate {candidate_id}: {e}")
        return False


async def batch_generate_embeddings(
    candidates: List[Dict[str, Any]],
    db,
    batch_size: int = 20,
) -> Dict[str, Any]:
    """
    Generate embeddings for multiple candidates in batches.
    Uses batch API for efficiency.
    """
    processed = 0
    failed    = 0
    total     = len(candidates)

    for i in range(0, total, batch_size):
        batch = candidates[i:i + batch_size]

        texts      = [embedding_service._prepare_candidate_text(c) for c in batch]
        embeddings = await embedding_service.generate_embeddings_batch(texts)

        now = datetime.now(timezone.utc).isoformat()
        for candidate, embedding in zip(batch, embeddings):
            if embedding:
                await db.candidate_bank.update_one(
                    {"id": candidate["id"]},
                    {"$set": {
                        "embedding":            embedding,
                        "embedding_updated_at": now,
                    }},
                )
                processed += 1
            else:
                failed += 1

        logger.info(
            f"Embedding progress: {min(i + batch_size, total)}/{total} "
            f"({processed} success, {failed} failed)"
        )

    return {
        "total":        total,
        "processed":    processed,
        "failed":       failed,
        "success_rate": round(processed / total * 100, 1) if total > 0 else 0,
    }
