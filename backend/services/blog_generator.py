"""
Blog Content Generation Service — LLM Abstraction Layer
Model-agnostic: configurable model, temperature, and prompts.
Supports future upgrade to GPT-4o or routing logic.
"""
import os
import json
import re
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# --- Model Configuration (upgradeable) ---
BLOG_MODEL = os.environ.get("BLOG_LLM_MODEL", "gpt-4o-mini")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
BLOG_TEMPERATURE = float(os.environ.get("BLOG_LLM_TEMPERATURE", "0.7"))
BLOG_MAX_TOKENS = int(os.environ.get("BLOG_LLM_MAX_TOKENS", "4096"))


def _get_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY not configured")
    return key


async def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = None) -> str:
    """Generic LLM call with error handling."""
    api_key = _get_api_key()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": BLOG_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": BLOG_TEMPERATURE,
        "max_tokens": max_tokens or BLOG_MAX_TOKENS,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(OPENAI_API_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            logger.error(f"[Blog LLM] Error {resp.status_code}: {resp.text[:300]}")
            raise Exception(f"LLM API error: {resp.status_code}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ──────────────────────────────────────────────
# EMPLOYER BLOG GENERATION
# ──────────────────────────────────────────────

EMPLOYER_SYSTEM_PROMPT = """You are an expert content strategist specializing in industrial recruitment and talent acquisition. You write authoritative, data-driven blog articles that position the company as an Industrial Hiring Intelligence Leader.

Your writing style:
- Professional, authoritative, industry-expert tone
- Data-driven with real hiring scenarios
- Deep industry knowledge
- SEO-optimized structure
- No AI disclaimers or mentions of being AI-generated

Target audience: HR Heads, Plant Heads, Manufacturing decision-makers across industrial sectors.
Excluded industries: BPO, Banking, Insurance.

You MUST return valid JSON only. No markdown fencing, no backticks, no commentary outside JSON."""

EMPLOYER_USER_PROMPT = """Generate a complete recruitment-focused blog article.

Topic: {topic}
Industry Focus: {industry}
Region: {region}
Target Keywords: {keywords}

Requirements:
- 1500-2000 words of content
- SEO optimized title (60-70 characters)
- Meta description (150-160 characters)
- URL slug suggestion
- Proper H1, H2, H3 heading structure
- Include real hiring scenarios and data-driven insights
- Mid-article CTA for recruitment consultation
- End CTA: "Our team can shortlist top candidates within 72 hours"
{ats_note}
- Suggest 3-5 internal linking opportunities

Return as JSON with this exact structure:
{{
  "title": "SEO optimized title",
  "meta_description": "150-160 char description",
  "slug": "url-slug-suggestion",
  "content": "Full HTML content with <h2>, <h3>, <p>, <ul>, <li>, <strong>, <blockquote> tags. Include mid-article CTA as a styled callout div and end CTA.",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "internal_links": ["suggested link text 1", "suggested link text 2", "suggested link text 3"],
  "cta_type": "recruitment_consultation",
  "word_count_estimate": 1750
}}"""


# ──────────────────────────────────────────────
# CANDIDATE BLOG GENERATION
# ──────────────────────────────────────────────

CANDIDATE_SYSTEM_PROMPT = """You are a friendly, experienced career advisor who writes helpful articles for industrial professionals. Your tone is warm, supportive, and practical — never salesy or aggressive.

Your writing style:
- Helpful, non-sales tone
- Easy readability with short paragraphs
- Bullet points where relevant
- Practical advice professionals can act on immediately
- No AI disclaimers or mentions of being AI-generated

Target audience: Engineers, Plant HR, IR professionals, Manufacturing leaders.
Excluded industries: BPO, Banking, Insurance.

You MUST return valid JSON only. No markdown fencing, no backticks, no commentary outside JSON."""

CANDIDATE_USER_PROMPT = """Generate a complete career advice blog article.

Topic: {topic}
Category: {category}
Industry Focus: {industry}
Target Keywords: {keywords}

Requirements:
- 1200-1800 words of content
- SEO optimized title (60-70 characters)
- Meta description (150-160 characters)
- URL slug suggestion
- Proper H1, H2, H3 heading structure
- Easy readability, short paragraphs
- Bullet points where relevant
- Helpful, non-sales tone throughout
- Soft CTA: Encourage readers to "Create your profile" or "Upload your resume" to discover matching opportunities
- Suggest 3-5 internal linking opportunities

Return as JSON with this exact structure:
{{
  "title": "SEO optimized title",
  "meta_description": "150-160 char description",
  "slug": "url-slug-suggestion",
  "content": "Full HTML content with <h2>, <h3>, <p>, <ul>, <li>, <strong>, <blockquote> tags. Include soft CTAs naturally within content.",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "internal_links": ["suggested link text 1", "suggested link text 2", "suggested link text 3"],
  "cta_type": "profile_creation",
  "word_count_estimate": 1500
}}"""


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fencing."""
    text = text.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


async def generate_employer_blog(topic: str, industry: str, region: str, keywords: str) -> dict:
    """Generate a complete employer-focused blog article."""
    ats_note = '- Include ATS (Applicant Tracking System) positioning and how technology accelerates hiring' if region.lower() == 'global' else ''
    user_prompt = EMPLOYER_USER_PROMPT.format(
        topic=topic, industry=industry, region=region,
        keywords=keywords, ats_note=ats_note
    )
    raw = await _call_llm(EMPLOYER_SYSTEM_PROMPT, user_prompt)
    result = _parse_json_response(raw)
    result["blog_type"] = "employer"
    result["region"] = region
    return result


async def generate_candidate_blog(topic: str, category: str, industry: str, keywords: str) -> dict:
    """Generate a complete candidate-focused blog article."""
    user_prompt = CANDIDATE_USER_PROMPT.format(
        topic=topic, category=category, industry=industry, keywords=keywords
    )
    raw = await _call_llm(CANDIDATE_SYSTEM_PROMPT, user_prompt)
    result = _parse_json_response(raw)
    result["blog_type"] = "candidate"
    result["category"] = category
    return result
