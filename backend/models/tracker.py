"""
Tracker-related Pydantic models.
Models for submission tracker templates, trackers, and row operations.
"""
from pydantic import BaseModel
from typing import Optional, List


class ColumnDef(BaseModel):
    key: str
    label: str
    category: str = "Custom"
    field_type: str = "text"
    required: bool = False
    order: int = 0
    dropdown_options: Optional[List[str]] = None
    is_custom: bool = False


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    client_id: Optional[str] = None
    employer_id: Optional[str] = None
    columns: List[ColumnDef]


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    columns: Optional[List[ColumnDef]] = None


class TrackerCreate(BaseModel):
    name: str
    mandate_id: str
    client_id: Optional[str] = None
    employer_id: Optional[str] = None
    team_id: Optional[str] = None
    template_id: str


class AddRowRequest(BaseModel):
    candidate_id: str
    application_id: str
    data: Optional[dict] = None


class UpdateRowRequest(BaseModel):
    data: dict


class UpdateRowStatusRequest(BaseModel):
    submission_status: str


class DuplicateTrackerRequest(BaseModel):
    name: str
    mandate_id: Optional[str] = None
