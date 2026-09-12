"""Pydantic models for MADIO CRM."""
from pydantic import AliasChoices, BaseModel, Field, ConfigDict, field_validator
from typing import List, Literal, Optional, Any
from datetime import datetime, timezone
import uuid

import lifecycle as lc


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# The GST actually charged on a received bank transfer is a property of that
# payment (it mirrors the tax invoice raised against it), so it keeps a real
# default rather than 0.
GST_DEFAULT = 18.0

# Documents (quotes, invoices, PO lines, configurator output) default to 0%
# instead: a pre-filled 18% silently taxed drafts that were never meant to
# carry GST, and it is far safer for a rate to be visibly missing than
# invisibly wrong. The UI offers these slabs as one-click choices.
GST_DOC_DEFAULT = 0.0
GST_SLABS = [0.0, 5.0, 12.0, 18.0, 28.0]


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
class VisitorRemark(BaseModel):
    """One dated remark entry. Visitors carry a list of these instead of one
    flat string, so a follow-up note never overwrites the one before it."""
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = None
    text: str
    at: Optional[str] = None  # ISO timestamp, stamped server-side if missing


class VisitorBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    name: str
    # "Male" / "Female" / "Company" — "" means legacy/unset, kept for records
    # created before this field existed.
    customer_type: Optional[str] = ""
    location: Optional[str] = ""
    reference: Optional[str] = ""       # display name, kept for legacy rows / CSV export
    reference_id: Optional[str] = ""    # Architect.id when linked via the picker
    phone: Optional[str] = ""
    requirement: Optional[str] = ""
    attend_person: Optional[str] = ""     # display name, kept for legacy rows / CSV export
    attend_person_id: Optional[str] = ""  # Staff (users) id when linked via the picker
    site_visit: Optional[str] = ""
    # Accepts either the new list-of-entries shape or a legacy plain string;
    # normalize_visitor() upgrades a legacy string to a single entry on write.
    remarks: Optional[Any] = Field(default_factory=list)
    status: Optional[str] = "New"  # New / Quoted / Negotiation / Delivered / Lost
    stage: Optional[str] = "New"
    ticket_value: Optional[float] = 0


class VisitorCreate(VisitorBase):
    pass


class Visitor(VisitorBase):
    id: str
    created_at: str


# ------- Leads -------
class RemarkEntry(BaseModel):
    """One timestamped remark on a Lead. Leads carry a list of these so a
    follow-up note never overwrites the one before it. Distinct from
    VisitorRemark above: that one predates this and uses {id, text, at}; this
    also records who wrote it, the same way `log` entries carry `by`."""
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = None
    text: str
    created_at: Optional[str] = None   # ISO timestamp, stamped server-side if missing
    author_name: Optional[str] = ""    # acting user's name, stamped server-side if missing


class LeadBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    name: str
    phone: Optional[str] = ""
    source: Optional[str] = ""    # channel the lead came through, e.g. "Referral" / "Instagram"
    architect_id: Optional[str] = ""    # Architect.id, set when source == "Architect"
    architect_name: Optional[str] = ""  # display name, prepopulated from the picker
    reference: Optional[str] = ""  # the specific person/campaign/handle, e.g. "Ramesh Kumar" / "@madiointeriors"
    stage: str = "New"  # New, Contacted, Qualified, Quoted, Won, Lost
    follow_up_date: Optional[str] = ""
    # Kept a plain string on purpose: CSV export and the leads list filter
    # still read it, and old rows only have this. New notes are appended to
    # `remarks_history` instead — a legacy string surfaces there as the first
    # entry on read (see normalize_remarks_history), never migrated in place.
    remarks: Optional[str] = ""
    remarks_history: List[RemarkEntry] = Field(default_factory=list)
    assigned_to: Optional[str] = ""     # display name, kept for legacy rows / CSV export
    assigned_to_id: Optional[str] = ""  # Staff (users) id when linked via the picker
    attended_by: Optional[str] = ""       # who met the lead — linked to Team/Users by name
    confidence_level: Optional[float] = None  # 0-100 — sales rep's read on close probability
    team_id: Optional[str] = ""           # direct team link for reporting; independent of assigned_to's own team_id
    visitor_id: Optional[str] = ""        # lineage when converted from a Visitor
    value: Optional[float] = 0
    # Dated, multi-entry audit trail: [{at, by, by_id, text, confidence_level, kind}].
    # `remarks` above stays a plain string (unmigrated) — old screens still read it.
    log: List[dict] = Field(default_factory=list)
    custom_fields: dict = Field(default_factory=dict)  # key (CustomFieldDef.key) -> value


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

    @field_validator("confidence_level")
    @classmethod
    def _snap_confidence(cls, v):
        return lc.snap_confidence(v)


class Lead(LeadBase):
    id: str
    created_at: str


# ------- Floors (stock-ledger warehouse/floor color coding) -------
class FloorBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    color: Optional[str] = ""  # one of PALETTE_KEYS (server.py) — assigned server-side if blank


class FloorCreate(FloorBase):
    pass


class Floor(FloorBase):
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
    email: Optional[str] = ""   # optional; captured by the Lead modal's inline create sub-form
    # Optional extra contacts, e.g. a site PM or second number — [{name, phone}].
    alternate_contacts: Optional[Any] = Field(default_factory=list)
    last_contact: Optional[str] = ""
    visited: bool = False
    assigned_to: Optional[str] = ""     # display name, kept for legacy rows / CSV export
    assigned_to_id: Optional[str] = ""  # Staff (users) id when linked via the picker
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
    # Settlement split on the quote. `other` was called `cash` before the
    # Other / Direct Settlement rename — the alias keeps pre-rename quote
    # rows and older clients readable.
    other: Optional[float] = Field(0, validation_alias=AliasChoices("other", "cash"))
    bank: Optional[float] = 0
    mode: Optional[str] = "Walk-in"
    remarks: Optional[str] = ""
    line_items: Optional[List[dict]] = []
    subtotal: Optional[float] = 0
    tax_pct: Optional[float] = GST_DOC_DEFAULT
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
    # ---- Visual drag-and-drop builder (optional — a quote can stay a plain
    # line-item quote via QuoteWorkspace and never touch these). Same quote
    # record either way: one id, one quote_no, one stage/approval workflow,
    # one deal-won path — never a second parallel "quotation" entity.
    template_id: Optional[str] = ""      # which pre-built industry template this was instantiated from, if any
    layout_config: Optional[dict] = None  # {section_order: [ids], visible: {id: bool}, column_headers: {...}}
    sections: Optional[List[dict]] = None  # [{id, type, title, tax_rate, discount_pct, items: [...]}]
    financial_summary: Optional[dict] = None  # {subtotal, total_discount, total_tax, grand_total}


class QuoteCreate(QuoteBase):
    @field_validator("confidence_level")
    @classmethod
    def _snap_confidence(cls, v):
        return lc.snap_confidence(v)


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


# ------- Vendors -------
class VendorBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    code: Optional[str] = ""  # VEN-NNN, assigned server-side (see lifecycle.next_vendor_code)


class VendorCreate(VendorBase):
    pass


class Vendor(VendorBase):
    id: str
    created_at: str


# ------- Inventory -------
class InventoryBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str
    name: str
    category: Optional[str] = ""
    vendor: Optional[str] = ""       # vendor name — derived server-side from vendor_id, admin/accountant only on read
    vendor_id: Optional[str] = ""    # Vendor.id, set via the picker
    vendor_code: Optional[str] = ""  # vendor's serial code — derived server-side, visible to everyone
    model_no: Optional[str] = ""
    qty: int = 1
    cost: float = 0
    mrp: float = 0
    margin: float = 0
    status: str = "In Stock"  # In Stock / Display / Sold / Missing / Reserved
    location: Optional[str] = "Warehouse"
    image_url: Optional[str] = ""
    vendor_code: Optional[str] = ""
    division: Optional[str] = ""  # Division.slug, for the price-tag's division logo/brand color
    # Always stored in millimetres regardless of what the entry form was set
    # to — the price-tag PDF and every report read these directly, so a row
    # whose numbers meant inches would silently corrupt them. `dimension_unit`
    # records only which unit to DISPLAY and re-edit in; it never changes what
    # the three *_mm fields mean.
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    depth_mm: Optional[float] = None
    dimension_unit: Optional[str] = "mm"  # "mm" | "in" — display/entry unit only
    material_finish: Optional[str] = ""

    @field_validator("dimension_unit")
    @classmethod
    def _valid_dimension_unit(cls, v):
        v = str(v or "mm")
        if v not in ("mm", "in"):
            raise ValueError("dimension_unit must be mm or in")
        return v


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
    priority: str = "Medium"  # Low / Medium / High / Urgent
    due_date: Optional[str] = ""
    assigned_to: Optional[str] = ""
    category: Optional[str] = "General"
    ref: Optional[str] = ""
    ref_type: Optional[str] = ""  # "" / lead / quote / sale / project — what `ref` points at
    linked_entity_name: Optional[str] = ""  # display name for ref/ref_type, e.g. the project's customer name
    notes: Optional[str] = ""
    done: bool = False
    # Daily Planner fields — `date` is the day this task is planned for
    # (distinct from `due_date`, which is a deadline, not a plan slot).
    # `status` is the richer state Daily Planner needs; `done` stays the
    # boolean the original Tasks page reads — normalize_task keeps both in
    # sync regardless of which UI made the edit.
    date: Optional[str] = ""
    time_slot: Optional[str] = ""
    status: str = "Pending"  # Pending / In Progress / Completed / Rolled Over
    completed_at: Optional[str] = ""
    is_recurring: bool = False
    updated_at: Optional[str] = ""


class TaskCreate(TaskBase):
    pass


class Task(TaskBase):
    id: str
    created_at: str
    created_by: Optional[str] = ""
    created_by_id: Optional[str] = ""  # stamped server-side; personal-visibility key


# ------- Line item (shared by Quotes / Invoices) -------
class LineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: Optional[str] = ""
    description: str = ""
    hsn: Optional[str] = ""
    qty: float = 1
    rate: float = 0
    discount_pct: Optional[float] = 0
    tax_pct: Optional[float] = GST_DOC_DEFAULT  # GST slab for this line (HSN/SAC dependent)


# ------- Purchase Orders (outbound: what WE buy from a vendor) -------
# Reuses LineItem above rather than defining a PO-specific line: it already
# carries exactly what a PO line needs (sku, description, hsn, qty, rate,
# discount_pct, tax_pct). Totals are computed server-side via lc.po_totals,
# never trusted from the client.
PO_STATUSES = ["Draft", "Issued", "Received", "Cancelled"]
# A PO only becomes real committed spend once it leaves Draft, and a
# Cancelled one stops being spend — this is the set project P&L counts.
PO_COMMITTED_STATUSES = {"Issued", "Received"}


class PurchaseOrderBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    po_no: Optional[str] = ""        # PO-YYMM-NNN, assigned server-side
    date: str = ""
    vendor_id: str = ""
    vendor_name: Optional[str] = ""  # derived server-side from vendor_id
    vendor_code: Optional[str] = ""  # derived server-side from vendor_id
    project_id: Optional[str] = ""   # when this PO is bought against a project — feeds project P&L
    division: Optional[str] = ""
    line_items: List[LineItem] = Field(default_factory=list)
    subtotal: float = 0
    tax_total: float = 0
    grand_total: float = 0
    payment_terms: Optional[str] = ""
    delivery_address: Optional[str] = ""
    expected_date: Optional[str] = ""
    # Draft never counts as committed spend; Cancelled stops counting. Only
    # Issued/Received feed project P&L material cost (see compute_project_pnl).
    status: str = "Draft"            # Draft / Issued / Received / Cancelled
    by_user: Optional[str] = ""
    remarks: Optional[str] = ""

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        v = str(v or "Draft")
        if v not in PO_STATUSES:
            raise ValueError(f"status must be one of {PO_STATUSES}")
        return v


class PurchaseOrderCreate(PurchaseOrderBase):
    @field_validator("vendor_id")
    @classmethod
    def _vendor_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("A vendor is required on a purchase order")
        return v


class PurchaseOrder(PurchaseOrderBase):
    id: str
    created_at: str


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
    # Direct project linkage. Tasks already had this via their generic
    # ref/ref_type pair ("project" is one of the accepted ref_type values);
    # meetings had no equivalent, so a site meeting could not be tied to the
    # project it was about.
    project_id: Optional[str] = ""
    agenda: Optional[str] = ""
    status: str = "Scheduled"  # Scheduled / Done / Cancelled
    created_by: Optional[str] = ""
    created_by_id: Optional[str] = ""  # stamped server-side; personal-visibility key


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
    mode: str = "Other"  # Other (Direct Settlement) / Bank / UPI
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
    project_id: Optional[str] = ""        # "" = not linked to a project
    imprest_limit: Optional[float] = 0    # 0 = no limit; shown as a balance-vs-limit bar
    strict_overdraft: bool = False        # when true, an expense can't be approved past current_balance


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
    payment_mode: str = "OTHER"           # OTHER (Direct Settlement) / UPI / ONLINE
    remark: Optional[str] = ""
    receipt_url: Optional[str] = ""
    entry_person: Optional[str] = ""
    custodian_upi_id: Optional[str] = ""  # payee VPA, e.g. user@okhdfcbank — for the UPI pay deep-link
    payout_utr: Optional[str] = ""        # bank UTR reference, set once the payout is confirmed
    # CASH_IN is pre-trusted credit and lands on current_balance immediately
    # (see create_cashbook_entry) — only a CASH_OUT (expense) is created
    # Pending and only debits the book once approved (see approve_cashbook_entry).
    status: str = "Approved"             # Pending / Approved / Rejected
    approved_by: Optional[str] = ""
    approved_at: Optional[str] = ""


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


class CashbookEntryApproval(BaseModel):
    approved: bool
    utr_number: Optional[str] = ""  # bank UTR once the payout is actually made


class CashbookTopUp(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: float
    payment_mode: str = "OTHER"
    remark: Optional[str] = ""
    entry_person: Optional[str] = ""

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v):
        if v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


class CashbookExpense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: float
    category: Optional[str] = ""
    payment_mode: str = "OTHER"
    remark: Optional[str] = ""
    receipt_url: Optional[str] = ""
    entry_person: Optional[str] = ""
    custodian_upi_id: Optional[str] = ""  # payee VPA, captured at expense-logging time if known

    @field_validator("amount")
    @classmethod
    def _positive_amount(cls, v):
        if v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


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


# ------- Agent conversations (durable per-record conversation handle —
# the "shape" of a Durable Agent Bridge, in-process today; no separate
# process, no LLM, see backend/agent_bridge.py for why) -------
class AgentConversationBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject_type: str                          # "lead" / "quote" / "sale" / ...
    subject_id: str
    status: str = "open"                       # open / awaiting_input / closed
    pending_question: Optional[dict] = None    # durable HITL record: {id, text, options, asked_at}
    resume_cursor: Optional[str] = ""          # opaque pointer for a future remote executor
    # {at, by, by_id, text, kind} — kind: message / tool_call / question / answer.
    # Same ledger convention as Lead.log/Quote.log/AgentTask.log; this IS the
    # durable event archive, not a separate collection (see agent_bridge.py).
    log: List[dict] = Field(default_factory=list)


class AgentConversationCreate(AgentConversationBase):
    pass


class AgentConversation(AgentConversationBase):
    id: str
    created_at: str


# ------- Record contacts (a lightweight many-to-many "people on this
# record" join, e.g. a lead's site engineer or decision maker, beyond the
# single customer/assigned_to string fields Lead/Quote/Sale already carry) -------
class RecordContactBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject_type: str              # "lead" / "quote" / "sale" / "project"
    subject_id: Optional[str] = "" # "" is valid at request time — the create
                                    # endpoint fills it in via resolve_phone
                                    # when the caller only knows a phone number
    contact_name: str
    contact_phone: Optional[str] = ""
    role: Optional[str] = ""       # free text, e.g. "Decision Maker", "Site Engineer"


class RecordContactCreate(RecordContactBase):
    @field_validator("contact_name")
    @classmethod
    def _name_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Contact name is required")
        return v


class RecordContact(RecordContactBase):
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


# ------- Tenant business profile: per-tenant division roster, so a sister
# entity onboarded onto this same codebase configures its own divisions
# instead of the app hardcoding Madio's three business lines. -------
# The canonical Project.stage values, unchanged across every division —
# notifications, division-pulse, and P&L all key off these exact strings.
# A division only customizes how each one is LABELED for its own trade,
# never the underlying state machine.
PROJECT_STAGE_KEYS = ["Survey", "Quoted", "Execution", "Review", "Closure", "Completed"]


class Division(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    slug: str
    brand_color: Optional[str] = "#0062D2"  # matches --brand in index.css (Aura Blue)
    logo_url: Optional[str] = ""
    custom_sku_prefix: Optional[str] = ""
    terms_and_conditions: Optional[str] = ""
    stage_labels: Optional[dict] = None  # PROJECT_STAGE_KEYS entry -> this division's display label


DEFAULT_DIVISIONS = [
    Division(id="furniture", name="Madio Furniture", slug="Furniture", custom_sku_prefix="MF", stage_labels={
        "Survey": "Site Survey", "Quoted": "3D Render & Quote", "Execution": "Execution",
        "Review": "Quality Check", "Closure": "Delivery", "Completed": "Completed",
    }),
    Division(id="map", name="MAP Premium Acrylic Paints", slug="MAP", custom_sku_prefix="MAP", stage_labels={
        "Survey": "Substrate Moisture Test", "Quoted": "Surface Prep Quote", "Execution": "Topcoat",
        "Review": "Quality Inspection", "Closure": "Warranty", "Completed": "Completed",
    }),
    Division(id="dw", name="Madio Doors & Windows", slug="D&W", custom_sku_prefix="DW", stage_labels={
        "Survey": "Site Measurement", "Quoted": "Fabrication Quote", "Execution": "Installation",
        "Review": "Quality Check", "Closure": "Handover", "Completed": "Completed",
    }),
]


class TenantBusinessProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    divisions: List[Division] = Field(default_factory=lambda: [d.model_copy() for d in DEFAULT_DIVISIONS])


class TenantBusinessProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    divisions: List[Division]


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
    quote_id: Optional[str] = ""          # the deal this project was won from (lineage)
    sale_id: Optional[str] = ""           # links back to the sales order it was generated from
    lead_id: Optional[str] = ""           # lineage back to the originating lead
    requirement_id: Optional[str] = ""    # set when started from a Requirement, before any quote exists
    milestones: List[dict] = Field(default_factory=list)  # [{name, status, completed_at}]
    log: List[dict] = Field(default_factory=list)  # [{at, by, by_id, text, confidence_level, kind}]
    # Incentive-pipeline lineage, set once at deal-won provisioning time —
    # sales_rep_id is a display name, matching the by_user/assigned_to
    # convention used everywhere else in this codebase, not a true user id.
    budgeted_petty_cash: Optional[float] = 0
    sales_rep_id: Optional[str] = ""
    architect_id: Optional[str] = ""
    incentive_total: Optional[float] = 0
    stakeholders: Optional["ProjectStakeholders"] = None
    current_milestone: Optional[str] = ""
    completion_percentage: Optional[int] = 0
    custom_fields: dict = Field(default_factory=dict)  # key (CustomFieldDef.key) -> value


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
    stakeholders: Optional["ProjectStakeholders"] = None
    current_milestone: Optional[str] = None
    completion_percentage: Optional[int] = None
    custom_fields: Optional[dict] = None


class ProjectStageUpdate(BaseModel):
    stage: str


class Project(ProjectBase):
    id: str
    created_at: str


# ------- Project stakeholder linkage — four fixed slots on a project,
# each optionally pointing at an id in an existing collection (architects /
# record_contacts / customers / users) via `id`, so unlinking is just
# clearing the slot rather than deleting a record. -------
class StakeholderPerson(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = ""
    name: str
    phone: str
    email: Optional[str] = ""


class ArchitectStakeholder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = ""
    name: str
    phone: Optional[str] = ""
    firm: Optional[str] = ""
    commission_rate: Optional[float] = None


class ContractorStakeholder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = ""
    name: str
    phone: str
    role: Literal["APPLICATOR", "FABRICATOR", "CARPENTER", "LEAD_INSTALLER"]


class SupervisorStakeholder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    phone: Optional[str] = ""


class ProjectStakeholders(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client_poc: Optional[StakeholderPerson] = None
    architect: Optional[ArchitectStakeholder] = None
    applicator_or_contractor: Optional[ContractorStakeholder] = None
    internal_site_supervisor: Optional[SupervisorStakeholder] = None


ProjectBase.model_rebuild()
ProjectCreate.model_rebuild()
Project.model_rebuild()
ProjectUpdate.model_rebuild()


# ------- Daily site execution log — one entry per project per day,
# capturing what a site supervisor reports. Separate collection from the
# generic `Project.log` (freeform notes/audit trail) since a daily log has
# a fixed, structured shape (labor, materials, photos) that a freeform log
# entry doesn't. -------
class MaterialReceived(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_name: str
    quantity: float = 0
    unit: str = ""


class LaborCount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    skilled: int = 0
    unskilled: int = 0


class ProjectDailyLogBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project_id: str
    division: Optional[str] = ""
    log_date: str
    supervisor_id: Optional[str] = ""
    supervisor_name: str
    work_completed_today: str
    materials_received: List[MaterialReceived] = Field(default_factory=list)
    labor_count: LaborCount = Field(default_factory=LaborCount)
    site_hindrances: Optional[str] = ""
    site_photos: List[str] = Field(default_factory=list)
    # When set, POSTing this log also advances the parent project's rollup
    # fields (current_milestone always overwrites; completion_percentage
    # only ever moves up — see create_project_daily_log in server.py).
    current_milestone: Optional[str] = None
    completion_percentage: Optional[int] = None


class ProjectDailyLogCreate(ProjectDailyLogBase):
    pass


class ProjectDailyLog(ProjectDailyLogBase):
    id: str
    tenant_id: Optional[str] = ""
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
    # Structural clear height above the aperture, in inches like w/h. A
    # fabricator needs it to know whether the frame can be top-fixed; it was
    # previously only ever captured in free-text `notes`, if at all.
    lintel: Optional[float] = 0
    hardware_finish: Optional[str] = ""  # e.g. "SS Brushed", "Black Matte"
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
    # Record linkage. `customer` above stays the plain display string every
    # existing survey was written with (and what the quote conversion reads);
    # these ids are additive, so a legacy survey with none of them still
    # loads and converts exactly as before.
    customer_id: Optional[str] = ""
    project_id: Optional[str] = ""
    architect_id: Optional[str] = ""
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
    mode: str = "Other"                 # Other (Direct Settlement) / Bank / UPI / Cheque
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
    # Earned = auto-provisioned at deal-won time, not yet reviewed;
    # Approved / Paid — a manually-approved row could also be created
    # directly (the pre-existing /analytics/commissions/approve flow).
    status: str = "Approved"            # Earned / Approved / Paid
    approved_by: Optional[str] = ""
    paid_at: Optional[str] = ""
    remarks: Optional[str] = ""
    project_id: Optional[str] = ""      # set when auto-provisioned from a won deal
    quote_id: Optional[str] = ""


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
    tax_pct: float = GST_DOC_DEFAULT
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
    custom_fields: dict = Field(default_factory=dict)  # key (CustomFieldDef.key) -> value


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

    @field_validator("confidence_level")
    @classmethod
    def _snap_confidence(cls, v):
        return lc.snap_confidence(v)


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


# ------- Saved views (per-user or shared filter presets on a list page) -------
class SavedViewBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entity: str                    # "leads" / "customers" / ... — matches the frontend page's own key
    name: str
    filters: dict = Field(default_factory=dict)   # opaque — replayed as-is into the page's filter state
    shared: bool = False           # visible to the whole tenant, not just the creator


class SavedViewCreate(SavedViewBase):
    @field_validator("name")
    @classmethod
    def _name_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Name is required")
        return v


class SavedView(SavedViewBase):
    id: str
    created_by: Optional[str] = ""
    created_by_id: Optional[str] = ""
    created_at: str


# ------- Custom field definitions (admin-configurable extra fields per
# entity; values live directly on the entity's own document as a
# custom_fields dict, not in a separate collection) -------
class CustomFieldDefBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entity: str                    # "lead" / "customer"
    key: str                       # server-assigned slug of label, immutable
    label: str
    type: str = "text"             # text / number / date / select / boolean
    options: List[str] = Field(default_factory=list)   # for type == "select"
    show_table: bool = False
    show_filter: bool = False
    show_detail: bool = True
    order: int = 0
    active: bool = True

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v):
        if v not in ("text", "number", "date", "select", "boolean"):
            raise ValueError("type must be text, number, date, select, or boolean")
        return v


class CustomFieldDefCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entity: str
    label: str
    type: str = "text"
    options: List[str] = Field(default_factory=list)
    show_table: bool = False
    show_filter: bool = False
    show_detail: bool = True

    @field_validator("label")
    @classmethod
    def _label_required(cls, v):
        if not str(v or "").strip():
            raise ValueError("Label is required")
        return v

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v):
        if v not in ("text", "number", "date", "select", "boolean"):
            raise ValueError("type must be text, number, date, select, or boolean")
        return v


class CustomFieldDefUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: Optional[str] = None
    options: Optional[List[str]] = None
    show_table: Optional[bool] = None
    show_filter: Optional[bool] = None
    show_detail: Optional[bool] = None
    order: Optional[int] = None
    active: Optional[bool] = None


class CustomFieldDef(CustomFieldDefBase):
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


# ------- Finance: split Other/bank-transfer payments with GST -------
# A separate collection/model from the existing Payment (sale/invoice
# collection ledger, no GST or deal/project linkage) — this tracks
# deal/project-level settlements with a GST-bearing bank-transfer component
# and a privacy-maskable Other component, which would be an awkward,
# backward-incompatible bolt-on to the existing flat Payment shape.
class BankTransferComponent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    taxable_amount: float = 0
    gst_rate: float = GST_DEFAULT
    gst_amount: float = 0
    total_bt_amount: float = 0
    utr_reference: Optional[str] = ""
    bank_account_id: Optional[str] = ""
    tax_invoice_number: Optional[str] = ""


class OtherComponent(BaseModel):
    """The non-bank leg of a split payment — "Other" / Direct Settlement.

    Reads legacy `cash_amount` too: rows written before the terminology
    rename are still on disk, and an old client may still post that key.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    other_amount: float = Field(0, validation_alias=AliasChoices("other_amount", "cash_amount"))
    wallet_id: Optional[str] = ""
    receipt_voucher_no: Optional[str] = ""


class SplitPaymentBase(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    deal_id: Optional[str] = ""
    project_id: Optional[str] = ""
    customer_id: Optional[str] = ""
    payment_mode: Literal["BANK_TRANSFER", "OTHER", "SPLIT"]
    bank_transfer_component: Optional[BankTransferComponent] = None
    other_component: Optional[OtherComponent] = Field(
        None, validation_alias=AliasChoices("other_component", "cash_component"))
    receipt_date: str

    @field_validator("payment_mode", mode="before")
    @classmethod
    def _rename_legacy_mode(cls, v):
        """Legacy callers/rows still say CASH; it is now OTHER."""
        return "OTHER" if v == "CASH" else v


class SplitPaymentCreate(SplitPaymentBase):
    pass


class SplitPayment(SplitPaymentBase):
    id: str
    tenant_id: str
    total_collected: float = 0
    status: Literal["RECORDED", "VERIFIED", "RECONCILED"] = "RECORDED"
    created_at: str


def normalize_settlement(doc: dict) -> dict:
    """Map a stored finance_payments row from the pre-rename shape
    (payment_mode "CASH", `cash_component.cash_amount`) onto the current
    Other / Direct Settlement shape. Mutates and returns `doc`.

    Applied on read rather than as a one-shot data migration so that rows
    written by an older server instance mid-deploy are also handled.
    """
    if doc.get("payment_mode") == "CASH":
        doc["payment_mode"] = "OTHER"
    legacy = doc.pop("cash_component", None)
    if legacy and not doc.get("other_component"):
        legacy["other_amount"] = legacy.pop("cash_amount", legacy.get("other_amount", 0))
        doc["other_component"] = legacy
    return doc


def normalize_remarks_history(doc: dict) -> dict:
    """Surface a Lead's legacy flat `remarks` string as the first entry of
    `remarks_history`. Mutates and returns `doc`.

    Applied on read rather than as a one-shot data migration — same reason as
    normalize_settlement above: rows written by an older server instance
    mid-deploy are handled too. `remarks` is deliberately left in place; CSV
    export and the leads list filter still read it.
    """
    if doc.get("remarks_history"):
        return doc
    legacy = str(doc.get("remarks") or "").strip()
    doc["remarks_history"] = [{
        "id": f"legacy-{doc.get('id') or ''}",
        "text": legacy,
        # No timestamp was ever recorded for a flat remark, so fall back to
        # when the lead itself was created rather than inventing "now".
        "created_at": doc.get("created_at") or doc.get("date") or "",
        # Nor an author — left blank rather than misattributed to whoever
        # happens to be assigned to the lead today.
        "author_name": "",
    }] if legacy else []
    return doc


def mask_settlement(doc: dict) -> dict:
    """Redact the Other / Direct Settlement leg for a masked viewer.

    Nulling `other_component` on its own does NOT hide the figure:
    `total_collected` is bank-transfer + Other, and the bank-transfer leg
    stays visible on purpose (it is the invoiceable, official number), so
    `total_collected - total_bt_amount` hands the hidden amount straight
    back. Under the mask the total is therefore restated as the
    bank-transfer-only figure, leaving a zero residual and nothing to
    subtract.

    It is restated from `total_bt_amount` — the exact field the masked
    response also exposes — so the two can never disagree by a rounding
    step. A row with no bank-transfer leg masks down to 0.

    Mutates and returns `doc`. Apply only to masked responses; the
    unmasked/PIN-unlocked shape must keep the real grand total.
    """
    doc["other_component"] = None
    bt = doc.get("bank_transfer_component") or {}
    doc["total_collected"] = bt.get("total_bt_amount") or 0
    return doc


def mask_cashbook_entry(doc: dict) -> dict:
    """Redact a wallet entry that was credited from a masked Other/Direct
    Settlement collection (see the split-payment wallet credit in server.py,
    which tags these `category="Payment Collection"`).

    Without this, a masked settlement's real amount was still readable in
    plain text on the project's Cashbook screen by anyone with cashbook
    view access — the mask on /finance/payments and the P&L report didn't
    apply to the wallet ledger the same money lands in.

    Mutates and returns `doc`. Apply only to masked responses.
    """
    if doc.get("category") == "Payment Collection":
        doc["amount"] = None
        doc["entry_person"] = None
    return doc


class PrivacyPinSet(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pin: str  # 4-digit PIN, hashed with the same bcrypt helper as login PINs


class PrivacyPinVerify(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pin: str
