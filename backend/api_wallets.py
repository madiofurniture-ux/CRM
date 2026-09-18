"""
Wallet API — /api/v1/wallets. See models_wallet.py's module docstring for
why this is a separate entity from the existing Cashbook system.

Mounted after server.py finishes defining itself, same pattern as
api_canonical.py/api_hr.py: no import-time dependency on server.py, reads
the Mongo handle off request.app.state.db. `apply_petty_cash_voucher` is
the one function server.py calls directly (from normalize_petty_cash) —
everything else is only reached through this module's own routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional

import tenancy
import permissions as perm
from auth import get_current_user
from models_wallet import (
    new_id, now_iso, to_paise,
    WalletCreate, WalletTopUp, WalletAdjustment,
    OVERHEAD_WALLET_NAME,
)

router = APIRouter(prefix="/api/v1")

WALLETS = "wallets"
WALLET_TRANSACTIONS = "wallet_transactions"


def _db(request: Request):
    return request.app.state.db


# --------------------------------------------------------------- RBAC
# Reproduces server.py's _roles_for/_require_permission locally rather than
# importing them — same no-import-time-dependency-on-server.py reasoning as
# api_hr.py's own _roles_for/_can_hr/_require_hr.
async def _roles_for(db, user: dict) -> list:
    return await db.roles.find(tenancy.scope({}, "roles", user), {"_id": 0}).to_list(200)


async def _can_wallets(db, user: dict, action: str) -> bool:
    roles = await _roles_for(db, user)
    return perm.can(user, roles, "wallets", action)


async def _require_wallets(db, user: dict, action: str) -> None:
    if not await _can_wallets(db, user, action):
        raise HTTPException(status_code=403, detail=f"Not permitted: {action} wallets")


# --------------------------------------------------------------- helpers
async def _get_wallet_or_404(db, wallet_id: str, user: dict) -> dict:
    owned = tenancy.scope({"id": wallet_id}, WALLETS, user)
    wallet = await db[WALLETS].find_one(owned, {"_id": 0})
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


async def get_or_create_wallet(db, user: dict, *, project_id: Optional[str],
                                name: Optional[str] = None) -> dict:
    """Every project gets a wallet on its first petty-cash voucher; a missing
    project_id resolves to the tenant's single "Overhead" wallet. Both are
    auto-created on first use — queried by project_id first so a second
    voucher against the same project never spawns a duplicate wallet."""
    pid = project_id or None
    query = tenancy.scope({"project_id": pid, "status": {"$ne": "Closed"}}, WALLETS, user)
    existing = await db[WALLETS].find_one(query, {"_id": 0})
    if existing:
        return existing
    return await _create_wallet(db, user, WalletCreate(
        project_id=pid, name=name or (OVERHEAD_WALLET_NAME if pid is None else f"Project {pid} Wallet"),
        opening_balance=0,
    ))


async def _create_wallet(db, user: dict, payload: WalletCreate) -> dict:
    doc = payload.model_dump()
    doc["id"] = new_id()
    doc["current_balance"] = doc["opening_balance"]
    doc["created_by"] = doc.get("created_by") or (user or {}).get("name", "")
    doc["created_at"] = now_iso()
    doc["updated_at"] = doc["created_at"]
    tenancy.stamp(doc, WALLETS, user)
    await db[WALLETS].insert_one(dict(doc))
    doc.pop("_id", None)
    if doc["opening_balance"]:
        await _insert_transaction(
            db, user, doc, type_="Opening", amount=doc["opening_balance"], direction="In",
            narration="Opening balance",
        )
    return doc


async def _insert_transaction(db, user: dict, wallet: dict, *, type_: str, amount: int,
                              direction: str, narration: str = "",
                              linked_petty_cash_id: str = "", linked_invoice_id: str = "",
                              approved_by: str = "", approved_at: str = "") -> dict:
    txn = {
        "id": new_id(), "wallet_id": wallet["id"], "type": type_, "amount": int(amount),
        "direction": direction, "linked_petty_cash_id": linked_petty_cash_id,
        "linked_invoice_id": linked_invoice_id, "narration": narration,
        "created_by": (user or {}).get("name", ""), "approved_by": approved_by,
        "approved_at": approved_at, "created_at": now_iso(),
    }
    tenancy.stamp(txn, WALLET_TRANSACTIONS, user)
    await db[WALLET_TRANSACTIONS].insert_one(dict(txn))
    txn.pop("_id", None)
    return txn


async def _apply_delta(db, user: dict, wallet: dict, delta: int, *, type_: str,
                       narration: str = "", linked_petty_cash_id: str = "",
                       linked_invoice_id: str = "", allow_override: bool = True) -> dict:
    """Posts one transaction against `wallet` and updates its balance.
    `delta` is signed (+In / -Out). Blocks a negative projected balance
    unless the acting user holds the "wallets:approve" grant (the Division
    Head-style override) — in which case the transaction is auto-approved
    and stamped with who signed off on it."""
    projected = wallet["current_balance"] + delta
    direction = "In" if delta >= 0 else "Out"
    approved_by = approved_at = ""
    if projected < 0:
        can_override = allow_override and await _can_wallets(db, user, "approve")
        if not can_override:
            raise HTTPException(
                status_code=400,
                detail="This entry would take the wallet negative — needs Division Head override",
            )
        approved_by = (user or {}).get("name", "")
        approved_at = now_iso()
    txn = await _insert_transaction(
        db, user, wallet, type_=type_, amount=abs(delta), direction=direction,
        narration=narration, linked_petty_cash_id=linked_petty_cash_id,
        linked_invoice_id=linked_invoice_id, approved_by=approved_by, approved_at=approved_at,
    )
    owned = tenancy.scope({"id": wallet["id"]}, WALLETS, user)
    await db[WALLETS].update_one(owned, {"$set": {"current_balance": projected, "updated_at": now_iso()}})
    wallet = {**wallet, "current_balance": projected, "updated_at": txn["created_at"]}
    return {"wallet": wallet, "transaction": txn}


async def apply_petty_cash_voucher(db, user: dict, petty_cash_doc: dict) -> dict:
    """Called from server.py's normalize_petty_cash on create. Auto-creates
    (or reuses) the project/overhead wallet, posts a Voucher transaction,
    and returns {"wallet": ..., "transaction": ...} — the caller stamps
    wallet["id"] onto the petty-cash doc as wallet_id; this function never
    mutates petty_cash_doc itself."""
    wallet = await get_or_create_wallet(db, user, project_id=petty_cash_doc.get("project_id") or None)
    amount_paise = to_paise(petty_cash_doc.get("amount"))
    delta = amount_paise if str(petty_cash_doc.get("kind") or "Out") == "In" else -amount_paise
    return await _apply_delta(
        db, user, wallet, delta, type_="Voucher",
        narration=petty_cash_doc.get("description", ""),
        linked_petty_cash_id=petty_cash_doc.get("id", ""),
    )


# --------------------------------------------------------------- routes
@router.get("/wallets")
async def list_wallets(project_id: Optional[str] = None, status: Optional[str] = "Active",
                       request: Request = None, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_wallets(db, user, "view")
    q: dict = {}
    if project_id is not None:
        q["project_id"] = project_id or None
    if status:
        q["status"] = status
    query = tenancy.scope(q, WALLETS, user)
    return await db[WALLETS].find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.get("/wallets/{wallet_id}")
async def get_wallet(wallet_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_wallets(db, user, "view")
    wallet = await _get_wallet_or_404(db, wallet_id, user)
    txns = await db[WALLET_TRANSACTIONS].find(
        tenancy.scope({"wallet_id": wallet_id}, WALLET_TRANSACTIONS, user), {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {**wallet, "transactions": txns}


@router.post("/wallets")
async def create_wallet(payload: WalletCreate, request: Request,
                        user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_wallets(db, user, "create")
    return await _create_wallet(db, user, payload)


@router.post("/wallets/{wallet_id}/topup")
async def wallet_topup(wallet_id: str, payload: WalletTopUp, request: Request,
                       user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_wallets(db, user, "edit")
    wallet = await _get_wallet_or_404(db, wallet_id, user)
    txn_type = "Invoice_Receipt" if payload.linked_invoice_id else "Topup"
    result = await _apply_delta(
        db, user, wallet, payload.amount, type_=txn_type, narration=payload.narration,
        linked_invoice_id=payload.linked_invoice_id,
    )
    return result["wallet"]


@router.get("/wallets/{wallet_id}/transactions")
async def wallet_transactions(wallet_id: str, limit: int = 50, offset: int = 0,
                              request: Request = None, user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_wallets(db, user, "view")
    await _get_wallet_or_404(db, wallet_id, user)  # 404s before paginating, never leaks existence
    query = tenancy.scope({"wallet_id": wallet_id}, WALLET_TRANSACTIONS, user)
    cursor = db[WALLET_TRANSACTIONS].find(query, {"_id": 0}).sort("created_at", -1)
    return await cursor.skip(max(0, offset)).limit(max(1, min(limit, 500))).to_list(500)


@router.post("/wallets/{wallet_id}/adjustment")
async def wallet_adjustment(wallet_id: str, payload: WalletAdjustment, request: Request,
                            user: dict = Depends(get_current_user)):
    db = _db(request)
    await _require_wallets(db, user, "edit")
    wallet = await _get_wallet_or_404(db, wallet_id, user)
    delta = payload.amount if payload.direction == "In" else -payload.amount
    narration = payload.narration or payload.reason
    result = await _apply_delta(db, user, wallet, delta, type_="Adjustment", narration=narration)
    return result["wallet"]


# --------------------------------------------------- project P&L read model
# Deliberately its own small function rather than wired into
# csv_engine.compute_project_pnl: that function already computes
# approved_petty_cash/material_cost/gross_profit from the Cashbook system,
# and folding Wallet activity into the same totals would double-count any
# project that uses both systems. See docs/WALLETS_DESIGN.md.
async def project_wallet_pnl(db, user: dict, project_id: str) -> dict:
    wallets = await db[WALLETS].find(
        tenancy.scope({"project_id": project_id}, WALLETS, user), {"_id": 0}).to_list(200)
    wallet_ids = [w["id"] for w in wallets]
    txns = []
    if wallet_ids:
        txns = await db[WALLET_TRANSACTIONS].find(
            tenancy.scope({"wallet_id": {"$in": wallet_ids}}, WALLET_TRANSACTIONS, user),
            {"_id": 0}).to_list(20000)
    vouchers_out = [t for t in txns if t["type"] == "Voucher" and t["direction"] == "Out"]
    topups = [t for t in txns if t["type"] in ("Topup", "Invoice_Receipt")]
    by_category: dict[str, int] = {}
    for t in vouchers_out:
        cat = t.get("narration") or "Uncategorized"
        by_category[cat] = by_category.get(cat, 0) + t["amount"]
    return {
        "project_id": project_id,
        "wallet_count": len(wallets),
        "petty_cash_out_paise": sum(t["amount"] for t in vouchers_out),
        "wallet_topups_paise": sum(t["amount"] for t in topups),
        "closing_cash_in_hand_paise": sum(w["current_balance"] for w in wallets),
        "petty_cash_by_category": [{"narration": k, "amount_paise": v} for k, v in by_category.items()],
    }
