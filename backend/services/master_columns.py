"""
Master Column Definitions for Submission Tracker
Enterprise-grade column system with categories, types, and metadata.
Shared between backend validation and frontend rendering.
"""

FIELD_TYPES = ["text", "number", "currency", "date", "dropdown"]

MASTER_COLUMNS = [
    # ── Basic Info ──
    {"key": "s_no", "label": "S.No", "category": "Basic Info", "field_type": "number", "default_required": False},
    {"key": "candidate_id", "label": "Candidate ID", "category": "Basic Info", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "full_name", "label": "Full Name", "category": "Basic Info", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "gender", "label": "Gender", "category": "Basic Info", "field_type": "dropdown", "default_required": False, "dropdown_options": ["Male", "Female", "Other"]},
    {"key": "date_of_birth", "label": "Date of Birth", "category": "Basic Info", "field_type": "date", "default_required": False},
    {"key": "age", "label": "Age", "category": "Basic Info", "field_type": "number", "default_required": False},

    # ── Role & Mandate ──
    {"key": "position_role", "label": "Position / Role", "category": "Role & Mandate", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "mandate_name", "label": "Mandate Name", "category": "Role & Mandate", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "job_code", "label": "Job Code / Req ID", "category": "Role & Mandate", "field_type": "text", "default_required": False, "auto_fill": True},
    {"key": "recruiter_name", "label": "Recruiter Name", "category": "Role & Mandate", "field_type": "text", "default_required": False, "auto_fill": True},
    {"key": "submission_date", "label": "Submission Date", "category": "Role & Mandate", "field_type": "date", "default_required": True, "auto_fill": True},

    # ── Contact Details ──
    {"key": "mobile_number", "label": "Mobile Number", "category": "Contact Details", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "alternate_number", "label": "Alternate Number", "category": "Contact Details", "field_type": "text", "default_required": False},
    {"key": "email", "label": "Email", "category": "Contact Details", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "linkedin_profile", "label": "LinkedIn Profile", "category": "Contact Details", "field_type": "text", "default_required": False},
    {"key": "portfolio_link", "label": "Portfolio Link", "category": "Contact Details", "field_type": "text", "default_required": False},

    # ── Employment ──
    {"key": "current_company", "label": "Current Company", "category": "Employment", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "current_designation", "label": "Current Designation", "category": "Employment", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "total_experience", "label": "Total Experience", "category": "Employment", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "relevant_experience", "label": "Relevant Experience", "category": "Employment", "field_type": "text", "default_required": False},
    {"key": "reporting_level", "label": "Reporting Level", "category": "Employment", "field_type": "text", "default_required": False},
    {"key": "team_size_managed", "label": "Team Size Managed", "category": "Employment", "field_type": "number", "default_required": False},

    # ── Location ──
    {"key": "current_location", "label": "Current Location", "category": "Location", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "preferred_location", "label": "Preferred Location", "category": "Location", "field_type": "text", "default_required": False},
    {"key": "relocation_preference", "label": "Relocation Preference", "category": "Location", "field_type": "dropdown", "default_required": False, "dropdown_options": ["Yes", "No", "Negotiable"]},
    {"key": "work_mode_preference", "label": "Work Mode Preference", "category": "Location", "field_type": "dropdown", "default_required": False, "dropdown_options": ["On-site", "Remote", "Hybrid"]},

    # ── Compensation ──
    {"key": "current_ctc", "label": "Current CTC", "category": "Compensation", "field_type": "currency", "default_required": True, "auto_fill": True},
    {"key": "fixed_component", "label": "Fixed Component", "category": "Compensation", "field_type": "currency", "default_required": False},
    {"key": "variable_component", "label": "Variable Component", "category": "Compensation", "field_type": "currency", "default_required": False},
    {"key": "expected_ctc", "label": "Expected CTC", "category": "Compensation", "field_type": "currency", "default_required": True, "auto_fill": True},
    {"key": "min_acceptable_ctc", "label": "Minimum Acceptable CTC", "category": "Compensation", "field_type": "currency", "default_required": False},
    {"key": "compensation_flexibility", "label": "Compensation Flexibility", "category": "Compensation", "field_type": "text", "default_required": False},

    # ── Availability ──
    {"key": "notice_period", "label": "Notice Period", "category": "Availability", "field_type": "text", "default_required": True, "auto_fill": True},
    {"key": "last_working_day", "label": "Last Working Day", "category": "Availability", "field_type": "date", "default_required": False},
    {"key": "offer_in_hand", "label": "Offer in Hand", "category": "Availability", "field_type": "dropdown", "default_required": False, "dropdown_options": ["Yes", "No"]},
    {"key": "interview_availability", "label": "Interview Availability", "category": "Availability", "field_type": "text", "default_required": False},

    # ── Education ──
    {"key": "highest_qualification", "label": "Highest Qualification", "category": "Education", "field_type": "text", "default_required": False, "auto_fill": True},
    {"key": "degree", "label": "Degree", "category": "Education", "field_type": "text", "default_required": False},
    {"key": "specialization", "label": "Specialization", "category": "Education", "field_type": "text", "default_required": False},
    {"key": "university", "label": "University", "category": "Education", "field_type": "text", "default_required": False},
    {"key": "graduation_year", "label": "Graduation Year", "category": "Education", "field_type": "number", "default_required": False},
    {"key": "certifications", "label": "Certifications", "category": "Education", "field_type": "text", "default_required": False},

    # ── Skills & Evaluation ──
    {"key": "primary_skills", "label": "Primary Skills", "category": "Skills & Evaluation", "field_type": "text", "default_required": False, "auto_fill": True},
    {"key": "secondary_skills", "label": "Secondary Skills", "category": "Skills & Evaluation", "field_type": "text", "default_required": False},
    {"key": "ai_resume_score", "label": "AI Resume Score", "category": "Skills & Evaluation", "field_type": "number", "default_required": False, "auto_fill": True},
    {"key": "recruiter_rating", "label": "Recruiter Rating", "category": "Skills & Evaluation", "field_type": "number", "default_required": False},
    {"key": "technical_rating", "label": "Technical Rating", "category": "Skills & Evaluation", "field_type": "number", "default_required": False},
    {"key": "communication_rating", "label": "Communication Rating", "category": "Skills & Evaluation", "field_type": "number", "default_required": False},
    {"key": "fitment_score", "label": "Fitment Score", "category": "Skills & Evaluation", "field_type": "number", "default_required": False},

    # ── Submission Intelligence ──
    {"key": "why_shortlisted", "label": "Why Shortlisted", "category": "Submission Intelligence", "field_type": "text", "default_required": False},
    {"key": "key_strengths", "label": "Key Strengths", "category": "Submission Intelligence", "field_type": "text", "default_required": False},
    {"key": "risks_concerns", "label": "Risks / Concerns", "category": "Submission Intelligence", "field_type": "text", "default_required": False},
    {"key": "recruiter_notes", "label": "Recruiter Notes", "category": "Submission Intelligence", "field_type": "text", "default_required": False},
    {"key": "client_feedback", "label": "Client Feedback", "category": "Submission Intelligence", "field_type": "text", "default_required": False},

    # ── Process Tracking ──
    {"key": "profile_shared_date", "label": "Profile Shared Date", "category": "Process Tracking", "field_type": "date", "default_required": False},
    {"key": "interview_round", "label": "Interview Round", "category": "Process Tracking", "field_type": "text", "default_required": False},
    {"key": "offer_status", "label": "Offer Status", "category": "Process Tracking", "field_type": "dropdown", "default_required": False, "dropdown_options": ["Pending", "Issued", "Accepted", "Declined"]},
    {"key": "final_status", "label": "Final Status", "category": "Process Tracking", "field_type": "dropdown", "default_required": False, "dropdown_options": ["In Process", "Selected", "Rejected", "On Hold", "Withdrawn"]},
]

# Column keys that can be auto-filled from candidate/application data
AUTO_FILL_KEYS = [c["key"] for c in MASTER_COLUMNS if c.get("auto_fill")]

# All categories in order
COLUMN_CATEGORIES = list(dict.fromkeys(c["category"] for c in MASTER_COLUMNS))

# Quick lookup by key
COLUMN_MAP = {c["key"]: c for c in MASTER_COLUMNS}

# Default template columns (most commonly used)
DEFAULT_TEMPLATE_COLUMNS = [
    "s_no", "full_name", "position_role", "current_company", "current_designation",
    "total_experience", "current_location", "current_ctc", "expected_ctc",
    "notice_period", "mobile_number", "email", "submission_date",
    "recruiter_notes", "final_status",
]
