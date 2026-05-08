"""
Activity Log Pydantic models.
Models for tracking all actions on candidate profiles.
"""
from pydantic import BaseModel
from typing import Optional, List


class ActivityLogEntry(BaseModel):
    """Single activity log entry"""
    id: str
    candidate_id: str
    candidate_name: Optional[str] = None
    action: str  # captured, updated, cv_uploaded, applied, stage_changed, note_added, approval, match_scored, viewed
    description: str
    details: Optional[dict] = None
    performed_by: str
    performed_by_name: Optional[str] = None
    performed_by_role: Optional[str] = None
    timestamp: str


class ActivityLogResponse(BaseModel):
    """Response for activity log queries"""
    total: int
    page: int
    limit: int
    entries: List[dict]
