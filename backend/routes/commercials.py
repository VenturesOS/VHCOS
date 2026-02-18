"""
VHC Talent OS - Commercial Intelligence Routes
Handles commercial configurations and revenue calculations.
Refactored from server.py for better code organization.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from config import db
from utils import get_current_user, require_role

# Create router
commercials_router = APIRouter(prefix="/api", tags=["Commercials"])

logger = logging.getLogger(__name__)


# ============== PYDANTIC MODELS ==============

class CommercialCreate(BaseModel):
    company_id: str
    commercial_name: str
    type: str  # "percentage", "fixed", "level_based"
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    level_config: Optional[Dict[str, float]] = None  # {"junior": 8, "mid": 10, "senior": 12}
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    job_level: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: bool = True


class CommercialUpdate(BaseModel):
    commercial_name: Optional[str] = None
    type: Optional[str] = None
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    level_config: Optional[Dict[str, float]] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    job_level: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: Optional[bool] = None


class CommercialResponse(BaseModel):
    id: str
    company_id: str
    company_name: Optional[str] = None
    commercial_name: str
    type: str
    fee_percentage: Optional[float] = None
    fixed_amount: Optional[float] = None
    level_config: Optional[Dict[str, float]] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    job_level: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: bool = True
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        extra = "ignore"


# ============== HELPER FUNCTIONS ==============

def calculate_revenue(offered_salary: float, commercial: dict, job_level: Optional[str] = None) -> float:
    """Legacy wrapper — delegates to central revenue engine.
    Returns float for backward compatibility with server.py pipeline calculations.
    Returns 0 if calculation fails (pipeline forecast tolerance)."""
    from services.revenue_engine import calculate_revenue as _engine_calc, RevenueCalculationError
    try:
        result = _engine_calc(offered_salary, commercial)
        return result["revenue_amount"]
    except RevenueCalculationError:
        return 0.0


async def get_applicable_commercial(
    company_id: str,
    salary: Optional[float] = None,
    job_level: Optional[str] = None
) -> Optional[dict]:
    """Get the applicable commercial from the company document."""
    company = await db.companies.find_one({"id": company_id}, {"_id": 0, "commercial": 1})
    if not company or not company.get("commercial"):
        return None
    return company["commercial"]


# ============== COMMERCIAL CRUD ==============

@commercials_router.post("/commercials", response_model=CommercialResponse)
async def create_commercial(
    commercial_data: CommercialCreate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Create a commercial configuration for a company."""
    company = await db.companies.find_one({"id": commercial_data.company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this company")
    
    # Validate commercial type fields
    if commercial_data.type == "percentage" and commercial_data.fee_percentage is None:
        raise HTTPException(status_code=400, detail="fee_percentage required for percentage type")
    if commercial_data.type == "fixed" and commercial_data.fixed_amount is None:
        raise HTTPException(status_code=400, detail="fixed_amount required for fixed type")
    if commercial_data.type == "level_based" and commercial_data.level_config is None:
        raise HTTPException(status_code=400, detail="level_config required for level_based type")
    
    commercial_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    commercial_doc = {
        "id": commercial_id,
        "company_id": commercial_data.company_id,
        "company_name": company.get("name"),
        "commercial_name": commercial_data.commercial_name,
        "type": commercial_data.type,
        "fee_percentage": commercial_data.fee_percentage,
        "fixed_amount": commercial_data.fixed_amount,
        "level_config": commercial_data.level_config,
        "salary_min": commercial_data.salary_min,
        "salary_max": commercial_data.salary_max,
        "job_level": commercial_data.job_level,
        "effective_from": commercial_data.effective_from or now,
        "effective_to": commercial_data.effective_to,
        "is_active": commercial_data.is_active,
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "updated_at": now,
        "audit_log": [{
            "action": "created",
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        }]
    }
    
    await db.commercials.insert_one(commercial_doc)
    logger.info(f"Commercial '{commercial_data.commercial_name}' created for company {company.get('name')}")
    
    return CommercialResponse(**commercial_doc)


@commercials_router.get("/commercials", response_model=List[CommercialResponse])
async def get_commercials(
    company_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get commercials based on user role."""
    query = {}
    
    if current_user["role"] == "employer":
        assigned_companies = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
        query["company_id"] = {"$in": company_ids}
    
    if company_id:
        query["company_id"] = company_id
    if is_active is not None:
        query["is_active"] = is_active
    
    commercials = await db.commercials.find(query, {"_id": 0}).to_list(1000)
    return [CommercialResponse(**c) for c in commercials]


@commercials_router.get("/commercials/{commercial_id}", response_model=CommercialResponse)
async def get_commercial(
    commercial_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get a specific commercial by ID."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": commercial["company_id"]}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return CommercialResponse(**commercial)


@commercials_router.put("/commercials/{commercial_id}", response_model=CommercialResponse)
async def update_commercial(
    commercial_id: str,
    update_data: CommercialUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Update a commercial configuration."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": commercial["company_id"]}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_dict["updated_at"] = now
    
    audit_entry = {
        "action": "updated",
        "changes": list(update_dict.keys()),
        "by_id": current_user["id"],
        "by_name": current_user["name"],
        "by_role": current_user["role"],
        "timestamp": now
    }
    
    await db.commercials.update_one(
        {"id": commercial_id},
        {
            "$set": update_dict,
            "$push": {"audit_log": audit_entry}
        }
    )
    
    updated = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    return CommercialResponse(**updated)


@commercials_router.delete("/commercials/{commercial_id}")
async def delete_commercial(
    commercial_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Soft delete (deactivate) a commercial. Admin only."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.commercials.update_one(
        {"id": commercial_id},
        {
            "$set": {"is_active": False, "updated_at": now},
            "$push": {"audit_log": {
                "action": "deactivated",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": current_user["role"],
                "timestamp": now
            }}
        }
    )
    
    return {"message": "Commercial deactivated successfully"}


# ============== REVENUE CALCULATION ==============

@commercials_router.post("/revenue/calculate")
async def calculate_application_revenue(
    application_id: str,
    offered_salary: float,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Calculate and store revenue for an application."""
    application = await db.applications.find_one({"id": application_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    job = await db.jobs.find_one({"id": application["job_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    company_id = job.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Job has no company assigned")
    
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    commercial = await get_applicable_commercial(
        company_id,
        salary=offered_salary,
        job_level=job.get("job_level")
    )
    
    if not commercial:
        raise HTTPException(status_code=400, detail="No commercial configured for this company")
    
    calculated_revenue = calculate_revenue(
        offered_salary,
        commercial,
        job.get("job_level")
    )
    
    now = datetime.now(timezone.utc).isoformat()
    
    existing = await db.revenue.find_one({"application_id": application_id}, {"_id": 0})
    
    comm_type = commercial.get("type", "")
    fee_pct = commercial.get("percentage_value") or commercial.get("fee_percentage")
    fixed_amt = commercial.get("fixed_fee_amount") or commercial.get("fixed_amount")

    if existing:
        await db.revenue.update_one(
            {"application_id": application_id},
            {
                "$set": {
                    "offered_salary": offered_salary,
                    "commercial_type": comm_type,
                    "fee_percentage": fee_pct,
                    "fixed_amount": fixed_amt,
                    "calculated_revenue": calculated_revenue,
                    "final_revenue": existing.get("manual_override") or calculated_revenue,
                    "stage": application.get("stage", "offered"),
                    "updated_at": now
                },
                "$push": {"audit_log": {
                    "action": "recalculated",
                    "offered_salary": offered_salary,
                    "calculated_revenue": calculated_revenue,
                    "by_id": current_user["id"],
                    "by_name": current_user["name"],
                    "timestamp": now
                }}
            }
        )
        revenue_id = existing["id"]
    else:
        revenue_id = str(uuid.uuid4())
        revenue_doc = {
            "id": revenue_id,
            "application_id": application_id,
            "job_id": application["job_id"],
            "job_title": job.get("title"),
            "candidate_id": application.get("candidate_id"),
            "candidate_name": application.get("candidate_name"),
            "company_id": company_id,
            "offered_salary": offered_salary,
            "commercial_type": comm_type,
            "fee_percentage": fee_pct,
            "fixed_amount": fixed_amt,
            "calculated_revenue": calculated_revenue,
            "manual_override": None,
            "final_revenue": calculated_revenue,
            "stage": application.get("stage", "offered"),
            "is_closed": application.get("stage") == "hired",
            "created_at": now,
            "created_by": current_user["id"],
            "audit_log": [{
                "action": "created",
                "offered_salary": offered_salary,
                "calculated_revenue": calculated_revenue,
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "timestamp": now
            }]
        }
        await db.revenue.insert_one(revenue_doc)
    
    await db.applications.update_one(
        {"id": application_id},
        {"$set": {"offered_salary": offered_salary, "updated_at": now}}
    )
    
    return {
        "revenue_id": revenue_id,
        "application_id": application_id,
        "offered_salary": offered_salary,
        "commercial_type": comm_type,
        "fee_percentage": fee_pct,
        "calculated_revenue": calculated_revenue,
        "final_revenue": calculated_revenue
    }


@commercials_router.put("/revenue/{revenue_id}/override")
async def override_revenue(
    revenue_id: str,
    manual_override: float,
    reason: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin-only: Manually override calculated revenue."""
    revenue = await db.revenue.find_one({"id": revenue_id}, {"_id": 0})
    if not revenue:
        raise HTTPException(status_code=404, detail="Revenue entry not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.revenue.update_one(
        {"id": revenue_id},
        {
            "$set": {
                "manual_override": manual_override,
                "final_revenue": manual_override,
                "updated_at": now
            },
            "$push": {"audit_log": {
                "action": "manual_override",
                "previous_revenue": revenue.get("final_revenue"),
                "new_revenue": manual_override,
                "reason": reason,
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "timestamp": now
            }}
        }
    )
    
    updated = await db.revenue.find_one({"id": revenue_id}, {"_id": 0})
    return updated


# ============== REVENUE REPORTS ==============

@commercials_router.get("/revenue/summary")
async def get_revenue_summary(
    company_id: Optional[str] = None,
    period: str = "all",  # "month", "quarter", "year", "all"
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get revenue summary with aggregations."""
    query = {}
    
    if current_user["role"] == "employer":
        assigned = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        query["company_id"] = {"$in": [c["id"] for c in assigned]}
    
    if company_id:
        query["company_id"] = company_id
    
    # Apply period filter
    now = datetime.now(timezone.utc)
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": start.isoformat()}
    elif period == "quarter":
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        start = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": start.isoformat()}
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": start.isoformat()}
    
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "total_revenue": {"$sum": "$final_revenue"},
            "total_offers": {"$sum": 1},
            "avg_revenue": {"$avg": "$final_revenue"},
            "total_salary": {"$sum": "$offered_salary"},
            "closed_count": {"$sum": {"$cond": ["$is_closed", 1, 0]}}
        }}
    ]
    
    results = await db.revenue.aggregate(pipeline).to_list(1)
    
    if not results:
        return {
            "total_revenue": 0,
            "total_offers": 0,
            "avg_revenue": 0,
            "total_salary": 0,
            "closed_count": 0,
            "period": period
        }
    
    return {**results[0], "_id": None, "period": period}


@commercials_router.get("/revenue/by-company")
async def get_revenue_by_company(
    current_user: dict = Depends(require_role(["admin"]))
):
    """Get revenue grouped by company (Admin only)."""
    pipeline = [
        {"$group": {
            "_id": "$company_id",
            "total_revenue": {"$sum": "$final_revenue"},
            "offer_count": {"$sum": 1},
            "closed_count": {"$sum": {"$cond": ["$is_closed", 1, 0]}}
        }},
        {"$sort": {"total_revenue": -1}},
        {"$limit": 50}
    ]
    
    results = await db.revenue.aggregate(pipeline).to_list(50)
    
    # Enrich with company names
    for r in results:
        company = await db.companies.find_one({"id": r["_id"]}, {"name": 1, "_id": 0})
        r["company_name"] = company.get("name") if company else "Unknown"
        r["company_id"] = r.pop("_id")
    
    return results
