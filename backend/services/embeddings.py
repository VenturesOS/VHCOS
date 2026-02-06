"""
Vector Embeddings Service for Semantic Search
Generates and stores embeddings for candidates and jobs.
Uses OpenAI embeddings API with Emergent LLM Key.
"""
import os
import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Embedding model configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


class EmbeddingService:
    """Service for generating and managing vector embeddings."""
    
    def __init__(self):
        self.client = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the OpenAI client with Emergent API."""
        if self._initialized:
            return
        
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if api_key:
            # Use Emergent's API endpoint
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://emergentintegrations-api.onrender.com/v1"
            )
            self._initialized = True
            logger.info("✅ Embedding service initialized with Emergent API")
        else:
            logger.warning("⚠️ EMERGENT_LLM_KEY not set, embeddings disabled")
    
    def _prepare_candidate_text(self, candidate: Dict[str, Any]) -> str:
        """Prepare candidate data as text for embedding."""
        parts = []
        
        if candidate.get("name"):
            parts.append(f"Name: {candidate['name']}")
        if candidate.get("designation"):
            parts.append(f"Title: {candidate['designation']}")
        
        skills = candidate.get("skills", [])
        if skills:
            parts.append(f"Skills: {', '.join(skills[:20])}")
        
        if candidate.get("experience_years"):
            parts.append(f"Experience: {candidate['experience_years']} years")
        if candidate.get("current_employer"):
            parts.append(f"Current Employer: {candidate['current_employer']}")
        if candidate.get("industry"):
            parts.append(f"Industry: {candidate['industry']}")
        if candidate.get("location"):
            parts.append(f"Location: {candidate['location']}")
        if candidate.get("summary"):
            parts.append(f"Summary: {candidate['summary'][:500]}")
        
        return " | ".join(parts)
    
    def _prepare_job_text(self, job: Dict[str, Any]) -> str:
        """Prepare job data as text for embedding."""
        parts = []
        
        if job.get("title"):
            parts.append(f"Title: {job['title']}")
        
        skills = job.get("skills_required", []) or job.get("required_skills", [])
        if skills:
            parts.append(f"Required Skills: {', '.join(skills[:15])}")
        
        if job.get("min_experience"):
            exp_text = f"{job['min_experience']}"
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
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding vector for text."""
        if not self._initialized:
            await self.initialize()
        
        if not self.client:
            logger.warning("Embedding client not initialized")
            return None
        
        try:
            response = await self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
                dimensions=EMBEDDING_DIMENSIONS
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None
    
    async def generate_candidate_embedding(self, candidate: Dict[str, Any]) -> Optional[List[float]]:
        """Generate embedding for a candidate profile."""
        text = self._prepare_candidate_text(candidate)
        return await self.generate_embedding(text)
    
    async def generate_job_embedding(self, job: Dict[str, Any]) -> Optional[List[float]]:
        """Generate embedding for a job posting."""
        text = self._prepare_job_text(job)
        return await self.generate_embedding(text)
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    async def find_similar_candidates(
        self,
        job_embedding: List[float],
        candidates: List[Dict[str, Any]],
        top_k: int = 50
    ) -> List[Dict[str, Any]]:
        """Find most similar candidates to a job based on embeddings."""
        from services.cache import cache
        
        results = []
        
        for candidate in candidates:
            candidate_id = candidate.get("id")
            embedding = cache.get_candidate_embedding(candidate_id)
            
            if not embedding:
                embedding = await self.generate_candidate_embedding(candidate)
                if embedding:
                    cache.set_candidate_embedding(candidate_id, embedding)
            
            if embedding:
                similarity = self.cosine_similarity(job_embedding, embedding)
                results.append({**candidate, "semantic_score": round(similarity * 100, 2)})
            else:
                results.append({**candidate, "semantic_score": 0})
        
        results.sort(key=lambda x: x.get("semantic_score", 0), reverse=True)
        return results[:top_k]


# Global instance
embedding_service = EmbeddingService()


async def process_candidate_embedding(candidate_id: str, candidate_data: Dict[str, Any], db) -> bool:
    """Process and store embedding for a candidate."""
    try:
        embedding = await embedding_service.generate_candidate_embedding(candidate_data)
        
        if embedding:
            await db.candidate_bank.update_one(
                {"id": candidate_id},
                {"$set": {
                    "embedding": embedding,
                    "embedding_updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            logger.info(f"Embedding stored for candidate: {candidate_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to process embedding for candidate {candidate_id}: {e}")
        return False


async def batch_generate_embeddings(candidates: List[Dict[str, Any]], db, batch_size: int = 10) -> int:
    """Generate embeddings for multiple candidates in batches."""
    processed = 0
    total = len(candidates)
    
    for i in range(0, total, batch_size):
        batch = candidates[i:i + batch_size]
        tasks = [process_candidate_embedding(c["id"], c, db) for c in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed += sum(1 for r in results if r is True)
        logger.info(f"Embedding progress: {min(i + batch_size, total)}/{total}")
    
    return processed
