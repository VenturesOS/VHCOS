"""
neural_schema.py — VHC Talent OS canonical entity models (Neural Schema v1)
===========================================================================

The single source of truth for the platform's semantic layer:

  • Six canonical entities: Candidate, Skill, Role, Company, Location,
    Mandate — strict models with normalized fields.
  • EmbeddingEnvelope: every vector on the platform carries provenance
    (model, dim, computed_at) so re-embedding is a tracked migration.
  • Relation registry + Edge model for the graph layer (v2).
  • Normalization helpers shared by capture, backfill, and seed scripts:
    salary strings → numeric LPA, notice strings → days, phone/email
    canonical forms (identical rules to ensure_search_indexes_v2.py).

Design rules:
  - ADDITIVE: canonical fields live alongside legacy strings on
    candidate_bank; nothing here mandates removing existing data.
  - Ontology ids are human-readable slugs ("skill:sap-mm",
    "loc:bengaluru") so edges and debug output stay legible.
  - Pydantic v2 style. If the project pins pydantic v1, only the
    @field_validator decorators need the v1 spelling.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "1.0"

# ═══════════════════════════════════════════════════════════════════════
# Normalization helpers (shared by seed / backfill / capture paths)
# ═══════════════════════════════════════════════════════════════════════

_DIGITS = re.compile(r"\D+")
_WS = re.compile(r"\s+")


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Digits only, last 10 kept — mirrors the search-index backfill."""
    if not raw:
        return None
    digits = _DIGITS.sub("", raw)
    if not digits:
        return None
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_email(raw: Optional[str]) -> Optional[str]:
    return raw.strip().lower() if raw and raw.strip() else None


def slug_id(prefix: str, name: str) -> str:
    """'SAP MM' -> 'skill:sap-mm'. Stable, human-readable ontology ids."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return f"{prefix}:{s or 'unknown'}"


_LPA_PATTERNS = [
    # "12 LPA", "12.5 lpa", "12 lacs", "8 lakh", "9L"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:lpa|lacs?|lakhs?|l\b)", re.I), 1.0),
    # "1.2 cr", "1 crore"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:cr|crores?)", re.I), 100.0),
]
_K_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*k\b", re.I)
_PLAIN_NUM = re.compile(r"(\d[\d,]{2,})(?:\.\d+)?")
_MONTHLY_HINT = re.compile(r"month|pm\b|p\.m", re.I)


def parse_salary_to_lpa(raw) -> Optional[float]:
    """
    Best-effort conversion of the salary strings in candidate_bank to
    annual lakhs (LPA). Returns None when not confidently parseable —
    a None is more honest than a wrong number.

    Handles: "12 LPA", "12.5 Lacs", "1.2 Cr", "1,200,000", "85k/month",
    "95000 per month", plain "1450000". Ambiguous small integers
    ("12") are treated as LPA only when <= 99.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        if v <= 0:
            return None
        if v < 100:          # already LPA
            return round(v, 2)
        if v >= 10_000:      # rupees annual
            return round(v / 100_000, 2)
        return None
    text = str(raw).strip()
    if not text:
        return None

    for pat, mult in _LPA_PATTERNS:
        m = pat.search(text)
        if m:
            return round(float(m.group(1)) * mult, 2)

    monthly = bool(_MONTHLY_HINT.search(text))
    m = _K_PATTERN.search(text)
    if m:
        rupees = float(m.group(1)) * 1_000
        rupees = rupees * 12 if monthly else rupees
        return round(rupees / 100_000, 2) if rupees >= 100_000 else None

    m = _PLAIN_NUM.search(text)
    if m:
        rupees = float(m.group(1).replace(",", ""))
        if monthly:
            rupees *= 12
        if rupees >= 100_000:
            return round(rupees / 100_000, 2)
        if rupees < 100:  # "12" as LPA shorthand
            return round(rupees, 2)
    return None


_NOTICE_IMMEDIATE = re.compile(r"immediate|serving|already|any ?time", re.I)
_NOTICE_DAYS = re.compile(r"(\d+)\s*d", re.I)
_NOTICE_MONTHS = re.compile(r"(\d+(?:\.\d+)?)\s*m", re.I)
_NOTICE_WEEKS = re.compile(r"(\d+)\s*w", re.I)


def parse_notice_to_days(raw) -> Optional[int]:
    """'15 days'→15, '2 months'→60, '1 Month'→30, 'Immediate'→0,
    bare '45'→45 (capped at 365)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        d = int(raw)
        return d if 0 <= d <= 365 else None
    text = str(raw).strip()
    if not text:
        return None
    if _NOTICE_IMMEDIATE.search(text):
        return 0
    m = _NOTICE_MONTHS.search(text)
    if m:
        return min(int(float(m.group(1)) * 30), 365)
    m = _NOTICE_WEEKS.search(text)
    if m:
        return min(int(m.group(1)) * 7, 365)
    m = _NOTICE_DAYS.search(text)
    if m:
        return min(int(m.group(1)), 365)
    if text.isdigit():
        d = int(text)
        return d if d <= 365 else None
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════
# Neural envelope — every vector carries provenance
# ═══════════════════════════════════════════════════════════════════════

class EmbeddingEnvelope(BaseModel):
    vector: List[float]
    model: str                      # e.g. "BAAI/bge-base-en-v1.5"
    dim: int
    computed_at: datetime = Field(default_factory=utcnow)

    @field_validator("dim")
    @classmethod
    def _dim_matches(cls, v, info):
        vec = info.data.get("vector")
        if vec is not None and len(vec) != v:
            raise ValueError(f"dim {v} != len(vector) {len(vec)}")
        return v


# ═══════════════════════════════════════════════════════════════════════
# Ontology entities
# ═══════════════════════════════════════════════════════════════════════

class SkillCategory(str, Enum):
    technical = "technical"
    functional = "functional"
    tool = "tool"
    certification = "certification"
    soft = "soft"


class SkillEntity(BaseModel):
    id: str                         # "skill:sap-mm"
    canonical_name: str
    aliases: List[str] = []
    category: SkillCategory = SkillCategory.technical
    parent_skill_id: Optional[str] = None   # "skill:sap"
    embedding: Optional[EmbeddingEnvelope] = None
    usage_count: int = 0            # mentions across candidate_bank
    schema_version: str = SCHEMA_VERSION
    updated_at: datetime = Field(default_factory=utcnow)


class Seniority(str, Enum):
    entry = "entry"
    executive = "executive"
    senior_executive = "senior_executive"
    manager = "manager"
    senior_manager = "senior_manager"
    head = "head"
    director = "director"
    cxo = "cxo"


class RoleEntity(BaseModel):
    id: str                         # "role:territory-sales-manager"
    canonical_name: str
    aliases: List[str] = []
    function: Optional[str] = None  # "Sales", "Manufacturing", "HR"
    seniority: Optional[Seniority] = None
    embedding: Optional[EmbeddingEnvelope] = None
    usage_count: int = 0
    schema_version: str = SCHEMA_VERSION
    updated_at: datetime = Field(default_factory=utcnow)


class CompanyEntity(BaseModel):
    id: str                         # "co:berger-paints"
    canonical_name: str
    aliases: List[str] = []
    industry: Optional[str] = None
    size_band: Optional[str] = None  # "1-50", "51-500", "500+"
    schema_version: str = SCHEMA_VERSION
    updated_at: datetime = Field(default_factory=utcnow)


class LocationEntity(BaseModel):
    id: str                         # "loc:bengaluru"
    canonical_name: str
    aliases: List[str] = []
    state: Optional[str] = None
    country: str = "IN"
    tier: Optional[int] = None      # 1/2/3
    lat: Optional[float] = None
    lng: Optional[float] = None
    schema_version: str = SCHEMA_VERSION
    updated_at: datetime = Field(default_factory=utcnow)


# ═══════════════════════════════════════════════════════════════════════
# Candidate — canonical additions (live ALONGSIDE legacy fields)
# ═══════════════════════════════════════════════════════════════════════

class SkillRef(BaseModel):
    skill_id: str
    evidence: Optional[str] = None      # the raw string that resolved here
    last_used_year: Optional[int] = None
    primary: bool = False


class ConsentBlock(BaseModel):
    """DPDP: consent lives with the canonical record."""
    status: str = "unknown"             # granted | revoked | unknown
    channel: Optional[str] = None       # capture | whatsapp | portal
    recorded_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class Provenance(BaseModel):
    source: Optional[str] = None        # naukri | linkedin | portal | referral
    captured_by: Optional[str] = None
    parser_version: Optional[str] = None
    resolved_at: Optional[datetime] = None  # last canonical resolution


class CanonicalCandidateFields(BaseModel):
    """
    The v1 additive block written onto candidate_bank documents.
    Legacy fields (skills, key_skills, current_location, ...) remain
    untouched; queries migrate to these as resolution coverage grows.
    """
    skill_ids: List[SkillRef] = []
    role_id: Optional[str] = None
    company_id: Optional[str] = None
    location_id: Optional[str] = None
    preferred_location_ids: List[str] = []
    current_lpa: Optional[float] = None
    expected_lpa: Optional[float] = None
    notice_days: Optional[int] = None
    experience_months: Optional[int] = None
    profile_embedding: Optional[EmbeddingEnvelope] = None
    skills_embedding: Optional[EmbeddingEnvelope] = None     # facet (v2)
    narrative_embedding: Optional[EmbeddingEnvelope] = None  # facet (v2)
    consent: ConsentBlock = ConsentBlock()
    provenance: Provenance = Provenance()
    schema_version: str = SCHEMA_VERSION


# ═══════════════════════════════════════════════════════════════════════
# Mandate — structured requirements
# ═══════════════════════════════════════════════════════════════════════

class SkillRequirement(BaseModel):
    skill_id: str
    weight: float = 1.0
    must_have: bool = False


class CanonicalMandateFields(BaseModel):
    skill_requirements: List[SkillRequirement] = []
    role_id: Optional[str] = None
    min_experience_months: Optional[int] = None
    max_experience_months: Optional[int] = None
    budget_min_lpa: Optional[float] = None
    budget_max_lpa: Optional[float] = None
    location_ids: List[str] = []
    remote_ok: bool = False
    max_notice_days: Optional[int] = None
    mandate_embedding: Optional[EmbeddingEnvelope] = None
    schema_version: str = SCHEMA_VERSION


# ═══════════════════════════════════════════════════════════════════════
# Relations — the graph layer (edges collection, populated in v2)
# ═══════════════════════════════════════════════════════════════════════

class Rel(str, Enum):
    HAS_SKILL = "HAS_SKILL"
    HELD_ROLE = "HELD_ROLE"
    WORKED_AT = "WORKED_AT"
    IN_LOCATION = "IN_LOCATION"
    PREFERS_LOCATION = "PREFERS_LOCATION"
    SIMILAR_TO = "SIMILAR_TO"          # precomputed kNN
    MATCHED_TO = "MATCHED_TO"          # candidate ↔ mandate, weight=score
    SHORTLISTED = "SHORTLISTED"        # outcome edges → LTR training data
    SUBMITTED = "SUBMITTED"
    INTERVIEWED = "INTERVIEWED"
    PLACED = "PLACED"
    REJECTED = "REJECTED"


class Edge(BaseModel):
    src: str                            # "cand:{id}" | "mandate:{id}" | ontology id
    src_type: str
    rel: Rel
    dst: str
    dst_type: str
    weight: float = 1.0
    evidence: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
