"""
Team Lead helpers — recruiters granted acting-employer access by their employer/admin.

A Team Lead is a recruiter with is_team_lead=True and team_lead_employer_id=<employer.id>.
They can:
  - View team + pipeline for that employer
  - Create/edit mandates for that employer
  - Assign mandates to recruiters under the employer's team
They CANNOT see confidential financial data — billing, commissions, margins, contract notes.
Candidate CTC (current + expected) IS visible.
"""
from typing import Optional
from fastapi import HTTPException


CONFIDENTIAL_KEYS = {
    "billing_rate", "billing_rates",
    "invoice_amount", "invoice_amounts", "invoice_total",
    "gross_margin", "net_margin", "margin",
    "recruiter_commission", "referral_payout", "commission_percent", "commission",
    "contract_notes", "private_notes",
    "commercial", "commercials",
    "financial", "financials",
    "revenue", "cost",
    "payout", "payouts",
}


def get_effective_employer_id(user: dict) -> Optional[str]:
    """Return the employer_id this user acts as, or None.

    - role=employer  -> own id
    - is_team_lead   -> team_lead_employer_id
    - anything else  -> None
    """
    if user.get("role") == "employer":
        return user.get("id")
    if user.get("role") == "recruiter" and user.get("is_team_lead"):
        return user.get("team_lead_employer_id")
    return None


def require_employer_scope(user: dict) -> str:
    """Assert the user has employer scope (own or delegated). Returns the employer_id."""
    eid = get_effective_employer_id(user)
    if not eid:
        raise HTTPException(status_code=403, detail="Employer access required")
    return eid


def is_team_lead(user: dict) -> bool:
    return bool(user.get("role") == "recruiter" and user.get("is_team_lead"))


def mask_confidential(obj, user: dict):
    """Deep-scrub confidential keys from any dict/list when viewer is a Team Lead.
    Admin, employer, and non-team-lead recruiters see everything they normally do.
    """
    if not is_team_lead(user):
        return obj
    return _scrub(obj)


def _scrub(obj):
    if isinstance(obj, dict):
        return {
            k: _scrub(v)
            for k, v in obj.items()
            if k not in CONFIDENTIAL_KEYS
        }
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj
