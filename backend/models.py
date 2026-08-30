"""Pydantic models for MADIO CRM."""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone
import uuid


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
    role: str = "user"  # "admin" or "user"
    icon: str = "U"  # short label or emoji
    color: str = "#C85A32"
    pages: Optional[List[str]] = None  # None == all pages (admin)


class UserCreate(UserBase):
    pin: str  # 4-digit PIN


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    pages: Optional[List[str]] = None
    pin: Optional[str] = None


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
class LeadBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    name: str
    phone: Optional[str] = ""
    source: Optional[str] = ""
    architect_id: Optional[str] = ""    # Architect.id, set when source == "Architect"
    architect_name: Optional[str] = ""  # display name, prepopulated from the picker
    stage: str = "New"  # New, Contacted, Qualified, Quoted, Won, Lost
    follow_up_date: Optional[str] = ""
    # Accepts either the new list-of-entries shape or a legacy plain string;
    # normalize_lead() upgrades a legacy string to a single entry on write —
    # same convention as VisitorBase.remarks.
    remarks: Optional[Any] = Field(default_factory=list)
    assigned_to: Optional[str] = ""     # display name, kept for legacy rows / CSV export
    assigned_to_id: Optional[str] = ""  # Staff (users) id when linked via the picker
    value: Optional[float] = 0


class LeadCreate(LeadBase):
    pass


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


class QuoteCreate(QuoteBase):
    pass


class Quote(QuoteBase):
    id: str
    created_at: str


# ------- Sales -------
class SaleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sale_no: str
    date: str
    customer: str
    division: str = "Furniture"
    quote_ref: Optional[str] = ""
    by_user: Optional[str] = ""
    value: float = 0
    paid: float = 0
    balance: float = 0
    stage: str = "Delivered"
    remarks: Optional[str] = ""


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


class InventoryCreate(InventoryBase):
    pass


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
    notes: Optional[str] = ""
    image_url: Optional[str] = ""


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
