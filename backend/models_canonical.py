"""
Canonical CRM v1 models — Account, Contact, Lead, Opportunity, Product,
Quotation, Activity.

These are additive, namespaced collections (crm_accounts, crm_contacts,
crm_leads, crm_opportunities, crm_products, crm_quotations, crm_activities)
that sit alongside the existing models.py collections (leads, quotes, sales,
...). They do not replace anything — see docs/MODEL_MAPPING.md for how the
two relate and the migration path.

Multi-tenancy: every entity carries `tenant_id`, matching tenancy.py's
existing field. The engineering brief for this feature calls that field
"brand_id" — same concept (one Mongo database, scoped by tenant), so we
reuse tenant_id instead of adding a second, parallel tenancy key. See
docs/MODEL_MAPPING.md.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional

from models import new_id, now_iso  # re-exported for api_canonical.py

__all__ = [
    "new_id", "now_iso",
    "AccountBase", "AccountCreate", "Account",
    "ContactBase", "ContactCreate", "Contact",
    "LeadBase", "LeadCreate", "Lead",
    "OpportunityBase", "OpportunityCreate", "Opportunity",
    "ProductBase", "ProductCreate", "Product",
    "QuotationBase", "QuotationCreate", "Quotation", "QuotationLine",
    "ActivityBase", "ActivityCreate", "Activity",
    "LEAD_STATUSES", "OPPORTUNITY_STAGES",
]


class _Tenanted(BaseModel):
    """Fields every canonical entity carries. Not a DB table of its own —
    just the shared shape, matching the brief's "every entity must include"
    list (brand_id/tenant_id, created_at, updated_at, custom_data)."""
    model_config = ConfigDict(extra="ignore")
    tenant_id: Optional[str] = ""   # stamped server-side; = "brand_id" in the PRD
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    custom_data: dict = Field(default_factory=dict)  # brand-specific extension fields


# ------- Account (company / organization a brand does business with) -------
class AccountBase(_Tenanted):
    name: str
    industry: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    website: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    owner_id: Optional[str] = ""     # Users.id — account owner / rep
    parent_account_id: Optional[str] = ""


class AccountCreate(AccountBase):
    pass


class Account(AccountBase):
    id: str


# ------- Contact (person, usually tied to an Account) -------
class ContactBase(_Tenanted):
    first_name: str
    last_name: Optional[str] = ""
    account_id: Optional[str] = ""   # Account.id
    email: Optional[str] = ""
    phone: Optional[str] = ""
    title: Optional[str] = ""        # job title
    is_primary: bool = False         # primary contact for its account
    owner_id: Optional[str] = ""


class ContactCreate(ContactBase):
    pass


class Contact(ContactBase):
    id: str


# ------- Lead (unqualified interest, pre-Account/Contact/Opportunity) -------
LEAD_STATUSES = ["new", "contacted", "qualified", "converted", "lost"]


class LeadBase(_Tenanted):
    name: str
    company: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = ""             # channel: referral, website, ads, ...
    lead_status: str = "new"               # LEAD_STATUSES
    owner_id: Optional[str] = ""
    matched_account_id: Optional[str] = "" # Account.id once matched/deduped
    converted_contact_id: Optional[str] = ""
    converted_opportunity_id: Optional[str] = ""
    notes: Optional[str] = ""


class LeadCreate(LeadBase):
    pass


class Lead(LeadBase):
    id: str


# ------- Opportunity (a qualified, in-progress deal) -------
# Stage lists are brand-configurable (see modules_loader.py); this is the
# fallback used when a brand manifest defines none.
OPPORTUNITY_STAGES = ["qualification", "proposal", "negotiation", "won", "lost"]


class OpportunityBase(_Tenanted):
    name: str
    account_id: Optional[str] = ""     # Account.id
    contact_id: Optional[str] = ""     # Contact.id — primary contact for the deal
    lead_id: Optional[str] = ""        # Lead.id this opportunity was converted from, if any
    stage_id: str = "qualification"    # OPPORTUNITY_STAGES or brand pipeline key
    amount: Optional[float] = 0
    probability: Optional[float] = None  # 0-100
    close_date: Optional[str] = None     # ISO date
    owner_id: Optional[str] = ""
    is_won: Optional[bool] = None        # None = open, True/False once decided
    lost_reason: Optional[str] = ""


class OpportunityCreate(OpportunityBase):
    pass


class Opportunity(OpportunityBase):
    id: str


# ------- Product -------
class ProductBase(_Tenanted):
    name: str
    sku: Optional[str] = ""
    category: Optional[str] = ""
    unit_price: Optional[float] = 0
    unit: Optional[str] = ""   # e.g. "sqft", "litre", "piece"
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    id: str


# ------- Quotation (offer sent against an Opportunity) -------
class QuotationLine(BaseModel):
    model_config = ConfigDict(extra="ignore")
    product_id: Optional[str] = ""
    description: Optional[str] = ""
    qty: float = 1
    unit_price: float = 0
    total: Optional[float] = None  # computed if omitted: qty * unit_price


class QuotationBase(_Tenanted):
    opportunity_id: str
    account_id: Optional[str] = ""
    template_id: Optional[str] = ""   # quotation_templates.py template, if used
    status: str = "draft"             # draft, sent, accepted, rejected, expired
    lines: List[QuotationLine] = Field(default_factory=list)
    total: Optional[float] = None     # computed if omitted: sum(lines.total)
    valid_until: Optional[str] = None
    owner_id: Optional[str] = ""


class QuotationCreate(QuotationBase):
    pass


class Quotation(QuotationBase):
    id: str


# ------- Activity (call/email/meeting/task logged against any entity) -------
class ActivityBase(_Tenanted):
    type: str = "note"   # call, email, meeting, task, note
    subject: Optional[str] = ""
    body: Optional[str] = ""
    related_type: Optional[str] = ""   # "account" | "contact" | "lead" | "opportunity"
    related_id: Optional[str] = ""
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    owner_id: Optional[str] = ""


class ActivityCreate(ActivityBase):
    pass


class Activity(ActivityBase):
    id: str
