"""
LinkedIn Auto-Posting Service
Posts blog articles to the LinkedIn company page when published.
Uses LinkedIn v2 UGC Posts API with organization URN.
"""
import os
import re
import logging
from datetime import datetime, timezone
import httpx

from config import db

logger = logging.getLogger(__name__)

LINKEDIN_UGC_URL = "https://api.linkedin.com/v2/ugcPosts"


async def get_linkedin_settings():
    """Get LinkedIn auto-posting settings from DB."""
    settings = await db.linkedin_settings.find_one({"_id": "config"}, {"_id": 0})
    if not settings:
        return {
            "auto_post_enabled": False,
            "organization_id": "",
        }
    return settings


async def save_linkedin_settings(settings: dict):
    """Save LinkedIn auto-posting settings to DB."""
    await db.linkedin_settings.update_one(
        {"_id": "config"},
        {"$set": {**settings, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def get_linkedin_token():
    """Retrieve stored LinkedIn access token."""
    integration = await db.social_integrations.find_one(
        {"platform": "linkedin"},
        {"_id": 0, "access_token": 1, "profile_name": 1}
    )
    if not integration or not integration.get("access_token"):
        return None
    return integration["access_token"]


async def get_linkedin_profile_urn():
    """Get the LinkedIn member URN (sub) for the connected user."""
    integration = await db.social_integrations.find_one(
        {"platform": "linkedin"},
        {"_id": 0, "access_token": 1, "profile_sub": 1}
    )
    if not integration:
        return None, None
    return integration.get("access_token"), integration.get("profile_sub")


async def post_blog_to_linkedin(blog: dict, is_test: bool = False):
    """
    Post a blog article link to LinkedIn.
    Uses w_member_social to post as the authenticated admin user.
    Returns dict with success status and post details.
    """
    settings = await get_linkedin_settings()
    org_id = settings.get("organization_id", "")

    if not org_id:
        return {"success": False, "error": "LinkedIn Organization ID not configured"}

    access_token = await get_linkedin_token()
    if not access_token:
        return {"success": False, "error": "LinkedIn not connected. Please authorize first."}

    # Get the member's profile URN for posting
    token, profile_sub = await get_linkedin_profile_urn()
    if not profile_sub:
        return {"success": False, "error": "LinkedIn profile info missing. Please re-authorize."}

    # Build the blog URL
    blog_type = blog.get("blog_type", "employer")
    slug = blog.get("slug", "")
    base_path = "industrial-hiring-insights" if blog_type == "employer" else "career-insights"
    blog_url = f"{os.environ.get('SITE_URL', 'https://ventureshrd.com').rstrip('/')}/{base_path}/{slug}"

    title = blog.get("title", "New Blog Post")
    description = blog.get("meta_description", "")
    commentary = f"{title}\n\n{description}\n\nRead more: {blog_url}" if description else f"{title}\n\nRead more: {blog_url}"

    if is_test:
        commentary = f"[Test Post] {commentary}"

    # Post as the authenticated member (admin user)
    author_urn = f"urn:li:person:{profile_sub}"

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": commentary},
                "shareMediaCategory": "ARTICLE",
                "media": [
                    {
                        "status": "READY",
                        "originalUrl": blog_url,
                        "title": {"text": title},
                        "description": {"text": description or title},
                    }
                ],
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202402",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(LINKEDIN_UGC_URL, json=payload, headers=headers)

            if response.status_code == 201:
                post_id = response.json().get("id", "")
                logger.info(f"[LinkedIn] Posted blog '{title}' -> {post_id}")

                # Log the post
                await db.linkedin_post_history.insert_one({
                    "blog_id": blog.get("id", ""),
                    "blog_title": title,
                    "blog_slug": slug,
                    "blog_type": blog_type,
                    "linkedin_post_id": post_id,
                    "blog_url": blog_url,
                    "is_test": is_test,
                    "status": "success",
                    "posted_at": datetime.now(timezone.utc).isoformat(),
                })

                return {"success": True, "post_id": post_id, "blog_url": blog_url}

            else:
                error_text = response.text
                logger.error(f"[LinkedIn] Post failed ({response.status_code}): {error_text}")

                await db.linkedin_post_history.insert_one({
                    "blog_id": blog.get("id", ""),
                    "blog_title": title,
                    "blog_slug": slug,
                    "blog_type": blog_type,
                    "linkedin_post_id": "",
                    "blog_url": blog_url,
                    "is_test": is_test,
                    "status": "failed",
                    "error": error_text[:500],
                    "status_code": response.status_code,
                    "posted_at": datetime.now(timezone.utc).isoformat(),
                })

                return {"success": False, "error": f"LinkedIn API error ({response.status_code}): {error_text[:200]}"}

    except httpx.RequestError as e:
        error_msg = str(e)
        logger.error(f"[LinkedIn] Request error: {error_msg}")
        return {"success": False, "error": f"Connection error: {error_msg[:200]}"}


async def auto_post_on_publish(blog: dict):
    """
    Called when a blog is published. Checks settings and posts if enabled.
    Runs as fire-and-forget (errors are logged, not raised).
    """
    try:
        settings = await get_linkedin_settings()
        if not settings.get("auto_post_enabled", False):
            logger.info("[LinkedIn] Auto-posting disabled, skipping.")
            return

        result = await post_blog_to_linkedin(blog)
        if result["success"]:
            logger.info(f"[LinkedIn] Auto-posted blog: {blog.get('title')}")
        else:
            logger.warning(f"[LinkedIn] Auto-post failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"[LinkedIn] Auto-post exception: {e}")


# ── Job → LinkedIn draft generator ─────────────────────────────────────────
# LinkedIn Marketing Developer Platform approval for `w_organization_social`
# is a multi-week process. Until it lands, this generator produces a ready-to-
# copy narrative post text for each active job that an admin pastes into
# LinkedIn manually. Once the scope is approved we can pipe the same text into
# `post_job_to_linkedin()` and flip a switch — no template rewrites needed.

_DEFAULT_HASHTAGS = ["#Hiring", "#IndustrialCareers", "#VenturesHRD"]

# Curated adjective pool per industry — keeps the "we're partnering with a
# ____ client" opener from feeling repetitive across 800+ drafts. Falls back
# to a neutral phrase for anything not in this map.
_INDUSTRY_ADJECTIVE = {
    "manufacturing":       "leading manufacturing",
    "automotive":          "top-tier automotive",
    "aerospace":            "high-precision aerospace",
    "oem":                 "global OEM",
    "pharma":              "growth-stage pharma",
    "pharmaceutical":      "growth-stage pharma",
    "chemical":            "large chemicals",
    "steel":               "integrated steel",
    "metals":              "specialty metals",
    "cement":              "large-scale cement",
    "engineering":         "high-growth engineering",
    "energy":              "energy transition",
    "logistics":           "modern logistics",
    "construction":        "infrastructure & construction",
    "textiles":            "vertically integrated textile",
    "consumer":            "consumer & industrial",
    "fmcg":                "global FMCG",
    "it":                  "high-growth technology",
    "banking":             "leading BFSI",
    "finance":             "financial services",
    "healthcare":          "healthcare",
    "renewable":           "renewable-energy",
    "electronics":         "electronics manufacturing",
    "food":                "food-processing",
}

# Short thematic hooks per function to open the "About the role" section
# when the job has no description on file. Keeps the fallback text from
# reading like the same paragraph on every post.
_FUNCTION_HOOK = {
    "plant head":                "This is an end-to-end plant leadership mandate — full P&L, quality, safety, and delivery ownership.",
    "operations":                "This is an operations leadership role with real ownership over throughput, cost, and cross-shift culture.",
    "quality":                   "This is a critical quality leadership role — customer satisfaction, warranty cost, and process capability all sit on this desk.",
    "engineering":               "This is a hands-on engineering role — design, validation, and cross-functional execution rolled into one.",
    "supply chain":              "This is a supply-chain leadership role — sourcing, planning, and vendor development at scale.",
    "scm":                       "This is a supply-chain leadership role — sourcing, planning, and vendor development at scale.",
    "hr":                        "This is a strategic HR partner role — talent, culture, and business alignment in equal measure.",
    "finance":                   "This is a finance leadership role — controllership, FP&A, and business partnering under one hat.",
    "sales":                     "This is a hunter sales role — quota-carrying, geographically owned, and closely partnered with the delivery org.",
    "marketing":                 "This is a marketing role with clear brand + demand-gen mandate and direct visibility to the CEO office.",
    "design":                    "This is a product/mechanical design role that owns concept-to-release for critical assemblies.",
    "maintenance":               "This is a plant maintenance leadership role — reliability, uptime, and preventive rigour above all.",
    "production":                "This is a production leadership role — daily rate, quality yield, and shopfloor discipline are the metrics that matter.",
    "safety":                    "This is an EHS leadership role — behavioural safety culture, statutory compliance, and zero-harm on the line.",
    "r&d":                       "This is an R&D leadership role with real capex, real timelines, and clear commercialisation targets.",
    "project management":        "This is a project-management leadership role — schedule, cost, safety, and stakeholder alignment across phases.",
    "customer success":          "This is a customer-success leadership role — retention, expansion, and lifecycle ownership across strategic accounts.",
}

# Consulting-firm boilerplate that closes every post. Keeps our name + track
# record top-of-mind for anyone scrolling past the specific role.
_FIRM_BOILERPLATE = (
    "At Ventures HRD Centre, we've helped India's manufacturing, automotive, "
    "aerospace, and OEM leaders build their teams for 25+ years — from plant "
    "heads and quality directors to design engineers and shopfloor talent. "
    "Every mandate we handle is retainer-driven, confidential, and shortlist-first."
)


def _fmt_experience(job: dict) -> str:
    """Return e.g. '3–7 yrs', '10+ yrs', or '' if no range on the job."""
    lo = job.get("experience_min")
    hi = job.get("experience_max")
    if lo is None and hi is None:
        return ""
    if lo is not None and hi is not None:
        return f"{lo}–{hi} yrs" if lo != hi else f"{lo} yrs"
    if lo is not None:
        return f"{lo}+ yrs"
    return f"up to {hi} yrs"


def _title_case_loc(loc: str | None) -> str:
    if not loc:
        return ""
    return " ".join(w.capitalize() if w.isalpha() else w for w in loc.split())


def _fmt_salary(job: dict) -> str:
    """Return e.g. '₹18–24 LPA' or '' if no salary on job.
    Assumes numeric fields are stored in absolute rupees or lakhs. If the
    value looks small (< 1000) we assume it's already in lakhs.
    """
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    if lo is None and hi is None:
        return ""
    cur = job.get("salary_currency") or "INR"
    sym = "₹" if cur in ("INR", "Rs", "rupees") else f"{cur} "

    def _lakh(v):
        if v is None:
            return None
        # If >= 1_00_000 assume raw rupees, convert to lakhs.
        return v / 1_00_000 if v >= 1_00_000 else v

    lo_l = _lakh(lo)
    hi_l = _lakh(hi)
    if lo_l is not None and hi_l is not None:
        return f"{sym}{lo_l:.0f}–{hi_l:.0f} LPA"
    if lo_l is not None:
        return f"{sym}{lo_l:.0f}+ LPA"
    return f"up to {sym}{hi_l:.0f} LPA"


def _clean_paragraph(raw: str | list | None, max_chars: int = 500) -> str:
    """Coerce a description-like field into a clean paragraph, truncated at
    sentence boundary. Handles arrays, HTML fragments, and stray whitespace.
    """
    if not raw:
        return ""
    if isinstance(raw, list):
        raw = " ".join(str(x) for x in raw if x)
    text = str(raw)
    # Strip crude HTML tags without a lib dependency.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    # Truncate at the last full sentence within the window.
    window = text[:max_chars]
    for end in (". ", "! ", "? "):
        idx = window.rfind(end)
        if idx > max_chars * 0.5:
            return window[: idx + 1].strip()
    # Fallback: last word boundary.
    idx = window.rfind(" ")
    return (window[:idx] if idx > 0 else window).strip() + "…"


def _scrub_client_names(text: str, job: dict) -> str:
    """Replace the real client / employer name in a description with a
    neutral phrase before we publish anything on LinkedIn.

    Recruitment mandates are almost always retained under NDA — leaking the
    hiring company's name in a public post breaks that agreement. We source
    every candidate name variation we know from the job doc (`company_name`,
    `client_name`) and swap them for `public_company_alias` if present, else
    "our client".
    """
    if not text:
        return text
    names: list[str] = []
    for k in ("company_name", "client_name"):
        v = job.get(k)
        if v and isinstance(v, str) and v.strip():
            names.append(v.strip())
    if not names:
        return text
    alias = (job.get("public_company_alias") or "our client").strip()
    # Build variant set — include each name AND each significant word (≥3
    # chars) inside multi-word names. E.g. "IBUS networks" → also match
    # bare "IBUS" or "iBUS". Skip common noise words that would over-scrub.
    _NOISE = {"and", "the", "of", "for", "ltd", "limited", "pvt", "private",
              "inc", "llp", "co", "corp", "corporation", "company", "group",
              "networks", "systems", "solutions", "services", "industries",
              "india", "global", "international"}
    variants: set[str] = set()
    for n in names:
        variants.add(n)
        variants.add(n.upper())
        variants.add(n.lower())
        variants.add(n.replace(" ", ""))
        for word in re.split(r"\s+", n):
            if len(word) >= 3 and word.lower() not in _NOISE:
                variants.add(word)
                variants.add(word.upper())
                variants.add(word.lower())
    # Longest first so "IBUS Networks" gets replaced before "IBUS".
    variants_sorted = sorted(variants, key=len, reverse=True)
    scrubbed = text
    for v in variants_sorted:
        if not v:
            continue
        pattern = r"\b" + re.escape(v) + r"\b"
        scrubbed = re.sub(pattern, alias, scrubbed, flags=re.IGNORECASE)
    # Collapse runs like "our client. Our client offers …" that can pile up
    # after multiple replacements adjacent to punctuation.
    scrubbed = re.sub(
        r"(" + re.escape(alias) + r")(\s+" + re.escape(alias) + r"){1,}",
        alias, scrubbed, flags=re.IGNORECASE,
    )
    return scrubbed


def _bullet_list(raw: str | list | None, max_items: int = 5, min_len: int = 3) -> list[str]:
    """Turn a skills / responsibilities field into a de-duped bullet list."""
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.replace("\n", ",").split(",")]
    seen: set[str] = set()
    out: list[str] = []
    for item in raw or []:
        s = re.sub(r"^[\-•\*\d\.\s]+", "", str(item)).strip()
        s = re.sub(r"\s+", " ", s)
        if len(s) < min_len:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def generate_job_linkedin_draft(job: dict) -> dict:
    """
    Build a long-form narrative "We're hiring" LinkedIn post for a job.

    Targets 1,200–1,600 chars — LinkedIn's engagement sweet spot for hiring
    posts. Uses whatever data the job has (description, skills, salary,
    seniority, experience) and falls back to curated function/industry-
    themed language so no draft ever reads like "TODO: fill in the blanks".

    Skeleton:
        🚀 We're hiring: {Title} — {Location}

        {Opener with industry adjective + role + experience}

        About the role
        {job.description or function-themed fallback}

        What we're looking for
        • {up to 5 skills bullets, or 3 generic seniority-appropriate ones}

        The good stuff
        • Ownership + scope
        • {Salary if available}
        • {Location} + industry positioning

        How to apply
        Full JD + application → {job_url}
        Or DM us with your CV. Confidentiality guaranteed.

        {Firm boilerplate}

        {Hashtags}
    """
    site_url = os.environ.get("SITE_URL", "https://ventureshrd.com").rstrip("/")
    job_id = job.get("id") or job.get("job_public_id") or ""
    job_url = f"{site_url}/jobs/{job_id}"

    title = (job.get("title") or "").strip() or "an exciting new role"
    location = _title_case_loc(job.get("location"))
    industry_raw = (job.get("industry") or "").strip().lower()
    industry_adj = _INDUSTRY_ADJECTIVE.get(industry_raw, "leading industrial")
    seniority = (job.get("seniority") or "").strip()
    experience = _fmt_experience(job)
    function = (job.get("function") or "").strip()
    salary = _fmt_salary(job)

    # ── Block 1: hook + role opener ───────────────────────────────────────
    hook_bits = ["🚀 We're hiring:", title]
    if location:
        hook_bits.append(f"— {location}")
    hook = " ".join(hook_bits)

    opener_bits = [f"We're partnering with a {industry_adj} client"]
    if function:
        opener_bits.append(f"to hire a {seniority.lower() + ' ' if seniority else ''}{function} lead")
        opener_bits[-1] = opener_bits[-1].replace("lead lead", "lead")
    else:
        opener_bits.append(f"to hire {'a ' + seniority + ' ' if seniority else 'for our next '}{title}")
    if experience:
        opener_bits.append(f"with {experience} of hands-on experience")
    opener = " ".join(opener_bits).strip() + "."
    opener = re.sub(r"\s+", " ", opener)

    # ── Block 2: About the role ───────────────────────────────────────────
    description = _clean_paragraph(
        job.get("description")
        or job.get("job_description")
        or job.get("summary"),
        max_chars=520,
    )
    # NDA safety: strip any client name that snuck into the JD before we
    # publish it to LinkedIn. Falls back to `public_company_alias` or
    # "our client".
    description = _scrub_client_names(description, job)
    if not description:
        # Function-themed fallback keeps the same slot filled with credible
        # narrative instead of leaving a blank section.
        fn_key = function.lower()
        for k, v in _FUNCTION_HOOK.items():
            if k in fn_key:
                description = v
                break
        if not description:
            description = (
                "This is a high-impact position where the incoming leader owns "
                "outcomes end-to-end, with real visibility to the CXO office and "
                "clear KPIs from day one."
            )

    # ── Block 3: What we're looking for ───────────────────────────────────
    skills_list = (
        _bullet_list(job.get("skills"), max_items=5)
        or _bullet_list(job.get("key_skills"), max_items=5)
        or _bullet_list(job.get("key_responsibilities"), max_items=5)
        or _bullet_list(job.get("responsibilities"), max_items=5)
    )
    if not skills_list:
        # Generic-but-credible fallback — better than an empty bullet list.
        skills_list = [
            f"{experience or '8+ yrs'} in {industry_raw or 'industrial'} operations",
            f"Track record of leading {'a shopfloor / plant team' if 'plant' in function.lower() or 'production' in function.lower() else 'cross-functional stakeholders'}",
            "Strong first-principles thinking and stakeholder management",
        ]
    what_block = "What we're looking for:\n" + "\n".join(f"• {s}" for s in skills_list)

    # ── Block 4: The good stuff ───────────────────────────────────────────
    good_stuff = ["• Ownership of a critical function with clear scope + KPIs"]
    if salary:
        good_stuff.append(f"• Compensation: {salary}")
    if location:
        good_stuff.append(f"• {location}-based role, no ambiguity on growth path")
    else:
        good_stuff.append("• Confidential search with a clearly defined career runway")
    good_stuff.append("• Direct partnership with an accountable leadership team")
    good_block = "The good stuff:\n" + "\n".join(good_stuff)

    # ── Block 5: Apply ────────────────────────────────────────────────────
    apply_block = (
        f"📩 View the full JD and apply → {job_url}\n"
        "Or DM us with your CV — every conversation is confidential."
    )

    # ── Block 6: Hashtags ────────────────────────────────────────────────
    tags = list(_DEFAULT_HASHTAGS)
    if function:
        fn_tag = "#" + "".join(w.capitalize() for w in function.replace("&", "").split())
        if fn_tag not in tags and 1 < len(fn_tag) <= 30:
            tags.insert(1, fn_tag)
    if industry_raw:
        ind_tag = "#" + "".join(w.capitalize() for w in industry_raw.split())
        if ind_tag not in tags and 1 < len(ind_tag) <= 30:
            tags.insert(2, ind_tag)
    if location:
        loc_tag = "#" + "".join(w.capitalize() for w in location.split())
        if loc_tag not in tags and 1 < len(loc_tag) <= 30:
            tags.append(loc_tag + "Jobs")
    tags_line = " ".join(tags)

    # ── Compose final post ────────────────────────────────────────────────
    text = "\n\n".join([
        hook,
        opener,
        "About the role:\n" + description,
        what_block,
        good_block,
        apply_block,
        _FIRM_BOILERPLATE,
        tags_line,
    ])

    return {
        "job_id":       job.get("id"),
        "title":        title,
        "location":     location,
        "function":     function,
        "seniority":    seniority,
        "experience":   experience,
        "url":          job_url,
        "text":         text,
        "char_count":   len(text),
        "posted_at":    job.get("linkedin_posted_at"),
        "updated_at":   job.get("updated_at"),
    }
