"""Pydantic models for MADIO CRM."""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone
import uuid


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


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
    username: str
    pin: str


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
    source: Optional[str] = ""
    stage: str = "New"  # New, Contacted, Qualified, Quoted, Won, Lost
    follow_up_date: Optional[str] = ""
    remarks: Optional[str] = ""
    assigned_to: Optional[str] = ""
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
    value: float = 0
    cash: Optional[float] = 0
    bank: Optional[float] = 0
    mode: Optional[str] = "Walk-in"
    remarks: Optional[str] = ""


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
