"""
Vector Embeddings Service for Semantic Search
Generates and stores embeddings for candidates and jobs.
Uses OpenAI embeddings via direct API call.
"""
import os
import logging
import asyncio
import httpx
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Embedding model configuration
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI's efficient embedding model
EMBEDDING_DIMENSIONS = 1536  # Output dimensions
OPENAI_API_URL = "https://emergentintegrations-api.onrender.com/v1/embeddings"


class EmbeddingService:
    """Service for generating and managing vector embeddings."""
    
    def __init__(self):
        self.api_key = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the embedding service."""
        if self._initialized:
            return
        
        self.api_key = os.environ.get("EMERGENT_LLM_KEY")
        if self.api_key:
            self._initialized = True
            logger.info("✅ Embedding service initialized")
        else:
            logger.warning("⚠️ EMERGENT_LLM_KEY not set, embeddings disabled")
    
    def _prepare_candidate_text(self, candidate: Dict[str, Any]) -> str:
        """Prepare candidate data as text for embedding."""
        parts = []
        
        # Name and title
        if candidate.get("name"):
            parts.append(f"Name: {candidate['name']}")
        if candidate.get("designation"):
            parts.append(f"Title: {candidate['designation']}")
        
        # Skills (most important for matching)
        skills = candidate.get("skills", [])
        if skills:
            parts.append(f"Skills: {', '.join(skills[:20])}")  # Top 20 skills
        
        # Experience
        if candidate.get("experience_years"):
            parts.append(f"Experience: {candidate['experience_years']} years")
        
        # Current/Previous employers
        if candidate.get("current_employer"):
            parts.append(f"Current Employer: {candidate['current_employer']}")
        
        # Industry
        if candidate.get("industry"):
            parts.append(f"Industry: {candidate['industry']}")
        
        # Location
        if candidate.get("location"):
            parts.append(f"Location: {candidate['location']}")
        
        # Summary (truncated)
        if candidate.get("summary"):
            summary = candidate["summary"][:500]  # First 500 chars
            parts.append(f"Summary: {summary}")
        
        return " | ".join(parts)
    
    def _prepare_job_text(self, job: Dict[str, Any]) -> str:
        """Prepare job data as text for embedding."""
        parts = []
        
        # Title
        if job.get("title"):
            parts.append(f"Title: {job['title']}")
        
        # Skills required
        skills = job.get("skills_required", []) or job.get("required_skills", [])
        if skills:
            parts.append(f"Required Skills: {', '.join(skills[:15])}")
        
        # Experience
        if job.get("min_experience"):
            exp_text = f"{job['min_experience']}"
            if job.get("max_experience"):
                exp_text += f"-{job['max_experience']}"
            parts.append(f"Experience Required: {exp_text} years")
        
        # Location
        if job.get("location"):
            parts.append(f"Location: {job['location']}")
        
        # Description (truncated)
        if job.get("description"):
            desc = job["description"][:500]
            parts.append(f"Description: {desc}")
        
        # Requirements
        if job.get("requirements"):
            req = job["requirements"][:300]
            parts.append(f"Requirements: {req}")
        
        return " | ".join(parts)
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding vector for text using OpenAI API."""
        if not self._initialized:
            await self.initialize()
        
        if not self.api_key:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    OPENAI_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": EMBEDDING_MODEL,
                        "input": text,
                        "dimensions": EMBEDDING_DIMENSIONS
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["data"][0]["embedding"]
                else:
                    logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                    return None
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
        """
        Find most similar candidates to a job based on embeddings.
        Returns candidates sorted by similarity score.
        """
        from services.cache import cache
        
        results = []
        
        for candidate in candidates:
            candidate_id = candidate.get("id")
            
            # Try to get cached embedding
            embedding = cache.get_candidate_embedding(candidate_id)
            
            if not embedding:
                # Generate embedding
                embedding = await self.generate_candidate_embedding(candidate)
                if embedding:
                    # Cache for future use
                    cache.set_candidate_embedding(candidate_id, embedding)
            
            if embedding:
                similarity = self.cosine_similarity(job_embedding, embedding)
                results.append({
                    **candidate,
                    "semantic_score": round(similarity * 100, 2)
                })
            else:
                # No embedding available, use default score
                results.append({
                    **candidate,
                    "semantic_score": 0
                })
        
        # Sort by semantic score descending
        results.sort(key=lambda x: x.get("semantic_score", 0), reverse=True)
        
        return results[:top_k]


# Global embedding service instance
embedding_service = EmbeddingService()


async def process_candidate_embedding(candidate_id: str, candidate_data: Dict[str, Any], db) -> bool:
    """
    Process and store embedding for a candidate.
    Called when a new candidate is added or updated.
    """
    try:
        embedding = await embedding_service.generate_candidate_embedding(candidate_data)
        
        if embedding:
            # Store embedding in the candidate document
            await db.candidate_bank.update_one(
                {"id": candidate_id},
                {
                    "$set": {
                        "embedding": embedding,
                        "embedding_updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            logger.info(f"Embedding stored for candidate: {candidate_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to process embedding for candidate {candidate_id}: {e}")
        return False


async def batch_generate_embeddings(candidates: List[Dict[str, Any]], db, batch_size: int = 10) -> int:
    """
    Generate embeddings for multiple candidates in batches.
    Returns count of successfully processed candidates.
    """
    processed = 0
    total = len(candidates)
    
    for i in range(0, total, batch_size):
        batch = candidates[i:i + batch_size]
        tasks = [
            process_candidate_embedding(c["id"], c, db)
            for c in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed += sum(1 for r in results if r is True)
        logger.info(f"Embedding progress: {min(i + batch_size, total)}/{total}")
    
    return processed
