"""
screening_flows.py — v2 conversation flows and mid-flow intelligence
====================================================================

Adds to the v1 screening flow:
  • FAQ interrupts   — candidates ask questions mid-screening; answer
                       from a whitelist of public mandate fields, then
                       re-ask the current question (block not consumed)
  • refresh flow     — stale-profile re-verification journey
  • docs flow        — request/receive documents (blocks of kind "doc")
  • cross-offer      — on NOT_QUALIFIED, find one alternative live
                       mandate the candidate *does* fit and offer it
  • referral tail    — optional share-card after any completed session

Everything here is deterministic; the LLM is never consulted for flow
decisions (same invariant as v1).
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from models.neural_schema import parse_salary_to_lpa

# ═══════════════════════ FAQ interrupt handling ══════════════════════════

_QUESTION_HINT = re.compile(
    r"\?|^(kya|kaun|kitna|kitni|kahan|kab|kyun|why|what|which|who|where|when|how)\b"
    r"|salary kya|ctc kya|company kaun|location kahan|kis company|batao|bata do",
    re.I,
)

_FAQ_PATTERNS: List[tuple] = [
    ("salary",   re.compile(r"salary|ctc|package|pay|paisa|kitna milega", re.I)),
    ("company",  re.compile(r"company|client|firm|organisation|organization|kis company|kaun si company", re.I)),
    ("location", re.compile(r"location|kahan|city|jagah|office kahan|posting", re.I)),
    ("role",     re.compile(r"role|position|designation|kaam kya|profile kya|job kya", re.I)),
    ("process",  re.compile(r"process|next|interview kab|aage kya|kya hoga|steps", re.I)),
    ("about_us", re.compile(r"ventures|vhc|aap kaun|who are you|consultancy", re.I)),
]


def looks_like_question(text: str) -> bool:
    return bool(_QUESTION_HINT.search(text.strip()))


def answer_faq(text: str, job: Dict[str, Any], language: str) -> Optional[str]:
    """Whitelisted answers only. Confidential mandates never reveal the
    client. Returns None when we have no safe answer (caller then defers
    to the recruiter and re-asks)."""
    hi = language in ("hi", "hinglish")
    topic = next((t for t, rx in _FAQ_PATTERNS if rx.search(text)), None)
    if topic is None:
        return None

    if topic == "salary":
        lo = job.get("budget_min_lpa") or parse_salary_to_lpa(job.get("salary_min"))
        hi_ = job.get("budget_max_lpa") or parse_salary_to_lpa(job.get("salary_max"))
        if job.get("hide_salary") or not (lo or hi_):
            return ("Salary aapke experience aur interview ke basis par decide hogi — recruiter details share karenge."
                    if hi else
                    "Compensation depends on your experience and the interview — our recruiter will share specifics.")
        rng = f"{lo:g}–{hi_:g} LPA" if lo and hi_ else f"up to {hi_:g} LPA" if hi_ else f"{lo:g}+ LPA"
        return (f"Is role ki salary range approx {rng} hai (experience ke hisaab se)."
                if hi else f"The indicative range for this role is {rng}, depending on experience.")

    if topic == "company":
        if job.get("confidential") or job.get("is_confidential"):
            return ("Client ka naam is stage par confidential hai — shortlist ke baad recruiter share karenge."
                    if hi else
                    "The client is confidential at this stage — our recruiter will share it once you're shortlisted.")
        name = job.get("company_name") or job.get("company")
        if not name:
            return None
        return (f"Yeh role {name} ke liye hai." if hi else f"This role is with {name}.")

    if topic == "location":
        loc = job.get("location") or "India"
        return (f"Job location {loc} hai." if hi else f"The role is based in {loc}.")

    if topic == "role":
        title = job.get("title") or job.get("job_title") or "this role"
        return (f"Position hai: {title}." if hi else f"The position is: {title}.")

    if topic == "process":
        return ("Yeh 2-3 minute ki screening hai. Fit hone par hamare recruiter interview schedule karenge."
                if hi else
                "This is a 2–3 minute screening. If it's a fit, our recruiter will schedule an interview with you.")

    if topic == "about_us":
        return ("Ventures HRD Centre ek recruitment consultancy hai — hum companies ke liye hiring karte hain. Details: ventureshrd.com"
                if hi else
                "Ventures HRD Centre is a recruitment consultancy — we hire on behalf of client companies. More at ventureshrd.com")
    return None


def unknown_faq_reply(language: str) -> str:
    return ("Achha sawaal — main recruiter se poochh kar batati hoon. Filhaal:"
            if language in ("hi", "hinglish")
            else "Good question — I'll have our recruiter get back to you on that. Meanwhile:")


# ═══════════════════════ refresh flow compiler ═══════════════════════════

def compile_refresh(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Stale-profile re-verification: short, low-friction, no mandate."""
    emp = candidate.get("current_employer") or candidate.get("current_company") or "your last company"
    desig = candidate.get("current_designation") or candidate.get("designation") or "your last role"
    return [
        {"id": "consent", "kind": "consent", "param": None, "must_have": True,
         "en": ("Hi {name}, Asha here from Ventures HRD Centre (AI assistant). "
                "We last spoke a while ago — may I take 60 seconds to update your "
                "profile so we match you to the right roles? Reply YES to continue, "
                "HUMAN for our recruiter, STOP to opt out."),
         "hi": ("Namaste {name}, main Asha — Ventures HRD Centre ki AI assistant. "
                "Kaafi time ho gaya — kya 1 minute mein aapki profile update kar loon "
                "taaki sahi roles match karein? YES likhein. HUMAN = recruiter, STOP = band.")},
        {"id": "same_employer", "kind": "skill", "param": {"skill": f"still at {emp}"}, "must_have": False,
         "en": f"Are you still working at {emp}? (Yes/No — if no, where now?)",
         "hi": f"Kya aap abhi bhi {emp} mein hain? (Haan/Nahi — nahi toh kahan?)"},
        {"id": "designation_now", "kind": "custom", "param": {"prior": desig}, "must_have": False,
         "en": f"What's your current designation? (was: {desig})",
         "hi": f"Aapki current designation kya hai? (pehle: {desig})"},
        {"id": "ctc_current", "kind": "ctc_current", "param": {}, "must_have": False,
         "en": "Your current annual CTC? (e.g., 8.5 LPA)",
         "hi": "Current annual CTC? (jaise 8.5 LPA)"},
        {"id": "notice", "kind": "notice", "param": {}, "must_have": False,
         "en": "Current notice period? (days/months or immediate)",
         "hi": "Notice period kitna hai? (din/mahine ya immediate)"},
        {"id": "open_to_opps", "kind": "skill", "param": {"skill": "open to new opportunities"}, "must_have": False,
         "en": "Are you open to new opportunities right now? (Yes/No)",
         "hi": "Kya aap abhi naye opportunities ke liye open hain? (Haan/Nahi)"},
    ]


# ═══════════════════════ docs flow compiler ══════════════════════════════

DOC_LABELS = {
    "updated_cv": ("your updated CV (PDF/DOC)", "apna updated CV (PDF/DOC)"),
    "photo": ("a recent passport-size photo", "ek recent passport-size photo"),
    "ame_license": ("your AME license copy", "AME license ki copy"),
    "certificates": ("your relevant certificates", "relevant certificates"),
    "id_proof": ("a government ID proof", "government ID proof"),
    "payslip": ("your latest payslip", "latest payslip"),
}


def compile_docs(requested: List[str]) -> List[Dict[str, Any]]:
    blocks = [{
        "id": "consent", "kind": "consent", "param": None, "must_have": True,
        "en": ("Hi {name}, Asha from Ventures HRD Centre (AI assistant). Our recruiter "
               "needs a few documents for your application — may I collect them here? "
               "Reply YES to continue, HUMAN for our recruiter, STOP to opt out."),
        "hi": ("Namaste {name}, main Asha — Ventures HRD Centre ki AI assistant. "
               "Aapki application ke liye kuch documents chahiye — kya yahan bhej "
               "sakte hain? YES likhein. HUMAN = recruiter, STOP = band."),
    }]
    for key in requested:
        en, hi = DOC_LABELS.get(key, (key.replace("_", " "), key.replace("_", " ")))
        blocks.append({
            "id": f"doc_{key}", "kind": "doc", "param": {"doc_key": key}, "must_have": False,
            "en": f"Please send {en} here as an attachment. (Reply SKIP if unavailable right now.)",
            "hi": f"Kripya {hi} yahan attachment mein bhejein. (Abhi nahi hai toh SKIP likhein.)",
        })
    return blocks


# ═══════════════════════ cross-mandate offering ══════════════════════════

def _job_must_skills(job) -> List[str]:
    return [s.get("skill_name") for s in (job.get("skill_requirements") or []) if s.get("must_have")]


async def find_alternative(db, session: Dict[str, Any], candidate: Dict[str, Any],
                           verified: Dict[str, Any], score_fn) -> Optional[Dict[str, Any]]:
    """One best alternative active mandate that clears the constraint the
    candidate just failed. Deterministic rules + the same scorer."""
    if os.environ.get("AGENT_CROSS_OFFER", "1") != "1":
        return None
    cand_skills = {s.lower() for s in
                   [*(candidate.get("key_skills") or []), *(verified.get("verified_skills") or [])]}
    notice = verified.get("notice_days")
    expected = verified.get("expected_lpa")

    jobs = await db.jobs.find({"status": "active"}).to_list(length=100)
    best, best_score = None, 0
    for job in jobs:
        if job.get("id") == session["mandate_id"] or job.get("agent_cross_offer") is False:
            continue
        must = [m for m in _job_must_skills(job) if m]
        if any(m.lower() not in cand_skills for m in must):
            continue
        cap = job.get("max_notice_days")
        if cap is not None and isinstance(notice, int) and notice > cap:
            continue
        bmax = job.get("budget_max_lpa") or parse_salary_to_lpa(job.get("salary_max"))
        if bmax and isinstance(expected, (int, float)) and expected > bmax * 1.15:
            continue
        try:
            merged = dict(candidate)
            merged.update({k: v for k, v in verified.items() if k != "verified_skill_gaps"})
            score = (score_fn(merged, job) or {}).get("score") or 0
        except Exception:
            score = 0
        if score > best_score:
            best, best_score = job, score
    threshold = int(os.environ.get("AGENT_QUALIFY_THRESHOLD", "55"))
    return {"job": best, "score": best_score} if best and best_score >= threshold else None


def cross_offer_text(job: Dict[str, Any], language: str) -> str:
    title = job.get("title") or "another role"
    loc = job.get("location") or ""
    if language in ("hi", "hinglish"):
        return (f"Ek aur role hai jo aapke profile se match karta hai — *{title}*"
                f"{f' ({loc})' if loc else ''}. Kya aap interested hain? (Haan/Nahi)")
    return (f"There's another role that matches your profile — *{title}*"
            f"{f' ({loc})' if loc else ''}. Would you be interested? (Yes/No)")


CARRYABLE_KINDS = {"notice", "experience", "ctc_current", "ctc_expected"}


def carry_answers(new_blocks: List[Dict[str, Any]],
                  old_session: Dict[str, Any]) -> Dict[str, Any]:
    """Pre-fill a new session's answers with already-verified values so
    the candidate is never asked the same thing twice. Skill/location
    blocks are mandate-specific and re-asked; identity/consent re-run."""
    old = old_session.get("answers") or {}
    carried: Dict[str, Any] = {}
    for nb in new_blocks:
        if nb["kind"] in CARRYABLE_KINDS:
            prev = old.get(nb["id"])
            if prev and prev.get("confident") and prev.get("value") is not None:
                carried[nb["id"]] = {**prev, "carried_from": old_session["id"]}
    return carried


# ═══════════════════════ referral tail ═══════════════════════════════════

def referral_text(job: Dict[str, Any], language: str) -> Optional[str]:
    if os.environ.get("AGENT_REFERRAL", "0") != "1":
        return None
    slug = job.get("canonical_slug") or job.get("slug")
    base = os.environ.get("PUBLIC_SITE_URL", "https://ventureshrd.com")
    link = f"{base}/jobs/{slug}?utm_source=referral&utm_medium=whatsapp" if slug else base
    title = job.get("title") or "this role"
    if language in ("hi", "hinglish"):
        return (f"Agar aapke kisi dost ko *{title}* role suit karta hai, unhe yeh link "
                f"forward kar dein 🙏 {link}")
    return (f"If a friend would suit the *{title}* role, feel free to forward them "
            f"this link 🙏 {link}")
