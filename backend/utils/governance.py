"""
VHC Talent OS - Data Governance Utilities
Validation, audit logging, and profile freshness tracking for candidate data.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Any

# Import database connection
from config import db


def validate_mandatory_candidate_fields(data: dict, context: str = "candidate") -> List[str]:
    """
    Validate mandatory candidate fields for data completeness.
    Returns list of missing field errors.
    """
    errors = []
    
    # Current Salary - MANDATORY
    current_salary = data.get("current_salary")
    if current_salary is None or (isinstance(current_salary, (int, float)) and current_salary <= 0):
        errors.append("Current salary is mandatory and must be greater than 0")
    
    # Notice Period - MANDATORY
    notice_period = data.get("notice_period")
    if not notice_period or (isinstance(notice_period, str) and not notice_period.strip()):
        errors.append("Notice period is mandatory")
    
    # Location - MANDATORY
    location = data.get("location")
    if not location or (isinstance(location, str) and not location.strip()):
        errors.append("Location is mandatory")
    
    # Experience Years - MANDATORY (can be 0 for freshers)
    experience_years = data.get("experience_years")
    if experience_years is None:
        errors.append("Experience (years) is mandatory")
    
    return errors


def create_profile_audit_entry(
    field: str,
    old_value: Any,
    new_value: Any,
    user_id: str,
    user_name: str,
    user_role: str,
    source: str = "manual_update"
) -> dict:
    """
    Create an audit log entry for profile field changes.
    Tracks changes to: salary, notice_period, location, experience_years
    """
    return {
        "id": str(uuid.uuid4()),
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "changed_by_id": user_id,
        "changed_by_name": user_name,
        "changed_by_role": user_role,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def update_candidate_freshness(candidate_id: str, update_type: str = "profile"):
    """
    Update profile freshness metadata.
    update_type: 'profile' or 'application'
    """
    now = datetime.now(timezone.utc).isoformat()
    update_fields = {}
    
    if update_type == "profile":
        update_fields["last_profile_updated_at"] = now
    elif update_type == "application":
        update_fields["last_application_date"] = now
    
    update_fields["updated_at"] = now
    
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$set": update_fields}
    )


async def add_application_to_history(candidate_id: str, application_data: dict):
    """
    Add an application entry to candidate's internal history.
    This is visible ONLY to Admin/Employer/Recruiter.
    """
    history_entry = {
        "application_id": application_data.get("id"),
        "job_id": application_data.get("job_id"),
        "job_title": application_data.get("job_title"),
        "company_name": application_data.get("company_name"),  # Real name for internal use
        "source": application_data.get("source", "self"),  # self, recruiter, employer, admin, referral
        "applied_at": application_data.get("created_at"),
        "current_stage": application_data.get("stage", "applied"),
        "final_outcome": None,  # Will be updated on closure
        "closure_date": None
    }
    
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {
            "$push": {"application_history": history_entry},
            "$set": {"last_application_date": datetime.now(timezone.utc).isoformat()}
        }
    )


async def update_application_in_history(candidate_id: str, application_id: str, stage: str, outcome: str = None):
    """
    Update an application's stage/outcome in candidate's history.
    """
    update_data = {"application_history.$.current_stage": stage}
    
    if outcome:  # hired, rejected, dropped
        update_data["application_history.$.final_outcome"] = outcome
        update_data["application_history.$.closure_date"] = datetime.now(timezone.utc).isoformat()
    
    await db.candidate_bank.update_one(
        {"id": candidate_id, "application_history.application_id": application_id},
        {"$set": update_data}
    )
