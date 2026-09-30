"""
Canonical CRM v1 models — Account, Contact, Lead, Opportunity, Product,
Quotation, Activity.

These sit alongside (not instead of) backend/models.py. The existing
Lead/Quote/Sale/Customer/Architect/InventoryItem collections keep working
unchanged; this is a parallel, minimal, Salesforce/Odoo-shaped layer for the
new /api/v1 surface, intended as the target shape for a gradual migration
(see docs/MODEL_MAPPING.md).

Multi-tenancy: `tenant_id` is the hard isolation boundary and is stamped/
scoped by tenancy.py exactly like every other collection (a real SaaS
customer, later). `brand_id` is the softer, intra-tenant scope — one of
Madio's own brands (doors_windows / map_paints / navaki), equivalent to the
`division` field already used elsewhere in this codebase. A brand always
belongs to exactly one tenant.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Literal, Optional
import uuid
from datetime import datetime, timezone


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CanonicalBase(BaseModel):
    """Fields every canonical entity carries."""
    model_config = ConfigDict(extra="ignore")
    brand_id: str                              # required — which brand this record belongs to
    custom_data: dict = Field(default_factory=dict)  # brand-specific extension fields


class CanonicalOut(CanonicalBase):
    id: str
    tenant_id: str
    created_at: str
    updated_at: str


# ------- Account (Salesforce Account / Odoo res.partner (company)) -------
class AccountBase(CanonicalBase):
    name: str
    type: Literal["prospect", "customer", "partner", "vendor"] = "prospect"
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    owner_id: Optional[str] = ""   # Users.id


class AccountCreate(AccountBase):
    pass


class Account(AccountBase, CanonicalOut):
    pass


# ------- Contact (Salesforce Contact / Odoo res.partner (individual)) -------
class ContactBase(CanonicalBase):
    account_id: Optional[str] = ""   # -> Account.id
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    title: Optional[str] = ""        # job title / role at the account
    is_primary: bool = False


class ContactCreate(ContactBase):
    pass


class Contact(ContactBase, CanonicalOut):
    pass


# ------- Lead (Salesforce Lead / Odoo crm.lead in "lead" state) -------
LEAD_STATUSES = ["New", "Contacted", "Qualified", "Converted", "Lost"]


class LeadBase(CanonicalBase):
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = ""
    matched_account_id: Optional[str] = ""       # -> Account.id, set on de-dup match
    lead_status: str = "New"
    owner_id: Optional[str] = ""
    estimated_value: Optional[float] = 0
    converted_opportunity_id: Optional[str] = ""  # -> Opportunity.id, set by /convert


class LeadCreate(LeadBase):
    pass


class Lead(LeadBase, CanonicalOut):
    pass


# ------- Opportunity (Salesforce Opportunity / Odoo crm.lead in "opp" stage) -------
class OpportunityBase(CanonicalBase):
    name: str
    account_id: str                              # required -> Account.id
    contact_id: Optional[str] = ""                # -> Contact.id
    lead_id: Optional[str] = ""                    # lineage -> Lead.id
    stage_id: str = "New"
    probability: float = 0
    amount: float = 0
    close_date: Optional[str] = ""
    owner_id: Optional[str] = ""
    status: Literal["open", "won", "lost"] = "open"


class OpportunityCreate(OpportunityBase):
    pass


class Opportunity(OpportunityBase, CanonicalOut):
    pass


# ------- Product (Salesforce Product2 / Odoo product.product) -------
class ProductBase(CanonicalBase):
    name: str
    sku: Optional[str] = ""
    category: Optional[str] = ""
    unit_price: float = 0
    uom: Optional[str] = ""
    active: bool = True


class ProductCreate(ProductBase):
    pass


class Product(ProductBase, CanonicalOut):
    pass


# ------- Quotation (Odoo sale.order in draft/sent) -------
class QuotationBase(CanonicalBase):
    opportunity_id: str                            # required -> Opportunity.id
    account_id: Optional[str] = ""                  # denormalized from the opportunity
    quote_no: Optional[str] = ""
    status: Literal["draft", "sent", "accepted", "rejected", "expired"] = "draft"
    line_items: List[dict] = Field(default_factory=list)  # [{product_id, name, qty, unit_price, total}]
    subtotal: float = 0
    tax_total: float = 0
    grand_total: float = 0
    valid_until: Optional[str] = ""


class QuotationCreate(QuotationBase):
    pass


class Quotation(QuotationBase, CanonicalOut):
    pass


# ------- Activity (Salesforce Activity / Odoo mail.activity) -------
class ActivityBase(CanonicalBase):
    related_entity: Literal["account", "contact", "lead", "opportunity", "quotation"]
    related_id: str
    type: Literal["call", "email", "meeting", "note", "task"] = "note"
    subject: Optional[str] = ""
    notes: Optional[str] = ""
    due_date: Optional[str] = ""
    completed: bool = False
    owner_id: Optional[str] = ""


class ActivityCreate(ActivityBase):
    pass


class Activity(ActivityBase, CanonicalOut):
    pass
