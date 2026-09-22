"""Bill / Invoice domain models — Phase 55.6 (May 2026)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ────────────────────────────────────────────────────────────
# Bank accounts (fix.docx 2026-09-15) — user maintains a list,
# picks one per bill; the chosen values snapshot onto the bill
# so later account changes don't mutate old invoices.
# ────────────────────────────────────────────────────────────
class BankAccountBase(BaseModel):
    label: str = Field(..., description="Short human label e.g. 'HDFC Current — Delhi'")
    bank_name: str
    beneficiary_name: str
    branch: str
    account_number: str
    ifsc: str
    is_default: bool = False


class BankAccountCreate(BankAccountBase):
    pass


class BankAccountUpdate(BaseModel):
    label: Optional[str] = None
    bank_name: Optional[str] = None
    beneficiary_name: Optional[str] = None
    branch: Optional[str] = None
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
    is_default: Optional[bool] = None


class BankAccountRecord(BankAccountBase):
    id: str
    created_at: str
    updated_at: Optional[str] = None


class BillBankSnapshot(BaseModel):
    """Bank details frozen onto the bill at creation time."""
    bank_account_id: Optional[str] = None
    bank_name: str
    beneficiary_name: str
    branch: str
    account_number: str
    ifsc: str


# ────────────────────────────────────────────────────────────
# Line items + amount computations
# ────────────────────────────────────────────────────────────
class BillLineItem(BaseModel):
    candidate_name: str
    designation: Optional[str] = None
    joining_date: str  # ISO yyyy-mm-dd OR dd.mm.yyyy — UI controls format
    annual_ctc: float
    commercial_rate_pct: float = 8.33  # per-row override; default common rate
    line_amount: Optional[float] = None  # = annual_ctc * commercial_rate_pct / 100;
                                          # if omitted, the route auto-computes it.
                                          # Stored explicitly so manual overrides
                                          # survive round-trips.
    hsn_sac: str = "998512"  # placement consultancy default
    application_id: Optional[str] = None  # FK to applications, optional
    placement_id: Optional[str] = None  # FK to placement_ledger, optional


class BillTotals(BaseModel):
    taxable_value: float
    gst_kind: str = "IGST"  # "IGST" or "CGST_SGST"
    igst_pct: float = 18.0
    cgst_pct: float = 9.0
    sgst_pct: float = 9.0
    tax_total: float
    grand_total: float
    amount_in_words: str
    tax_in_words: str


# ────────────────────────────────────────────────────────────
# Persisted bill record
# ────────────────────────────────────────────────────────────
class BillRecord(BaseModel):
    id: str
    bill_number: str  # VHC/26-27/35
    bill_date: str    # iso yyyy-mm-dd
    due_date: Optional[str] = None

    # Sender entity — frozen at creation so changes to the company
    # settings later don't mutate old bills.
    sender_legal_name: str
    sender_address: str
    sender_gstin: str
    sender_pan: Optional[str] = None
    sender_state_code: str  # first 2 chars of GSTIN

    # Client
    client_company_id: Optional[str] = None
    client_legal_name: str
    client_address: str
    client_gstin: str
    client_state_code: str
    client_billing_email: EmailStr

    # Line items + totals
    line_items: List[BillLineItem]
    totals: BillTotals

    # Bank account snapshot (fix.docx 2026-09-15) — the bank the user
    # picked when creating this bill. Frozen so later account edits
    # don't rewrite paid invoices.
    bank_account: Optional[BillBankSnapshot] = None

    # Sender logo URL — snapshotted from sender config at creation.
    sender_logo_url: Optional[str] = None

    # Mail config (snapshotted at send time)
    cc_emails: List[EmailStr] = Field(default_factory=list)
    bcc_emails: List[EmailStr] = Field(default_factory=list)
    mail_subject: Optional[str] = None
    mail_body_html: Optional[str] = None
    mail_body_plain: Optional[str] = None

    # PDF storage
    pdf_r2_key: Optional[str] = None  # the canonical PDF
    pdf_sha256: Optional[str] = None

    # Status / lifecycle
    status: str = "draft"  # draft | sent | viewed | paid | cancelled
    sent_at: Optional[str] = None
    paid_at: Optional[str] = None
    cancelled_at: Optional[str] = None

    # Reminder schedule + audit
    reminders_enabled: bool = True
    reminder_schedule_days: List[int] = Field(default_factory=lambda: [7, 14, 30])
    reminders_sent: List[dict] = Field(default_factory=list)
    mail_events: List[dict] = Field(default_factory=list)

    # Audit
    created_by: str
    created_by_email: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


# ────────────────────────────────────────────────────────────
# Request bodies
# ────────────────────────────────────────────────────────────
class BillCreate(BaseModel):
    bill_date: Optional[str] = None  # default = today
    due_date: Optional[str] = None
    client_company_id: str
    line_items: List[BillLineItem]
    gst_kind: Optional[str] = None  # auto-detected from state codes if None
    sender_variant: Optional[str] = "VENTURE HRD CENTER"  # or "VENTURES HRD PVT LTD"
    bank_account_id: Optional[str] = None  # if None → default account


class BillUpdate(BaseModel):
    bill_date: Optional[str] = None
    due_date: Optional[str] = None
    line_items: Optional[List[BillLineItem]] = None
    gst_kind: Optional[str] = None
    sender_variant: Optional[str] = None
    bank_account_id: Optional[str] = None
    cc_emails: Optional[List[EmailStr]] = None
    bcc_emails: Optional[List[EmailStr]] = None
    mail_subject: Optional[str] = None
    mail_body_html: Optional[str] = None
    mail_body_plain: Optional[str] = None


class BillSend(BaseModel):
    to_email: Optional[EmailStr] = None  # fix.docx 2026-09-15 — override
                                           # `client_billing_email` (users
                                           # asked to type a per-send address)
    extra_cc: List[EmailStr] = Field(default_factory=list)
    mail_subject: Optional[str] = None
    mail_body_html: Optional[str] = None
    mail_body_plain: Optional[str] = None
    test_mode: bool = False  # if true, only sends to the requester


class ConsolidatedItem(BaseModel):
    """One candidate on a consolidated invoice. Either a pipeline joining
    (`application_id`) or a row from the branch tracker (`placement_id`)."""
    application_id: Optional[str] = None
    placement_id: Optional[str] = None
    designation: Optional[str] = None
    annual_ctc: float = 0
    commercial_rate_pct: float = 0
    line_amount: Optional[float] = None


class ConsolidatedInvoiceRequest(BaseModel):
    """Bill several candidates of the SAME client on one invoice, so the
    payment can be received — and marked — in one go."""
    items: List[ConsolidatedItem] = Field(..., min_length=1)
    client_company_id: Optional[str] = None
    sender_variant: Optional[str] = None
    gst_kind: Optional[str] = None
    bank_account_id: Optional[str] = None
    bill_date: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
