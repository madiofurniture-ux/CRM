"""
Module loader — config-driven brand extensions on top of the canonical CRM.

Convention: a brand's `brand_id` (== tenancy.py's `tenant_id`) IS its module
folder name under backend/modules/. Onboarding a new brand is dropping a new
manifest.json there — no code change, no deploy of new code. See
docs/MODULES_ARCHITECTURE.md.

Every brand implicitly depends on `core_crm` (loaded first, then the brand's
own manifest layered on top) even if its manifest omits `depends`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

MODULES_DIR = Path(__file__).parent / "modules"
CORE_MODULE = "core_crm"


@lru_cache(maxsize=64)
def _read_manifest(module_name: str) -> dict | None:
    path = MODULES_DIR / module_name / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_custom_fields(base: dict, extra: dict) -> dict:
    out = {k: list(v) for k, v in base.items()}
    for entity, fields in (extra or {}).items():
        existing = {f["key"]: f for f in out.get(entity, [])}
        for f in fields:
            existing[f["key"]] = f  # brand overrides core on key collision
        out[entity] = list(existing.values())
    return out


@lru_cache(maxsize=256)
def load_brand_config(brand_id: str) -> dict:
    """Resolve a brand_id to its effective config: core_crm's manifest with
    the brand's own manifest layered on top. Falls back to core_crm alone
    for an unknown/blank brand_id — fail open to sane defaults, not a 500."""
    core = _read_manifest(CORE_MODULE) or {
        "custom_fields": {}, "pipelines": {}, "quotations": {"templates": []},
        "permissions": {"default_role": "user"},
    }
    brand = _read_manifest(brand_id) if brand_id and brand_id != CORE_MODULE else None
    if brand is None:
        return {
            "module": CORE_MODULE,
            "custom_fields": dict(core.get("custom_fields", {})),
            "pipelines": dict(core.get("pipelines", {})),
            "quotations": dict(core.get("quotations", {"templates": []})),
            "permissions": dict(core.get("permissions", {"default_role": "user"})),
        }
    return {
        "module": brand.get("name", brand_id),
        "custom_fields": _merge_custom_fields(core.get("custom_fields", {}), brand.get("custom_fields", {})),
        "pipelines": {**core.get("pipelines", {}), **brand.get("pipelines", {})},
        "quotations": {**core.get("quotations", {}), **brand.get("quotations", {})},
        "permissions": {**core.get("permissions", {}), **brand.get("permissions", {})},
    }


def custom_fields_for(brand_id: str, entity: str) -> list[dict]:
    return load_brand_config(brand_id).get("custom_fields", {}).get(entity, [])


def pipeline_for(brand_id: str, entity: str, fallback: list[str]) -> list[str]:
    return load_brand_config(brand_id).get("pipelines", {}).get(entity) or fallback


def quotation_templates_for(brand_id: str) -> list[str]:
    return load_brand_config(brand_id).get("quotations", {}).get("templates", [])


def available_brands() -> list[str]:
    """Every onboarded brand — one manifest folder per brand, minus core_crm."""
    if not MODULES_DIR.is_dir():
        return []
    return sorted(
        p.name for p in MODULES_DIR.iterdir()
        if p.is_dir() and p.name != CORE_MODULE and (p / "manifest.json").is_file()
    )
