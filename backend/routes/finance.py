"""
Finance routes for Accounts role.
Handles invoices, client billing, expenses, and financial reports.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from utils import get_current_user, require_role
from config import db
import io
import csv

finance_router = APIRouter(prefix="/api/finance", tags=["finance"])

ALLOWED_ROLES = ["admin", "accounts"]

# ─── Pydantic Models ─────────────────────────────────────────────────

class InvoiceItem(BaseModel):
    description: str
    quantity: float = 1
    rate: float
    amount: float

class InvoiceCreate(BaseModel):
    client_id: str
    invoice_number: Optional[str] = None
    items: List[InvoiceItem]
    subtotal: float
    gst_percent: float = 18.0
    gst_amount: float
    total: float
    due_date: str
    notes: Optional[str] = None

class InvoiceUpdate(BaseModel):
    items: Optional[List[InvoiceItem]] = None
    subtotal: Optional[float] = None
    gst_percent: Optional[float] = None
    gst_amount: Optional[float] = None
    total: Optional[float] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

class ClientCreate(BaseModel):
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    payment_terms: Optional[str] = "Net 30"
    billing_cycle: Optional[str] = "Monthly"

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    payment_terms: Optional[str] = None
    billing_cycle: Optional[str] = None

class ExpenseCreate(BaseModel):
    category: str
    amount: float
    description: Optional[str] = None
    date: str
    vendor: Optional[str] = None
    payment_method: Optional[str] = None

class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    payment_method: Optional[str] = None

# ─── Invoice Endpoints ───────────────────────────────────────────────

@finance_router.get("/invoices")
async def list_invoices(
    status: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    query = {}
    if status:
        query["status"] = status
    if client_id:
        query["client_id"] = client_id
    
    total = await db.invoices.count_documents(query)
    skip = (page - 1) * limit
    invoices = await db.invoices.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {"invoices": invoices, "total": total, "page": page, "pages": max(1, -(-total // limit))}


@finance_router.post("/invoices")
async def create_invoice(
    data: InvoiceCreate,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc).isoformat()
    
    # Auto-generate invoice number if not provided
    inv_number = data.invoice_number
    if not inv_number:
        count = await db.invoices.count_documents({})
        inv_number = f"INV-{count + 1001:05d}"
    
    # Validate client exists
    client = await db.finance_clients.find_one({"id": data.client_id}, {"_id": 0, "name": 1})
    if not client:
        raise HTTPException(400, "Client not found")
    
    doc = {
        "id": str(uuid.uuid4()),
        "invoice_number": inv_number,
        "client_id": data.client_id,
        "client_name": client["name"],
        "items": [item.dict() for item in data.items],
        "subtotal": data.subtotal,
        "gst_percent": data.gst_percent,
        "gst_amount": data.gst_amount,
        "total": data.total,
        "due_date": data.due_date,
        "notes": data.notes,
        "status": "draft",
        "created_by": user.get("id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)
    return doc


@finance_router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv


@finance_router.patch("/invoices/{invoice_id}")
async def update_invoice(
    invoice_id: str,
    data: InvoiceUpdate,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    updates = {k: v for k, v in data.dict().items() if v is not None}
    if "items" in updates:
        updates["items"] = [item.dict() if hasattr(item, 'dict') else item for item in updates["items"]]
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.invoices.update_one({"id": invoice_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Invoice not found")
    return {"success": True}


@finance_router.post("/invoices/{invoice_id}/send")
async def send_invoice(
    invoice_id: str,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc).isoformat()
    result = await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"status": "sent", "sent_at": now, "updated_at": now}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Invoice not found")
    return {"success": True, "message": "Invoice marked as sent"}


@finance_router.post("/invoices/{invoice_id}/mark-paid")
async def mark_invoice_paid(
    invoice_id: str,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc).isoformat()
    result = await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"status": "paid", "paid_at": now, "updated_at": now}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Invoice not found")
    return {"success": True, "message": "Invoice marked as paid"}


@finance_router.delete("/invoices/{invoice_id}")
async def delete_invoice(
    invoice_id: str,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    result = await db.invoices.delete_one({"id": invoice_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Invoice not found")
    return {"success": True}


# ─── Client Billing Endpoints ────────────────────────────────────────

@finance_router.get("/clients")
async def list_clients(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    query = {}
    if search:
        import re
        query["name"] = {"$regex": re.escape(search), "$options": "i"}
    
    total = await db.finance_clients.count_documents(query)
    skip = (page - 1) * limit
    clients = await db.finance_clients.find(query, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    
    # Calculate outstanding balance for each client
    for client in clients:
        outstanding = await db.invoices.aggregate([
            {"$match": {"client_id": client["id"], "status": {"$in": ["sent", "overdue"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}}
        ]).to_list(1)
        client["outstanding_balance"] = outstanding[0]["total"] if outstanding else 0
    
    return {"clients": clients, "total": total, "page": page, "pages": max(1, -(-total // limit))}


@finance_router.post("/clients")
async def create_client(
    data: ClientCreate,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        **data.dict(),
        "created_by": user.get("id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.finance_clients.insert_one(doc)
    doc.pop("_id", None)
    return doc


@finance_router.patch("/clients/{client_id}")
async def update_client(
    client_id: str,
    data: ClientUpdate,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    updates = {k: v for k, v in data.dict().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.finance_clients.update_one({"id": client_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Client not found")
    return {"success": True}


@finance_router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    # Check if client has invoices
    inv_count = await db.invoices.count_documents({"client_id": client_id})
    if inv_count > 0:
        raise HTTPException(400, f"Cannot delete client with {inv_count} invoices. Delete invoices first.")
    result = await db.finance_clients.delete_one({"id": client_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Client not found")
    return {"success": True}


# ─── Expense Endpoints ───────────────────────────────────────────────

EXPENSE_CATEGORIES = [
    "Office Supplies", "Travel", "Software & Subscriptions", "Salary & Wages",
    "Marketing", "Utilities", "Rent", "Professional Services", "Equipment",
    "Recruitment", "Training", "Miscellaneous"
]

@finance_router.get("/expenses")
async def list_expenses(
    category: Optional[str] = Query(None),
    month: Optional[str] = Query(None, description="YYYY-MM format"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    query = {}
    if category:
        query["category"] = category
    if month:
        query["date"] = {"$regex": f"^{month}"}
    
    total = await db.expenses.count_documents(query)
    skip = (page - 1) * limit
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    
    # Monthly summary
    pipeline = [{"$match": query}, {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}]
    by_category = await db.expenses.aggregate(pipeline).to_list(50)
    
    return {
        "expenses": expenses,
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),
        "categories": EXPENSE_CATEGORIES,
        "summary_by_category": {r["_id"]: {"total": r["total"], "count": r["count"]} for r in by_category},
    }


@finance_router.post("/expenses")
async def create_expense(
    data: ExpenseCreate,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        **data.dict(),
        "created_by": user.get("id"),
        "created_at": now,
        "updated_at": now,
    }
    await db.expenses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@finance_router.patch("/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    data: ExpenseUpdate,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    updates = {k: v for k, v in data.dict().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.expenses.update_one({"id": expense_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Expense not found")
    return {"success": True}


@finance_router.delete("/expenses/{expense_id}")
async def delete_expense(
    expense_id: str,

    user=Depends(require_role(ALLOWED_ROLES)),
):
    result = await db.expenses.delete_one({"id": expense_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Expense not found")
    return {"success": True}


# ─── Revenue Dashboard ───────────────────────────────────────────────

@finance_router.get("/revenue-dashboard")
async def revenue_dashboard(
    period: Optional[str] = Query("current_month"),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc)
    
    if period == "current_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    elif period == "last_3_months":
        start = (now - timedelta(days=90)).isoformat()
    elif period == "last_6_months":
        start = (now - timedelta(days=180)).isoformat()
    elif period == "current_year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # Total revenue (paid invoices)
    paid = await db.invoices.aggregate([
        {"$match": {"status": "paid", "paid_at": {"$gte": start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    
    # Outstanding (sent + overdue)
    outstanding = await db.invoices.aggregate([
        {"$match": {"status": {"$in": ["sent", "overdue"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    
    # Overdue
    overdue = await db.invoices.aggregate([
        {"$match": {"status": "overdue"}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    
    # Total expenses
    expenses = await db.expenses.aggregate([
        {"$match": {"date": {"$gte": start[:10]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]).to_list(1)
    
    # Monthly trend (last 6 months)
    monthly_pipeline = [
        {"$match": {"status": "paid"}},
        {"$addFields": {"month": {"$substr": ["$paid_at", 0, 7]}}},
        {"$group": {"_id": "$month", "revenue": {"$sum": "$total"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}},
        {"$limit": 6}
    ]
    monthly = await db.invoices.aggregate(monthly_pipeline).to_list(6)
    
    # Top clients by revenue
    top_clients = await db.invoices.aggregate([
        {"$match": {"status": "paid"}},
        {"$group": {"_id": "$client_name", "total": {"$sum": "$total"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
        {"$limit": 5}
    ]).to_list(5)
    
    return {
        "total_revenue": paid[0]["total"] if paid else 0,
        "revenue_count": paid[0]["count"] if paid else 0,
        "outstanding": outstanding[0]["total"] if outstanding else 0,
        "outstanding_count": outstanding[0]["count"] if outstanding else 0,
        "overdue": overdue[0]["total"] if overdue else 0,
        "overdue_count": overdue[0]["count"] if overdue else 0,
        "total_expenses": expenses[0]["total"] if expenses else 0,
        "expense_count": expenses[0]["count"] if expenses else 0,
        "net_profit": (paid[0]["total"] if paid else 0) - (expenses[0]["total"] if expenses else 0),
        "monthly_trend": [{"month": m["_id"], "revenue": m["revenue"], "count": m["count"]} for m in reversed(monthly)],
        "top_clients": [{"name": c["_id"], "revenue": c["total"], "invoices": c["count"]} for c in top_clients],
    }


# ─── Financial Reports ───────────────────────────────────────────────

@finance_router.get("/reports/pnl")
async def profit_and_loss(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc)
    if not start_date:
        start_date = now.replace(month=1, day=1).strftime("%Y-%m-%d")
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")
    
    # Revenue by month
    revenue = await db.invoices.aggregate([
        {"$match": {"status": "paid", "paid_at": {"$gte": start_date, "$lte": end_date + "T23:59:59"}}},
        {"$addFields": {"month": {"$substr": ["$paid_at", 0, 7]}}},
        {"$group": {"_id": "$month", "total": {"$sum": "$total"}}},
        {"$sort": {"_id": 1}}
    ]).to_list(50)
    
    # Expenses by category
    expenses_by_cat = await db.expenses.aggregate([
        {"$match": {"date": {"$gte": start_date, "$lte": end_date}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}}
    ]).to_list(50)
    
    # Expenses by month
    expenses_by_month = await db.expenses.aggregate([
        {"$match": {"date": {"$gte": start_date, "$lte": end_date}}},
        {"$addFields": {"month": {"$substr": ["$date", 0, 7]}}},
        {"$group": {"_id": "$month", "total": {"$sum": "$amount"}}},
        {"$sort": {"_id": 1}}
    ]).to_list(50)
    
    total_rev = sum(r["total"] for r in revenue)
    total_exp = sum(e["total"] for e in expenses_by_cat)
    
    return {
        "period": {"start": start_date, "end": end_date},
        "total_revenue": total_rev,
        "total_expenses": total_exp,
        "net_profit": total_rev - total_exp,
        "revenue_by_month": [{"month": r["_id"], "amount": r["total"]} for r in revenue],
        "expenses_by_category": [{"category": e["_id"], "amount": e["total"]} for e in expenses_by_cat],
        "expenses_by_month": [{"month": e["_id"], "amount": e["total"]} for e in expenses_by_month],
    }


@finance_router.get("/reports/aging")
async def aging_report(

    user=Depends(require_role(ALLOWED_ROLES)),
):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    invoices = await db.invoices.find(
        {"status": {"$in": ["sent", "overdue"]}},
        {"_id": 0, "id": 1, "invoice_number": 1, "client_name": 1, "total": 1, "due_date": 1, "status": 1}
    ).to_list(500)
    
    buckets = {"current": [], "30_days": [], "60_days": [], "90_plus": []}
    totals = {"current": 0, "30_days": 0, "60_days": 0, "90_plus": 0}
    
    for inv in invoices:
        due = inv.get("due_date", today)
        try:
            days_overdue = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(due[:10], "%Y-%m-%d")).days
        except ValueError:
            days_overdue = 0
        
        if days_overdue <= 0:
            bucket = "current"
        elif days_overdue <= 30:
            bucket = "30_days"
        elif days_overdue <= 60:
            bucket = "60_days"
        else:
            bucket = "90_plus"
        
        inv["days_overdue"] = max(0, days_overdue)
        buckets[bucket].append(inv)
        totals[bucket] += inv["total"]
    
    return {
        "buckets": buckets,
        "totals": totals,
        "grand_total": sum(totals.values()),
    }


@finance_router.get("/reports/gst-summary")
async def gst_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc)
    if not start_date:
        start_date = now.replace(month=max(1, now.month - 2), day=1).strftime("%Y-%m-%d")
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")
    
    invoices = await db.invoices.find(
        {"created_at": {"$gte": start_date, "$lte": end_date + "T23:59:59"}},
        {"_id": 0, "invoice_number": 1, "client_name": 1, "subtotal": 1, "gst_percent": 1, "gst_amount": 1, "total": 1, "status": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(500)
    
    total_taxable = sum(inv.get("subtotal", 0) for inv in invoices)
    total_gst = sum(inv.get("gst_amount", 0) for inv in invoices)
    
    return {
        "period": {"start": start_date, "end": end_date},
        "invoices": invoices,
        "total_taxable_value": total_taxable,
        "total_gst_collected": total_gst,
        "total_with_gst": total_taxable + total_gst,
    }


# ─── CSV Export Endpoints ────────────────────────────────────────────

@finance_router.get("/export/invoices")
async def export_invoices_csv(
    status: Optional[str] = Query(None),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    query = {}
    if status:
        query["status"] = status
    
    invoices = await db.invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    
    rows = []
    for inv in invoices:
        rows.append({
            "Invoice Number": inv.get("invoice_number", ""),
            "Client": inv.get("client_name", ""),
            "Subtotal": inv.get("subtotal", 0),
            "GST %": inv.get("gst_percent", 0),
            "GST Amount": inv.get("gst_amount", 0),
            "Total": inv.get("total", 0),
            "Status": inv.get("status", ""),
            "Due Date": inv.get("due_date", ""),
            "Created": inv.get("created_at", "")[:10],
        })
    
    return {"rows": rows, "filename": f"invoices_{datetime.now().strftime('%Y%m%d')}.csv"}


@finance_router.get("/export/expenses")
async def export_expenses_csv(
    month: Optional[str] = Query(None),

    user=Depends(require_role(ALLOWED_ROLES)),
):
    query = {}
    if month:
        query["date"] = {"$regex": f"^{month}"}
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(5000)
    
    rows = []
    for exp in expenses:
        rows.append({
            "Date": exp.get("date", ""),
            "Category": exp.get("category", ""),
            "Description": exp.get("description", ""),
            "Amount": exp.get("amount", 0),
            "Vendor": exp.get("vendor", ""),
            "Payment Method": exp.get("payment_method", ""),
        })
    
    return {"rows": rows, "filename": f"expenses_{month or 'all'}_{datetime.now().strftime('%Y%m%d')}.csv"}
