"""
Module loader for the Canonical CRM's brand extensions.

Each brand is one manifest in backend/modules/<brand_id>/manifest.json,
`depends`-ing on core_crm (and, in principle, on other modules). Adding a new
brand later is: drop a new manifest.json here, no code changes — this is
what keeps onboarding a brand low-cost/low-ops for the operator (see
docs/MODULES_ARCHITECTURE.md).
"""
from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

MODULES_DIR = Path(__file__).parent / "modules"


def list_brands() -> list[str]:
    """Every brand_id with a manifest on disk, excluding core_crm itself
    (core_crm is a dependency, not a selectable brand)."""
    if not MODULES_DIR.is_dir():
        return []
    return sorted(
        p.parent.name for p in MODULES_DIR.glob("*/manifest.json")
        if p.parent.name != "core_crm"
    )


@lru_cache(maxsize=64)
def _read_manifest(brand_id: str) -> dict:
    path = MODULES_DIR / brand_id / "manifest.json"
    if not path.is_file():
        raise ValueError(f"Unknown brand_id: {brand_id!r} (no manifest at {path})")
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_custom_fields(base: dict, extra: dict) -> dict:
    out = {k: list(v) for k, v in base.items()}
    for entity, fields in extra.items():
        out.setdefault(entity, [])
        existing_keys = {f["key"] for f in out[entity]}
        out[entity].extend(f for f in fields if f["key"] not in existing_keys)
    return out


def load_for_brand(brand_id: str) -> dict:
    """
    Merge core_crm with the given brand's manifest (brand overrides/extends
    core_crm; core_crm's pipeline stays if the brand doesn't define one).

    Returns: {"custom_fields": {entity: [field...]}, "pipelines": {entity:
    [stage...]}, "quotations": {...}, "permissions": {...}}.
    """
    core = _read_manifest("core_crm")
    brand = _read_manifest(brand_id)

    custom_fields = _merge_custom_fields(
        core.get("custom_fields", {}), brand.get("custom_fields", {}))
    pipelines = {**core.get("pipelines", {}), **brand.get("pipelines", {})}
    quotations = {**core.get("quotations", {}), **brand.get("quotations", {})}
    permissions = {**core.get("permissions", {}), **brand.get("permissions", {})}

    return {
        "brand_id": brand_id,
        "custom_fields": custom_fields,
        "pipelines": pipelines,
        "quotations": quotations,
        "permissions": permissions,
    }


def pipeline_for(brand_id: str, entity: str) -> list[dict]:
    return load_for_brand(brand_id).get("pipelines", {}).get(entity, [])


def stage_keys(brand_id: str, entity: str) -> set[str]:
    return {s["key"] for s in pipeline_for(brand_id, entity)}


def won_stage(brand_id: str, entity: str) -> dict | None:
    return next((s for s in pipeline_for(brand_id, entity) if s.get("won")), None)


def lost_stage(brand_id: str, entity: str) -> dict | None:
    return next(
        (s for s in pipeline_for(brand_id, entity) if s.get("terminal") and not s.get("won")),
        None)
