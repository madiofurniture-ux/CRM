"""
Wallets — petty cash -> project cash-position ledger.

Built from prompt_1_wallets.md. This is a SEPARATE entity from the existing
Cashbook system (models.py's CashbookBase/CashbookEntryBase, server.py's
cashbook_top_up/cashbook_expense/cashbook_entry_approve) — Cashbook already
does project-linked wallet accounting with top-up/approval and already
feeds csv_engine.compute_project_pnl. This module exists because
prompt_1_wallets.md specifies a distinct entity keyed off the FLAT
PettyCash ledger (models.py's PettyCashBase) with money in integer paise
rather than Cashbook's float rupees. See docs/WALLETS_DESIGN.md for the
overlap this creates and why it was built anyway (explicit instruction to
execute the prompt as written).

Standalone module, no import-time dependency on server.py — same pattern
as models_canonical.py/models_hr.py; api_wallets.py reads the Mongo handle
off request.app.state.db.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

from models_canonical import new_id, now_iso  # reuse — identical helpers already exist there

WALLET_STATUSES = ["Active", "Closed", "Suspended"]
WALLET_TXN_TYPES = ["Opening", "Voucher", "Topup", "Adjustment", "Invoice_Receipt"]
WALLET_TXN_DIRECTIONS = ["In", "Out"]
OVERHEAD_WALLET_NAME = "Overhead"


def to_paise(rupees) -> int:
    """Boundary conversion at the PettyCash link: PettyCash.amount is a
    float rupee figure (models.py's existing convention across every money
    field in this codebase); every Wallet figure is integer paise per
    prompt_1_wallets.md's explicit "no floating-point for money" constraint."""
    return round(float(rupees or 0) * 100)


def from_paise(paise) -> float:
    return round(int(paise or 0) / 100, 2)


class WalletBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project_id: Optional[str] = None  # None/omitted = overhead wallet, not tied to a project
    name: str
    opening_balance: int = 0  # paise
    current_balance: int = 0  # paise — server-derived, never trusted from the client
    currency: str = "INR"
    status: str = "Active"
    created_by: Optional[str] = ""
    closed_by: Optional[str] = ""

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        v = str(v or "Active")
        if v not in WALLET_STATUSES:
            raise ValueError(f"status must be one of {WALLET_STATUSES}")
        return v


class WalletCreate(WalletBase):
    pass


class Wallet(WalletBase):
    id: str
    created_at: str
    updated_at: str


class WalletTopUp(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: int
    narration: Optional[str] = ""
    linked_invoice_id: Optional[str] = ""

    @field_validator("amount")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("amount must be positive")
        return v


class WalletAdjustment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: int
    direction: str = "Out"
    narration: Optional[str] = ""
    reason: Optional[str] = ""

    @field_validator("amount")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("direction")
    @classmethod
    def _valid_direction(cls, v):
        v = str(v or "Out")
        if v not in WALLET_TXN_DIRECTIONS:
            raise ValueError(f"direction must be one of {WALLET_TXN_DIRECTIONS}")
        return v


class WalletTransactionBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    wallet_id: str
    type: str = "Voucher"
    amount: int = 0  # paise, always positive — direction carries the sign
    direction: str = "Out"
    linked_petty_cash_id: Optional[str] = ""
    linked_invoice_id: Optional[str] = ""
    narration: Optional[str] = ""
    created_by: Optional[str] = ""
    approved_by: Optional[str] = ""
    approved_at: Optional[str] = ""

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v):
        v = str(v or "Voucher")
        if v not in WALLET_TXN_TYPES:
            raise ValueError(f"type must be one of {WALLET_TXN_TYPES}")
        return v

    @field_validator("direction")
    @classmethod
    def _valid_direction(cls, v):
        v = str(v or "Out")
        if v not in WALLET_TXN_DIRECTIONS:
            raise ValueError(f"direction must be one of {WALLET_TXN_DIRECTIONS}")
        return v


class WalletTransaction(WalletTransactionBase):
    id: str
    created_at: str
