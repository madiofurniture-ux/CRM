"""
Budgets — cost-center spend control (Budget / BudgetLine / BudgetOverride /
BudgetTransaction). Built from prompt_3_budgets.md.

Standalone module, no import-time dependency on server.py — same pattern as
models_wallet.py/models_canonical.py; api_budget.py reads the Mongo handle
off request.app.state.db.

Money is integer paise everywhere except the API boundary, where the
existing expense sources this links to (PettyCash.amount, PurchaseOrder.
grand_total) are float rupees — models_wallet.to_paise/from_paise are
reused for that conversion, same paise boundary Wallets already draws.

Primary keys use the codebase's "id" convention (not the literal
budget_id/line_id/override_id/transaction_id names prompt_3_budgets.md
spells out) — models_wallet.py made the same deviation from
prompt_1_wallets.md for the same reason: every other entity in this
codebase keys off "id", and a one-off "budget_id" primary key would be a
trap for every helper that assumes "id". Foreign keys keep descriptive
names (budget_id, budget_line_id, source_id) so a document is still
self-describing without its parent in hand.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator
from typing import List, Optional

from models_canonical import new_id, now_iso  # reuse — identical helpers already exist there
from models_wallet import to_paise, from_paise  # reuse — same paise boundary convention

BUDGET_STATUSES = ["Draft", "Approved", "Closed", "Superseded"]
COST_CENTER_TYPES = ["Department", "Project", "Unit"]
BUDGET_CATEGORIES = ["Material", "Labour", "Overhead", "Petty_Cash", "Payroll", "Other"]
OVERRIDE_STATUSES = ["Pending", "Approved", "Rejected"]
TRANSACTION_SOURCE_TYPES = ["PettyCash", "PurchaseOrder", "Invoice", "Payroll"]

DEFAULT_WARNING_THRESHOLD = 80.0  # % utilized
DEFAULT_BLOCK_THRESHOLD = 100.0   # % utilized


def compute_variance(budgeted_amount: int, spent_amount: int) -> tuple[int, float]:
    """(variance paise, variance_percent). Guarded against a zero/negative
    budgeted_amount, which would otherwise divide by zero — treated as
    fully overspent if anything has been posted, untouched otherwise."""
    variance = int(budgeted_amount) - int(spent_amount)
    if budgeted_amount <= 0:
        variance_percent = -100.0 if spent_amount > 0 else 0.0
    else:
        variance_percent = round(variance / budgeted_amount * 100, 2)
    return variance, variance_percent


class BudgetLineCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    category: str
    budgeted_amount: int  # paise
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD
    block_threshold: float = DEFAULT_BLOCK_THRESHOLD

    @field_validator("category")
    @classmethod
    def _valid_category(cls, v):
        if v not in BUDGET_CATEGORIES:
            raise ValueError(f"category must be one of {BUDGET_CATEGORIES}")
        return v

    @field_validator("budgeted_amount")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("budgeted_amount must be positive")
        return v


class BudgetLine(BudgetLineCreate):
    id: str
    budget_id: str
    spent_amount: int = 0
    variance: int = 0
    variance_percent: float = 0.0


class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # No tenant_id field: tenancy.stamp() derives it from the authenticated
    # user, same as every other *Create model in this codebase — a client
    # supplying its own tenant_id would be a cross-tenant write vector.
    cost_center_id: str
    cost_center_type: str = "Project"
    period_start: str
    period_end: str
    notes: Optional[str] = ""
    lines: List[BudgetLineCreate]

    @field_validator("cost_center_type")
    @classmethod
    def _valid_cc_type(cls, v):
        v = str(v or "Project")
        if v not in COST_CENTER_TYPES:
            raise ValueError(f"cost_center_type must be one of {COST_CENTER_TYPES}")
        return v

    @field_validator("lines")
    @classmethod
    def _valid_lines(cls, v):
        if not v:
            raise ValueError("a budget needs at least one line")
        cats = [ln.category for ln in v]
        if len(cats) != len(set(cats)):
            raise ValueError("duplicate category in budget lines")
        return v


class Budget(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    cost_center_id: str
    cost_center_type: str
    period_start: str
    period_end: str
    status: str = "Draft"
    created_by: Optional[str] = ""
    approved_by: Optional[str] = ""
    created_at: str
    approved_at: Optional[str] = ""
    notes: Optional[str] = ""


class BudgetOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requested_amount: int  # paise, additional budget requested
    reason: str

    @field_validator("requested_amount")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("requested_amount must be positive")
        return v


class BudgetOverride(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    budget_line_id: str
    requested_amount: int
    reason: str
    requested_by: str
    approved_by: Optional[str] = ""
    approved_at: Optional[str] = ""
    status: str = "Pending"
    created_at: str


class BudgetTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    budget_line_id: str
    source_type: str
    source_id: str
    amount: int  # paise
    posted_at: str
