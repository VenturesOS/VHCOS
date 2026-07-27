"""
screening_script.py — compile a mandate into Asha's question flow
=================================================================

compile_script(job) -> list[Block]

Reads canonical mandate fields when present (Phase 9) and falls back to
legacy job fields, producing an ordered list of question blocks. Order
is rejection-cheapest-first: if the mandate caps notice at 30 days, the
notice question runs before five skill probes.

Block shape:
  {id, kind, param, must_have, en, hi}
kinds: consent | identity | notice | experience | skill | ctc_current |
       ctc_expected | location | custom

Templates carry a {name} placeholder; the engine substitutes and (when
AGENT_LLM=1) may rephrase naturally in the candidate's language — but
the SEQUENCE and MEANING come from here, never from the LLM.

Compliance: compile_script raises BlockedQuestionError for any custom
question touching protected themes (religion, caste, marital status,
pregnancy/children, age beyond work-eligibility, disability fishing).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from models.neural_schema import parse_salary_to_lpa


class BlockedQuestionError(ValueError):
    """Raised when a custom question violates the protected-topics policy."""


_BLOCKED = re.compile(
    r"religion|religious|hindu|muslim|christian|sikh|caste|jaat|jati|"
    r"marital|married|shaadi|husband|wife|spouse|pregnan|children|bachch|"
    r"family planning|date of birth|\bage\b|kitne saal (ke|ki) (ho|hain)|"
    r"disabilit|handicap",
    re.I,
)

MAX_SKILL_PROBES = 5


def _first(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def _job_skills(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Prefer canonical skill_requirements; fall back to legacy lists."""
    canon = job.get("skill_requirements") or []
    if canon:
        out = []
        for s in canon:
            name = s.get("skill_name") or s.get("skill_id", "").split(":", 1)[-1].replace("-", " ")
            out.append({"name": name, "must_have": bool(s.get("must_have")), "skill_id": s.get("skill_id")})
        return out
    raw = _first(job.get("key_skills"), job.get("skills"), job.get("skills_required")) or []
    if isinstance(raw, str):
        raw = [x.strip() for x in re.split(r"[,|/]", raw) if x.strip()]
    return [{"name": s, "must_have": False, "skill_id": None} for s in raw]


def _exp_band(job) -> (Optional[float], Optional[float]):
    lo = _first(job.get("min_experience_months"), None)
    hi = _first(job.get("max_experience_months"), None)
    if lo is not None or hi is not None:
        return (lo / 12 if lo else None, hi / 12 if hi else None)
    return (
        _first(job.get("min_experience"), job.get("experience_min"), job.get("min_exp")),
        _first(job.get("max_experience"), job.get("experience_max"), job.get("max_exp")),
    )


def _budget_lpa(job) -> (Optional[float], Optional[float]):
    lo = _first(job.get("budget_min_lpa"), parse_salary_to_lpa(job.get("salary_min")))
    hi = _first(job.get("budget_max_lpa"), parse_salary_to_lpa(job.get("salary_max")))
    return lo, hi


def _notice_cap(job) -> Optional[int]:
    v = job.get("max_notice_days")
    if isinstance(v, (int, float)):
        return int(v)
    return None


def compile_script(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    title = _first(job.get("title"), job.get("job_title"), "this role")
    location = _first(job.get("location"), "the job location")
    skills = _job_skills(job)
    exp_lo, exp_hi = _exp_band(job)
    notice_cap = _notice_cap(job)

    blocks: List[Dict[str, Any]] = []

    # ── 0. Consent + AI disclosure (always first, non-negotiable) ──
    blocks.append({
        "id": "consent", "kind": "consent", "param": None, "must_have": True,
        "en": ("Hi {name}, this is Asha, an AI assistant calling on behalf of "
               f"Ventures HRD Centre regarding a {title} opportunity. "
               "I'd like to ask a few short screening questions (takes ~3 minutes). "
               "Reply YES to continue, or reply HUMAN anytime to talk to our recruiter. "
               "Reply STOP to opt out."),
        "hi": ("Namaste {name}, main Asha hoon — Ventures HRD Centre ki AI assistant, "
               f"{title} position ke liye. Kya main 2-3 minute ke kuch chhote sawaal "
               "puchh sakti hoon? Haan ke liye YES likhein. Kabhi bhi HUMAN likhein "
               "recruiter se baat karne ke liye, ya STOP likhein band karne ke liye."),
    })

    # ── 1. Identity confirm ──
    blocks.append({
        "id": "identity", "kind": "identity", "param": None, "must_have": True,
        "en": "Great, thank you! Just to confirm — am I speaking with {name}?",
        "hi": "Dhanyawaad! Confirm karna tha — kya aap {name} hi hain?",
    })

    # ── 2+. Requirement questions, cheapest rejection first ──
    req: List[Dict[str, Any]] = []

    if notice_cap is not None:
        req.append(({
            "id": "notice", "kind": "notice", "param": {"cap_days": notice_cap}, "must_have": True,
            "en": "What is your current notice period? (e.g., 15 days / 1 month / immediate)",
            "hi": "Aapka notice period kitna hai? (jaise 15 din / 1 mahina / immediate)",
        }, 0))
    else:
        req.append(({
            "id": "notice", "kind": "notice", "param": {}, "must_have": False,
            "en": "What is your current notice period? (e.g., 15 days / 1 month / immediate)",
            "hi": "Aapka notice period kitna hai? (jaise 15 din / 1 mahina / immediate)",
        }, 3))

    band_txt = ""
    if exp_lo and exp_hi:
        band_txt = f" (this role needs {exp_lo:g}–{exp_hi:g} years)"
    elif exp_lo:
        band_txt = f" (this role needs {exp_lo:g}+ years)"
    req.append(({
        "id": "experience", "kind": "experience",
        "param": {"min_years": exp_lo, "max_years": exp_hi},
        "must_have": bool(exp_lo),
        "en": f"How many years of total relevant experience do you have{band_txt}?",
        "hi": f"Aapke paas total kitne saal ka relevant experience hai{band_txt}?",
    }, 1 if exp_lo else 3))

    for i, s in enumerate(sorted(skills, key=lambda x: not x["must_have"])[:MAX_SKILL_PROBES]):
        req.append(({
            "id": f"skill_{i}", "kind": "skill",
            "param": {"skill": s["name"], "skill_id": s.get("skill_id")},
            "must_have": s["must_have"],
            "en": f"Do you have hands-on experience with {s['name']}? (Yes/No — a one-line detail helps)",
            "hi": f"Kya aapko {s['name']} ka hands-on experience hai? (Haan/Nahi — ek line detail bhi likh dein)",
        }, 2 if s["must_have"] else 4))

    b_lo, b_hi = _budget_lpa(job)
    req.append(({
        "id": "ctc_current", "kind": "ctc_current", "param": {}, "must_have": False,
        "en": "What is your current annual CTC? (e.g., 8.5 LPA)",
        "hi": "Aapki current annual CTC kitni hai? (jaise 8.5 LPA)",
    }, 5))
    req.append(({
        "id": "ctc_expected", "kind": "ctc_expected",
        "param": {"budget_min_lpa": b_lo, "budget_max_lpa": b_hi}, "must_have": False,
        "en": "And what CTC are you expecting?",
        "hi": "Aur aap kitni CTC expect kar rahe hain?",
    }, 5))

    req.append(({
        "id": "location", "kind": "location", "param": {"location": location}, "must_have": False,
        "en": f"The role is based in {location}. Are you currently there or open to relocating?",
        "hi": f"Yeh role {location} mein hai. Kya aap wahan hain ya relocate kar sakte hain?",
    }, 2))

    req.sort(key=lambda t: t[1])
    blocks.extend(b for b, _ in req)

    # ── Custom questions from the mandate (policy-filtered) ──
    for j, q in enumerate((job.get("screening_questions") or [])[:5]):
        text = q if isinstance(q, str) else q.get("text", "")
        if not text.strip():
            continue
        if _BLOCKED.search(text):
            raise BlockedQuestionError(
                f"Custom screening question blocked by policy (protected topic): {text!r}"
            )
        blocks.append({
            "id": f"custom_{j}", "kind": "custom", "param": {"text": text},
            "must_have": bool(isinstance(q, dict) and q.get("must_have")),
            "en": text, "hi": text,
        })

    return blocks
