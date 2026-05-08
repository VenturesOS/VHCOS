"""
Groq LLM Service for Candidate Profile Extraction
Ultra-fast and cost-effective alternative to Claude
"""
import os
import json
import re
from groq import AsyncGroq
import logging

logger = logging.getLogger(__name__)

# Initialize Groq client
groq_client = AsyncGroq(api_key=os.getenv('GROQ_API_KEY'))


async def extract_phone_and_work_experience_groq(raw_text: str, candidate_name: str = None) -> dict:
    """
    Extract phone number and work experience with automatic fallback.
    
    Uses: Groq → Emergent LLM Key → Raw fallback
    
    Args:
        raw_text: Raw profile text from Naukri
        candidate_name: Name of candidate (for logging)
    
    Returns:
        dict: {
            "phone": str or None,
            "work_experience": [...],
            "source": "groq" | "emergent_llm" | "raw_fallback"
        }
    """
    from services.llm_fallback_service import extract_phone_and_work_experience_fallback
    
    return await extract_phone_and_work_experience_fallback(raw_text, candidate_name)


async def extract_full_profile_groq(raw_text: str, candidate_name: str = None) -> dict:
    """
    Extract complete profile with automatic fallback.
    
    Uses: Groq → Emergent LLM Key → Raw fallback
    
    Returns all fields: name, email, phone, work_experience, education, skills, etc.
    """
    from services.llm_fallback_service import extract_full_profile_fallback
    
    return await extract_full_profile_fallback(raw_text, candidate_name)
