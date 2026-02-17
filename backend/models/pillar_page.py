"""
Pillar Page models — SEO Content Silo Architecture
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class PillarHero(BaseModel):
    headline: str = ""
    subtext: str = ""
    cta_text: str = ""
    cta_link: str = ""


class PillarFAQItem(BaseModel):
    question: str
    answer: str


class PillarPageCreate(BaseModel):
    slug: str = Field(..., pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    title: str
    meta_title: str
    meta_description: str
    hero: PillarHero = PillarHero()
    content: str = ""
    faq: List[PillarFAQItem] = []
    status: str = Field("draft", pattern=r'^(draft|published)$')


class PillarPageUpdate(BaseModel):
    title: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    hero: Optional[PillarHero] = None
    content: Optional[str] = None
    faq: Optional[List[PillarFAQItem]] = None
    status: Optional[str] = Field(None, pattern=r'^(draft|published)$')
