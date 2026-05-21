"""Tally XML envelope builder — Phase 55.8 (Feb 2026).

Translates a VHC bill record into a Tally Prime / Tally.ERP 9 compatible
"Sales Voucher" XML payload. Push via HTTP POST to the Tally XML
gateway listening on port 9000 (Gateway of Tally → F11 → AdvancedConfig
→ Enable ODBC/HTTP server).

The envelope follows the legacy `TDL XML` schema which is identical
between Tally Prime and Tally.ERP 9 — one builder serves both editions.

Public:
    build_sales_voucher_xml(bill, company_name) -> str
    build_ledger_create_xml(ledger_name, group="Sundry Debtors", gstin="") -> str
"""
from __future__ import annotations

from typing import Optional
from xml.sax.saxutils import escape

# ── Helpers ──────────────────────────────────────────────────────────
def _x(v) -> str:
    """XML-escape (None → empty)."""
    return escape("" if v is None else str(v))


def _amt(v) -> str:
    """Tally amount string. Negative means debit, positive means credit
    in Tally's convention for ledger entries (we follow the standard
    sales voucher convention: party DR, sales+tax CR)."""
    return f"{float(v or 0):.2f}"


def _ddmmyyyy(iso_date: str) -> str:
    """Tally wants dates as YYYYMMDD with no separators."""
    if not iso_date:
        return ""
    s = iso_date.replace("-", "").replace(".", "").replace("/", "")
    return s[:8]


# ── Ledger names — central place so we can override per-environment ──
DEFAULT_SALES_LEDGER = "Sales - Placement Consultancy"
DEFAULT_IGST_LEDGER = "Output IGST @ 18%"
DEFAULT_CGST_LEDGER = "Output CGST @ 9%"
DEFAULT_SGST_LEDGER = "Output SGST @ 9%"


# ── Sales Voucher ────────────────────────────────────────────────────
def build_sales_voucher_xml(
    bill: dict,
    company_name: str,
    *,
    sales_ledger: str = DEFAULT_SALES_LEDGER,
    igst_ledger: str = DEFAULT_IGST_LEDGER,
    cgst_ledger: str = DEFAULT_CGST_LEDGER,
    sgst_ledger: str = DEFAULT_SGST_LEDGER,
) -> str:
    """Build a Tally Sales Voucher import XML.

    `bill` is the VHC bill dict (matches `models.bill.BillRecord.model_dump()`).
    `company_name` MUST exactly match the company name in Tally — Tally
    uses this to route the voucher into the right company file.
    """
    totals = bill.get("totals") or {}
    taxable = float(totals.get("taxable_value") or 0)
    tax_total = float(totals.get("tax_total") or 0)
    grand = float(totals.get("grand_total") or 0)
    gst_kind = totals.get("gst_kind") or "IGST"

    party = bill.get("client_legal_name") or ""
    voucher_no = bill.get("bill_number") or ""
    voucher_date = _ddmmyyyy(bill.get("bill_date") or "")
    narration = (
        "Placement consultancy charges. "
        "Candidates: "
        + "; ".join(
            f"{li.get('candidate_name','')} (DOJ {li.get('joining_date','')})"
            for li in bill.get("line_items") or []
        )
    )

    # Build the tax ledger entries
    tax_entries = []
    if gst_kind == "IGST":
        tax_entries.append((igst_ledger, tax_total))
    else:
        # 9% + 9% split — recompute from taxable rather than tax_total/2 so
        # we never push a half-paisa mismatch into Tally's books.
        cgst = round(taxable * 0.09 + 1e-9, 2)
        sgst = round(taxable * 0.09 + 1e-9, 2)
        tax_entries.append((cgst_ledger, cgst))
        tax_entries.append((sgst_ledger, sgst))

    # Ledger entries XML
    ledger_entries_xml = []

    # 1. Party debit (the customer owes us the grand_total)
    ledger_entries_xml.append(f"""
      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{_x(party)}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <AMOUNT>-{_amt(grand)}</AMOUNT>
      </ALLLEDGERENTRIES.LIST>""")

    # 2. Sales credit (taxable value)
    ledger_entries_xml.append(f"""
      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{_x(sales_ledger)}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{_amt(taxable)}</AMOUNT>
      </ALLLEDGERENTRIES.LIST>""")

    # 3. Tax credits (IGST OR CGST+SGST)
    for led, amt in tax_entries:
        ledger_entries_xml.append(f"""
      <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{_x(led)}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{_amt(amt)}</AMOUNT>
      </ALLLEDGERENTRIES.LIST>""")

    # Final envelope. SVCURRENTCOMPANY tells Tally which loaded company
    # to push into. REMOTEID is a unique GUID-ish key so re-imports are
    # idempotent — Tally treats a 2nd push of the same REMOTEID as an
    # update, not a duplicate.
    remote_id = f"VHC-{bill.get('id','') or voucher_no}"

    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVCURRENTCOMPANY>{_x(company_name)}</SVCURRENTCOMPANY>
      </STATICVARIABLES>
      <IMPORTDATA>
        <REQUESTDESC>
          <REPORTNAME>Vouchers</REPORTNAME>
        </REQUESTDESC>
        <REQUESTDATA>
          <TALLYMESSAGE xmlns:UDF="TallyUDF">
            <VOUCHER VCHTYPE="Sales" ACTION="Create" OBJVIEW="Invoice Voucher View" REMOTEID="{_x(remote_id)}">
              <DATE>{_x(voucher_date)}</DATE>
              <EFFECTIVEDATE>{_x(voucher_date)}</EFFECTIVEDATE>
              <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
              <VOUCHERNUMBER>{_x(voucher_no)}</VOUCHERNUMBER>
              <REFERENCE>{_x(voucher_no)}</REFERENCE>
              <PARTYLEDGERNAME>{_x(party)}</PARTYLEDGERNAME>
              <PARTYNAME>{_x(party)}</PARTYNAME>
              <NARRATION>{_x(narration)}</NARRATION>
              <ISINVOICE>Yes</ISINVOICE>
              <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
              {''.join(ledger_entries_xml)}
            </VOUCHER>
          </TALLYMESSAGE>
        </REQUESTDATA>
      </IMPORTDATA>
    </DESC>
  </BODY>
</ENVELOPE>"""


# ── Ledger create (run once per new client) ──────────────────────────
def build_ledger_create_xml(
    company_name: str,
    ledger_name: str,
    *,
    parent_group: str = "Sundry Debtors",
    gstin: str = "",
    state: str = "",
    is_party: bool = True,
) -> str:
    """Generate Tally XML to create a customer ledger.

    Use this once for each new client before pushing their first
    invoice. After that, Tally will route subsequent vouchers to the
    same ledger by name match.
    """
    gst_block = ""
    if gstin and is_party:
        gst_block = f"""
        <PARTYGSTIN>{_x(gstin)}</PARTYGSTIN>
        <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
        <ISGSTREGNUMBERVALID>Yes</ISGSTREGNUMBERVALID>"""

    state_block = f"<LEDSTATENAME>{_x(state)}</LEDSTATENAME>" if state else ""

    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVCURRENTCOMPANY>{_x(company_name)}</SVCURRENTCOMPANY>
      </STATICVARIABLES>
      <IMPORTDATA>
        <REQUESTDESC>
          <REPORTNAME>All Masters</REPORTNAME>
        </REQUESTDESC>
        <REQUESTDATA>
          <TALLYMESSAGE xmlns:UDF="TallyUDF">
            <LEDGER NAME="{_x(ledger_name)}" ACTION="Create">
              <NAME>{_x(ledger_name)}</NAME>
              <PARENT>{_x(parent_group)}</PARENT>
              <ISBILLWISEON>Yes</ISBILLWISEON>
              {state_block}
              {gst_block}
            </LEDGER>
          </TALLYMESSAGE>
        </REQUESTDATA>
      </IMPORTDATA>
    </DESC>
  </BODY>
</ENVELOPE>"""


# ── Response parsing ─────────────────────────────────────────────────
def parse_tally_response(xml_text: str) -> dict:
    """Parse Tally's XML response into {success, created, ignored, errors}.

    A successful import response looks like:
        <RESPONSE>
          <CREATED>1</CREATED><ALTERED>0</ALTERED>
          <DELETED>0</DELETED><LASTVCHID>1234</LASTVCHID>
          <LINEERROR/>
        </RESPONSE>

    On error, <LINEERROR> contains a human-readable message.
    """
    import re

    def grab(tag: str) -> str:
        m = re.search(fr"<{tag}>(.*?)</{tag}>", xml_text or "", re.DOTALL | re.IGNORECASE)
        return (m.group(1).strip() if m else "")

    created = grab("CREATED")
    altered = grab("ALTERED")
    ignored = grab("IGNORED")
    line_err = grab("LINEERROR")
    last_id = grab("LASTVCHID")
    # If Tally rejects outright it returns <RESPONSE>... with a top-level
    # error message wrapped in <LINEERROR> or a non-zero <EXCEPTIONS>
    success = (
        not line_err and
        (created or altered) and
        int(created or "0") + int(altered or "0") > 0
    )
    return {
        "success": bool(success),
        "created": int(created or "0"),
        "altered": int(altered or "0"),
        "ignored": int(ignored or "0"),
        "last_vch_id": last_id or None,
        "error": line_err or (None if success else "Unknown Tally rejection"),
        "raw": (xml_text or "")[:2000],
    }
