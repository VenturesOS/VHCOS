"""
VHC Talent OS - Bug Reports Routes
Handles user-submitted issue reports and admin review.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from config import db
from utils import require_role

logger = logging.getLogger(__name__)

bug_reports_router = APIRouter(prefix="/api", tags=["Bug Reports"])


class BugReportCreate(BaseModel):
    title: str
    description: str
    page_url: Optional[str] = None
    category: Optional[str] = "general"  # general, login, search, ui, performance, other
    severity: Optional[str] = "medium"  # low, medium, high, critical
    browser_info: Optional[str] = None


class BugReportResponse(BaseModel):
    id: str
    title: str
    description: str
    page_url: Optional[str] = None
    category: str
    severity: str
    status: str
    reported_by: str
    reported_by_name: str
    reported_by_role: str
    browser_info: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: str
    updated_at: str


@bug_reports_router.post("/bug-reports", response_model=BugReportResponse)
async def create_bug_report(
    report: BugReportCreate,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter", "candidate"]))
):
    """Submit a bug report. Available to all authenticated users."""
    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": report_id,
        "title": report.title,
        "description": report.description,
        "page_url": report.page_url,
        "category": report.category or "general",
        "severity": report.severity or "medium",
        "status": "open",
        "reported_by": current_user["id"],
        "reported_by_name": current_user.get("name", ""),
        "reported_by_role": current_user["role"],
        "browser_info": report.browser_info,
        "admin_notes": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.bug_reports.insert_one(doc)
    logger.info(f"Bug report {report_id} created by {current_user['name']} ({current_user['role']})")
    return BugReportResponse(**doc)


@bug_reports_router.get("/bug-reports")
async def get_bug_reports(
    status: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter", "candidate"]))
):
    """
    Get bug reports.
    Admin: sees all. Others: see only their own.
    """
    query = {}
    if current_user["role"] != "admin":
        query["reported_by"] = current_user["id"]
    if status:
        query["status"] = status

    docs = await db.bug_reports.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@bug_reports_router.get("/bug-reports/{report_id}")
async def get_bug_report(
    report_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter", "candidate"]))
):
    """Get a specific bug report."""
    doc = await db.bug_reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bug report not found")
    if current_user["role"] != "admin" and doc.get("reported_by") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return doc


@bug_reports_router.put("/bug-reports/{report_id}")
async def update_bug_report(
    report_id: str,
    status: Optional[str] = None,
    admin_notes: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Update bug report status and notes (Admin only)."""
    doc = await db.bug_reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bug report not found")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if status:
        update["status"] = status
    if admin_notes is not None:
        update["admin_notes"] = admin_notes

    await db.bug_reports.update_one({"id": report_id}, {"$set": update})
    return {"message": "Bug report updated"}


@bug_reports_router.get("/bug-reports/stats/summary")
async def get_bug_report_stats(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get bug report summary stats for admin dashboard."""
    total = await db.bug_reports.count_documents({})
    open_count = await db.bug_reports.count_documents({"status": "open"})
    in_progress = await db.bug_reports.count_documents({"status": "in_progress"})
    resolved = await db.bug_reports.count_documents({"status": "resolved"})
    closed = await db.bug_reports.count_documents({"status": "closed"})

    # By severity
    critical = await db.bug_reports.count_documents({"status": "open", "severity": "critical"})
    high = await db.bug_reports.count_documents({"status": "open", "severity": "high"})

    return {
        "total": total,
        "open": open_count,
        "in_progress": in_progress,
        "resolved": resolved,
        "closed": closed,
        "critical_open": critical,
        "high_open": high,
    }
