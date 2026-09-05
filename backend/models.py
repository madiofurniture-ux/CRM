"""Pydantic models for MADIO CRM."""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Any
from datetime import datetime, timezone
import uuid

import lifecycle as lc


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


GST_DEFAULT = 18.0


# ------- Users -------
class UserBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    username: str
    name: str
    role: str = "user"  # "admin" or "user" — the absolute superuser bypass; never governed by role_id
    icon: str = "U"  # short label or emoji
    color: str = "#C85A32"
    pages: Optional[List[str]] = None  # None == all pages (admin) — legacy grant, still honored when role_id is unset
    team_id: Optional[str] = ""
    role_id: Optional[str] = ""   # "" = legacy role/pages behavior (every pre-P2 account)
    phone: Optional[str] = ""
    email: Optional[str] = ""
    active: bool = True


class UserCreate(UserBase):
    pin: str  # 4-digit PIN


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    pages: Optional[List[str]] = None
    pin: Optional[str] = None
    team_id: Optional[str] = None
    role_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    active: Optional[bool] = None


class UserPublic(UserBase):
    id: str
    created_at: str


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    pin: str = Field(max_length=64)


class LoginResponse(BaseModel):
    token: str
    user: UserPublic


# ------- Visitors -------
class VisitorBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    name: str
    location: Optional[str] = ""
    reference: Optional[str] = ""
    phone: Optional[str] = ""
    requirement: Optional[str] = ""
    attend_person: Optional[str] = ""
    site_visit: Optional[str] = ""
    remarks: Optional[str] = ""
    status: Optional[str] = "New"  # New / Quoted / Negotiation / Delivered / Lost
    stage: Optional[str] = "New"
    ticket_value: Optional[float] = 0


class VisitorCreate(VisitorBase):
    pass


class Visitor(VisitorBase):
    id: str
    created_at: str


# ------- Leads -------
class LeadBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    name: str
    phone: Optional[str] = ""
    source: Optional[str] = ""    # channel the lead came through, e.g. "Referral" / "Instagram"
    reference: Optional[str] = ""  # the specific person/campaign/handle, e.g. "Ramesh Kumar" / "@madiointeriors"
    stage: str = "New"  # New, Contacted, Qualified, Quoted, Won, Lost
    follow_up_date: Optional[str] = ""
    remarks: Optional[str] = ""
    assigned_to: Optional[str] = ""
    attended_by: Optional[str] = ""       # who met the lead — linked to Team/Users by name
    confidence_level: Optional[float] = None  # 0-100 — sales rep's read on close probability
    team_id: Optional[str] = ""           # direct team link for reporting; independent of assigned_to's own team_id
    visitor_id: Optional[str] = ""        # lineage when converted from a Visitor
    value: Optional[float] = 0
    # Dated, multi-entry audit trail: [{at, by, by_id, text, confidence_level, kind}].
    # `remarks` above stays a plain string (unmigrated) — old screens still read it.
    log: List[dict] = Field(default_factory=list)


class LeadCreate(LeadBase):
    # Redeclared as required (no default): Pydantic v2 doesn't run
    # field_validators against a value that was never supplied and fell
    # back to LeadBase's "" default, so a payload that omits the key
    # entirely would otherwise sail through. Required + the validators
    # below together close both gaps (missing key AND empty string).
    phone: str
    source: str
    reference: str

    @field_validator("phone")
    @classmethod
    def _phone_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Phone number is required")
        return v

    @field_validator("source")
    @classmethod
    def _source_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Source is required")
        return v

    @field_validator("reference")
    @classmethod
    def _reference_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Reference is required")
        return v

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v):
        return lc.validate_person_name(v)


class Lead(LeadBase):
    id: str
    created_at: str


# ------- Architects / Contacts -------
class ArchitectBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    firm: Optional[str] = ""
    type: Optional[str] = "Architect"  # Architect / Builder / Designer / Vendor
    location: Optional[str] = ""
    phone: Optional[str] = ""
    last_contact: Optional[str] = ""
    visited: bool = False
    assigned_to: Optional[str] = ""
    remarks: Optional[str] = ""


class ArchitectCreate(ArchitectBase):
    pass


class Architect(ArchitectBase):
    id: str
    created_at: str


# ------- Quotes -------
class QuoteBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    quote_no: str
    date: str
    customer: str
    reference: Optional[str] = ""
    phone: Optional[str] = ""
    division: str = "Furniture"  # Furniture / MAP / D&W
    by_user: Optional[str] = ""
    stage: str = "Quoted"
    lead_id: Optional[str] = ""           # lineage back to the originating lead
    requirement_id: Optional[str] = ""    # set when generated from a Requirement
    config_id: Optional[str] = ""         # set when generated from a Configurator run
    value: float = 0
    cash: Optional[float] = 0
    bank: Optional[float] = 0
    mode: Optional[str] = "Walk-in"
    remarks: Optional[str] = ""
    line_items: Optional[List[dict]] = []
    subtotal: Optional[float] = 0
    tax_pct: Optional[float] = GST_DEFAULT
    tax_total: Optional[float] = 0
    grand_total: Optional[float] = 0
    # ---- workspace: line-item builder, discount approval, versions ----
    # `discount` is an absolute rupee amount off the subtotal, not a percentage
    # (LineItem.discount_pct is the per-line percentage and is unrelated).
    version: int = 1
    discount: Optional[float] = 0
    # "" (none needed) | "pending" | "approved" | "rejected"
    approval: Optional[str] = ""
    approved_by: Optional[str] = ""
    approved_at: Optional[str] = ""
    # Dated, multi-entry follow-up ledger: [{at, by, by_id, text, confidence_level, kind}]
    log: List[dict] = Field(default_factory=list)
    confidence_level: Optional[float] = None   # 0-100 — latest read on close probability
    next_follow_up: Optional[str] = ""         # denormalized from the latest log entry, for dashboard bucketing


class QuoteCreate(QuoteBase):
    pass


class Quote(QuoteBase):
    id: str
    created_at: str


# ------- Sales (a.k.a. Sales Orders — same collection, "balance" is the
# order's balance_due) -------
class SaleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sale_no: str
    date: str
    customer: str
    division: str = "Furniture"
    quote_ref: Optional[str] = ""
    quote_id: Optional[str] = ""          # links back to the source quote, for idempotent auto-conversion
    lead_id: Optional[str] = ""           # lineage back to the originating lead
    by_user: Optional[str] = ""
    value: float = 0
    paid: float = 0
    balance: float = 0                    # balance_due
    status: str = "PENDING"               # PENDING / PARTIAL / PAID
    stage: str = "Delivered"
    remarks: Optional[str] = ""
    line_items: Optional[List[dict]] = []  # snapshot of quote lines at conversion time


class SaleCreate(SaleBase):
    pass


class Sale(SaleBase):
    id: str
    created_at: str


# ------- Inventory -------
class InventoryBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str
    name: str
    category: Optional[str] = ""
    vendor: Optional[str] = ""
    model_no: Optional[str] = ""
    qty: int = 1
    cost: float = 0
    mrp: float = 0
    margin: float = 0
    status: str = "In Stock"  # In Stock / Display / Sold / Missing / Reserved
    location: Optional[str] = "Warehouse"
    image_url: Optional[str] = ""
    vendor_code: Optional[str] = ""


class InventoryCreate(InventoryBase):
    # Required (no default) so a payload that omits the key entirely can't
    # skip the validator below the way InventoryBase's "" default would let
    # it — new items only, the ~2000 historical rows are not backfilled.
    vendor_code: str

    @field_validator("vendor_code")
    @classmethod
    def _vendor_code_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Vendor code is required")
        return v

    @field_validator("location")
    @classmethod
    def _canonical_floor(cls, v):
        return lc.normalize_location(v)


class InventoryItem(InventoryBase):
    id: str
    created_at: str


# ------- Tasks -------
class TaskBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    priority: str = "Medium"  # Low / Medium / High
    due_date: Optional[str] = ""
    assigned_to: Optional[str] = ""
    category: Optional[str] = "General"
    ref: Optional[str] = ""
    ref_type: Optional[str] = ""  # "" / lead / quote / sale / project — what `ref` points at
    notes: Optional[str] = ""
    done: bool = False


class TaskCreate(TaskBase):
    pass


class Task(TaskBase):
    id: str
    created_at: str
    created_by: Optional[str] = ""


# ------- Line item (shared by Quotes / Invoices) -------
class LineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: Optional[str] = ""
    description: str = ""
    hsn: Optional[str] = ""
    qty: float = 1
    rate: float = 0
    discount_pct: Optional[float] = 0
    tax_pct: Optional[float] = GST_DEFAULT  # GST


# ------- Invoice -------
class InvoiceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    invoice_no: str
    date: str
    customer: str
    billing_address: Optional[str] = ""
    phone: Optional[str] = ""
    gstin: Optional[str] = ""
    place_of_supply: Optional[str] = "Telangana"
    is_igst: bool = False  # interstate → IGST, else CGST+SGST
    line_items: List[LineItem] = []
    subtotal: float = 0
    discount_total: float = 0
    cgst: float = 0
    sgst: float = 0
    igst: float = 0
    total: float = 0
    paid: float = 0
    balance: float = 0
    by_user: Optional[str] = ""
    status: str = "Draft"  # Draft / Sent / Paid / Cancelled
    notes: Optional[str] = ""


class InvoiceCreate(InvoiceBase):
    pass


class Invoice(InvoiceBase):
    id: str
    created_at: str


# ------- Meet Planner -------
class MeetBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    date: str  # ISO date
    start_time: str = "10:00"
    end_time: str = "11:00"
    location: Optional[str] = ""
    attendees: List[str] = []
    with_person: Optional[str] = ""
    ref_type: Optional[str] = ""  # Lead / Architect / Customer / Internal
    ref_name: Optional[str] = ""
    agenda: Optional[str] = ""
    status: str = "Scheduled"  # Scheduled / Done / Cancelled
    created_by: Optional[str] = ""


class MeetCreate(MeetBase):
    pass


class Meet(MeetBase):
    id: str
    created_at: str


# ------- Petty Cash -------
class PettyCashBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    kind: str = "Out"  # In / Out
    category: str = "Misc"
    party: Optional[str] = ""
    description: str = ""
    amount: float = 0
    mode: str = "Cash"  # Cash / Bank / UPI
    by_user: Optional[str] = ""
    ref: Optional[str] = ""


class PettyCashCreate(PettyCashBase):
    pass


class PettyCash(PettyCashBase):
    id: str
    created_at: str


# ------- Cashbooks (multiple named cash boxes, each with a running
# balance — distinct from the single flat PettyCash ledger above, which
# stays untouched) -------
class CashbookBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    book_name: str
    description: Optional[str] = ""
    assigned_users: List[str] = Field(default_factory=list)  # user ids with access
    initial_balance: float = 0
    current_balance: float = 0
    status: str = "ACTIVE"  # ACTIVE / ARCHIVED


class CashbookCreate(CashbookBase):
    @field_validator("book_name")
    @classmethod
    def _name_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Book name is required")
        return v


class Cashbook(CashbookBase):
    id: str
    created_at: str


class CashbookEntryBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cashbook_id: str
    type: str                            # CASH_IN / CASH_OUT
    amount: float = 0
    category: Optional[str] = ""         # Hardware / Fuel / Refreshments / Transport / Advances / ...
    payment_mode: str = "CASH"            # CASH / UPI / ONLINE
    remark: Optional[str] = ""
    receipt_url: Optional[str] = ""
    entry_person: Optional[str] = ""


class CashbookEntryCreate(CashbookEntryBase):
    @field_validator("type")
    @classmethod
    def _valid_type(cls, v):
        if v not in ("CASH_IN", "CASH_OUT"):
            raise ValueError("type must be CASH_IN or CASH_OUT")
        return v

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v):
        if v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


class CashbookEntry(CashbookEntryBase):
    id: str
    created_at: str


# ------- Agent tasks (a generic, durable background-job queue — "agent"
# names the shape borrowed from a reference CRM's task worker, not an AI
# capability; no LLM is involved anywhere here) -------
class AgentTaskBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str                          # free-form, e.g. "followup_reminder" — not an enum
    subject_type: Optional[str] = ""   # "lead" / "quote" / "sale" / ""
    subject_id: Optional[str] = ""
    reason: Optional[str] = ""
    payload: dict = Field(default_factory=dict)
    priority: int = 0
    due_at: Optional[str] = ""         # ISO string, matches now_iso()/today_iso() convention
    attempts: int = 0
    max_attempts: int = 3
    leased_until: Optional[str] = ""
    leased_by: Optional[str] = ""      # observability only, never load-bearing for correctness
    started_at: Optional[str] = ""
    finished_at: Optional[str] = ""
    outcome: Optional[str] = ""        # "" while open; "done" / "failed" / "abandoned" once finished
    # Reuses the same {at, by, text, kind} ledger shape as Lead.log/Quote.log
    # for attempt/error history — one convention, not a second one invented here.
    log: List[dict] = Field(default_factory=list)


class AgentTaskCreate(AgentTaskBase):
    pass


class AgentTask(AgentTaskBase):
    id: str
    created_at: str


# ------- Attendance -------
class AttendanceCheckIn(BaseModel):
    lat: float
    lng: float
    note: Optional[str] = ""
    photo_url: Optional[str] = ""


class AttendanceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    username: str
    name: str
    date: str  # YYYY-MM-DD
    check_in_at: Optional[str] = None
    check_in_lat: Optional[float] = None
    check_in_lng: Optional[float] = None
    check_in_within: Optional[bool] = None
    check_in_distance: Optional[float] = None
    check_in_photo: Optional[str] = None
    check_out_at: Optional[str] = None
    check_out_lat: Optional[float] = None
    check_out_lng: Optional[float] = None
    check_out_within: Optional[bool] = None
    check_out_distance: Optional[float] = None
    check_out_photo: Optional[str] = None
    duration_min: Optional[int] = None
    note: Optional[str] = ""
    created_at: str



# ------- Settings -------
class OfficeSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = "MADIO Head Office"
    lat: float = 17.4065
    lng: float = 78.4772
    radius_m: int = 200
    address: Optional[str] = "Hyderabad, Telangana"
    gstin: Optional[str] = ""
    invoice_prefix: Optional[str] = "MAD"


# ------- Projects Execution -------
class ProjectBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project_no: str
    customer: str
    phone: Optional[str] = ""
    division: str = "Furniture"  # Furniture / MAP / D&W
    value: float = 0
    paid: float = 0
    stage: str = "Survey"  # Survey / Quoted / Execution / Review / Closure
    site_address: Optional[str] = ""
    assigned_engineer: Optional[str] = ""
    start_date: Optional[str] = ""
    target_date: Optional[str] = ""
    remarks: Optional[str] = ""
    quote_ref: Optional[str] = ""
    sale_id: Optional[str] = ""           # links back to the sales order it was generated from
    lead_id: Optional[str] = ""           # lineage back to the originating lead
    requirement_id: Optional[str] = ""    # set when started from a Requirement, before any quote exists
    milestones: List[dict] = Field(default_factory=list)  # [{name, status, completed_at}]
    log: List[dict] = Field(default_factory=list)  # [{at, by, by_id, text, confidence_level, kind}]


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    customer: Optional[str] = None
    phone: Optional[str] = None
    division: Optional[str] = None
    value: Optional[float] = None
    paid: Optional[float] = None
    stage: Optional[str] = None
    site_address: Optional[str] = None
    assigned_engineer: Optional[str] = None
    start_date: Optional[str] = None
    target_date: Optional[str] = None
    remarks: Optional[str] = None
    quote_ref: Optional[str] = None


class ProjectStageUpdate(BaseModel):
    stage: str


class Project(ProjectBase):
    id: str
    created_at: str


class QuoteLineBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    quote_id: str
    version: int = 1
    description: str = ""
    w: float = 0
    h: float = 0
    qty: float = 1
    rate: float = 0
    sft: Optional[float] = 0
    amount: Optional[float] = 0

class DWOpeningBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    survey_id: str
    room: Optional[str] = ""
    type: str = "Window"                # see lifecycle.DWS_TYPES
    w: float = 0                        # inches
    h: float = 0                        # inches
    qty: float = 1
    area: Optional[float] = 0           # sqft, computed
    frame: str = "uPVC"
    glass: str = "Single"
    mesh: bool = False
    handle_position: Optional[str] = ""  # "" (N/A) | "RHS" | "LHS"
    notes: Optional[str] = ""
    image_url: Optional[str] = ""

    @field_validator("handle_position")
    @classmethod
    def _valid_handle_position(cls, v):
        v = str(v or "")
        if v not in ("", "RHS", "LHS"):
            raise ValueError("handle_position must be RHS, LHS, or blank (N/A)")
        return v


# ── Recovered parity models (D&W surveys, payments, stock ledger, quote lines) ──
class DWSurveyBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    survey_id: Optional[str] = ""       # DW-YYMM-NNN, assigned server-side
    date: str = ""
    customer: str = ""
    phone: Optional[str] = ""
    site_address: Optional[str] = ""
    by_user: Optional[str] = ""
    status: str = "Draft"
    remarks: Optional[str] = ""
    # Site photos from the visit, stored as shrunken data URLs so a survey
    # travels as ONE document — engineers are frequently offline on site.
    photos: List[str] = Field(default_factory=list)

class DWSurveyCreate(DWSurveyBase):
    pass

class DWSurvey(DWSurveyBase):
    id: str
    created_at: str

class DWOpening(DWOpeningBase):
    id: str
    created_at: str


# ------- Stock ledger (inventory movements) -------

class PaymentBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    division: str = "Furniture"
    direction: str = "In"               # In / Out / Refund
    amount: float = 0
    mode: str = "Cash"                  # Cash / Bank / UPI / Cheque
    kind: Optional[str] = "Advance"     # Advance / Part / Final / Refund
    received_by: Optional[str] = ""
    against_sale_id: Optional[str] = ""
    against_invoice_id: Optional[str] = ""
    against_quote_no: Optional[str] = ""
    phone: Optional[str] = ""
    remarks: Optional[str] = ""

class PaymentCreate(PaymentBase):
    pass

class Payment(PaymentBase):
    id: str
    created_at: str


# ------- Activity feed -------

class StockMovementBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    movement_no: Optional[str] = ""      # MV-YYMM-NNN, assigned server-side
    date: str = ""
    type: str = "Receipt"                # see lifecycle.STOCK_MOVE_TYPES
    product_id: str = ""                 # inventory sku
    qty: float = 0
    unit: str = "pc"
    warehouse: Optional[str] = "Main"
    to_warehouse: Optional[str] = ""     # for transfers
    source_doc: Optional[str] = ""       # PO / sale / project reference
    reason: Optional[str] = ""
    by_user: Optional[str] = ""

class StockMovementCreate(StockMovementBase):
    pass

class StockMovement(StockMovementBase):
    id: str
    created_at: str


# ------- Inventory -------

class QuoteLine(QuoteLineBase):
    id: str
    created_at: str


# ------- Payments (against sales / quotes) -------


class DWOpeningCreate(DWOpeningBase):
    pass

class QuoteLineCreate(QuoteLineBase):
    pass


# ------- Commission rules (architect / sales-rep payout rates) -------
class CommissionRuleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    payee_type: str = "architect"       # architect / user
    payee: Optional[str] = ""           # "" = applies to every payee of that type
    rate_pct: float = 0
    flat_amount: float = 0
    division: Optional[str] = ""        # "" = all divisions
    active: bool = True
    remarks: Optional[str] = ""


class CommissionRuleCreate(CommissionRuleBase):
    pass


class CommissionRule(CommissionRuleBase):
    id: str
    created_at: str


# ------- Commission payouts (approved, persisted snapshot of a computed
# commission — the live /analytics/commissions computation is re-run every
# request, but once a manager approves a row it's frozen here so a later
# rule change or extra payment doesn't silently move an already-approved
# number) -------
class CommissionPayoutBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    period: str                         # "YYYY-MM"
    payee: str
    payee_type: str = "user"            # user / architect — mirrors CommissionRule
    division: Optional[str] = ""
    base_amount: float = 0              # sum of cleared (received) payments the payout is computed from
    rate_pct: float = 0
    flat_amount: float = 0
    commission_amount: float = 0
    status: str = "Approved"            # Approved / Paid — a row only exists once approved
    approved_by: Optional[str] = ""
    remarks: Optional[str] = ""


class CommissionPayoutCreate(CommissionPayoutBase):
    pass


class CommissionPayout(CommissionPayoutBase):
    id: str
    created_at: str


# ------- Requirements (structured need captured before a quote) -------
class RequirementBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lead_id: str
    project_id: Optional[str] = ""
    customer: str
    phone: Optional[str] = ""
    division: str = "Furniture"
    title: str = ""
    items: List[dict] = []   # [{space, item, qty, w, h, notes, budget}]
    budget: float = 0
    priority: str = "Medium"  # Low / Medium / High
    status: str = "Open"      # Open / Configured / Quoted
    site_address: Optional[str] = ""
    by_user: Optional[str] = ""
    notes: Optional[str] = ""


class RequirementCreate(RequirementBase):
    pass


class Requirement(RequirementBase):
    id: str
    created_at: str


# ------- Product Configurations (the "Configurator") -------
class ProductConfigBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requirement_id: str
    quote_id: Optional[str] = ""
    name: str = ""
    division: str = "Furniture"
    inputs: dict = {}              # raw configurator selections
    line_items: List[dict] = []    # computed via lc.calc_line, same shape as quote lines
    subtotal: float = 0
    discount: float = 0
    tax_pct: float = GST_DEFAULT
    tax_total: float = 0
    grand_total: float = 0
    version: int = 1
    status: str = "Draft"          # Draft / Quoted
    by_user: Optional[str] = ""


class ProductConfigCreate(ProductConfigBase):
    pass


class ProductConfig(ProductConfigBase):
    id: str
    created_at: str


# ------- Customers (post-sale lifecycle record) -------
class CustomerBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    phone: str
    email: Optional[str] = ""
    address: Optional[str] = ""
    gstin: Optional[str] = ""
    division: str = "Furniture"
    stage: str = "Prospect"        # Prospect / Active / Dormant — see tenancy.DEFAULT_WORKFLOWS["customer"]
    lead_id: Optional[str] = ""
    first_sale_id: Optional[str] = ""
    customer_since: Optional[str] = ""
    lifetime_value: float = 0
    balance: float = 0
    remarks: Optional[str] = ""
    confidence_level: Optional[float] = None  # 0-100
    team_id: Optional[str] = ""           # direct team link for reporting
    gender: Optional[str] = ""
    maps_url: Optional[str] = ""     # Google Maps location link
    lat: Optional[float] = None
    lng: Optional[float] = None
    alt_contact_name: Optional[str] = ""
    alt_phone: Optional[str] = ""


class CustomerCreate(CustomerBase):
    @field_validator("name")
    @classmethod
    def _valid_name(cls, v):
        return lc.validate_person_name(v)

    @field_validator("phone")
    @classmethod
    def _phone_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Phone number is required")
        return v


class Customer(CustomerBase):
    id: str
    created_at: str


# ------- Teams -------
class TeamBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    description: Optional[str] = ""
    active: bool = True


class TeamCreate(TeamBase):
    pass


class Team(TeamBase):
    id: str
    created_at: str


# ------- Roles & permissions (P2) -------
# Deliberately flat: module x {view,create,edit,delete,approve,export} x a
# single scope (own/team/all) — no field-level rules, no permission
# hierarchies. `role == "admin"` on the user itself remains the absolute,
# unconfigurable bypass (see permissions.py) so a role can never be
# misconfigured into locking the tenant out of itself.
class ModulePermission(BaseModel):
    model_config = ConfigDict(extra="ignore")
    module: str
    view: bool = False
    create: bool = False
    edit: bool = False
    delete: bool = False
    approve: bool = False
    export: bool = False
    scope: str = "own"  # "own" | "team" | "all"

    @field_validator("scope")
    @classmethod
    def _valid_scope(cls, v):
        if v not in ("own", "team", "all"):
            raise ValueError("scope must be own, team, or all")
        return v


class RoleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    permissions: List[ModulePermission] = Field(default_factory=list)
    active: bool = True


class RoleCreate(RoleBase):
    pass


class Role(RoleBase):
    id: str
    created_at: str


# ------- Audit log (P2) -------
class AuditLogBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: str   # role_created | role_changed | permission_changed |
                  # user_role_assigned | user_team_assigned | user_activated | user_deactivated
    by_user: str
    by_id: str
    detail: str = ""


class AuditLog(AuditLogBase):
    id: str
    created_at: str
