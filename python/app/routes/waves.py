"""
Wave management endpoints — create, list, release waves and manage rules.

POST /api/wes/waves          — create wave manually or auto-generate
GET  /api/wes/waves          — list waves with status
POST /api/wes/waves/{id}/release — release wave → generate tasks
POST /api/wes/wave-rules     — create a wave rule
GET  /api/wes/wave-rules     — list wave rules

Phase 4: Wave Rule Engine.
"""

import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/wes", tags=["wes-waves"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_wave_engine():
    from app.main import app_state
    return app_state.get("wes_wave_engine")


def _get_task_generator():
    from app.main import app_state
    return app_state.get("wes_task_generator")



# ── Pydantic models ──────────────────────────────────────


class WaveCreate(BaseModel):
    order_ids: list[str] = Field(..., min_length=1, description="Order IDs to include")
    zone_affinity: Optional[str] = None
    max_robots: int = Field(default=5, ge=1, le=50)


class WaveRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    conditions: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


# ── Wave endpoints ───────────────────────────────────────


@router.post("/waves")
async def create_or_auto_wave(body: Optional[WaveCreate] = None):
    """
    Create a wave manually (if body has order_ids) or auto-generate from rules.

    Manual: POST with {"order_ids": ["id1", "id2", ...]}
    Auto:   POST with empty body or {} → uses active rules on pending orders
    """
    engine = _get_wave_engine()
    db = _get_db()

    if engine is None:
        raise HTTPException(status_code=503, detail="Wave engine not initialized")

    if body and body.order_ids:
        # Manual wave creation
        wave = engine.create_wave(
            order_ids=body.order_ids,
            zone_affinity=body.zone_affinity,
            max_robots=body.max_robots,
        )

        # Persist to MongoDB (graceful if unavailable)
        persisted = False
        if db is not None:
            try:
                await db["waves"].insert_one(dict(wave))
                persisted = True
            except Exception:
                pass

        return {"wave": _strip_id(wave), "mode": "manual", "persisted": persisted}

    else:
        # Auto-wave from rules + pending orders (exclude already-waved orders)
        pending_orders = []
        if db is not None:
            try:
                # Get order IDs already in pending/active waves
                existing_waves = await db["waves"].find(
                    {"status": {"$in": ["pending", "active"]}},
                    {"order_ids": 1, "_id": 0},
                ).to_list(length=10000)
                waved_ids = set()
                for w in existing_waves:
                    waved_ids.update(w.get("order_ids", []))

                # Only fetch truly pending, un-waved orders
                query = {"status": "pending"}
                if waved_ids:
                    query["order_id"] = {"$nin": list(waved_ids)}
                pending_orders = await db["orders"].find(
                    query, {"_id": 0}
                ).to_list(length=10000)
            except Exception:
                pending_orders = []

        waves = engine.auto_wave(pending_orders)

        # Persist waves (graceful)
        if db is not None and waves:
            try:
                for w in waves:
                    await db["waves"].insert_one(dict(w))
            except Exception:
                pass

        return {
            "waves": [_strip_id(w) for w in waves],
            "count": len(waves),
            "mode": "auto",
            "pending_orders_evaluated": len(pending_orders),
        }


@router.get("/waves")
async def list_waves():
    """List all waves with status."""
    db = _get_db()
    if db is None:
        return {"waves": [], "count": 0, "summary": {"pending": 0, "active": 0, "completed": 0}}

    try:
        waves = await db["waves"].find({}, {"_id": 0}).to_list(length=1000)
    except Exception:
        waves = []

    return {
        "waves": waves,
        "count": len(waves),
        "summary": {
            "pending": sum(1 for w in waves if w.get("status") == "pending"),
            "active": sum(1 for w in waves if w.get("status") == "active"),
            "completed": sum(1 for w in waves if w.get("status") == "completed"),
        },
    }


@router.post("/waves/{wave_id}/release")
async def release_wave(wave_id: str):
    """
    Release a pending wave — generates tasks from its orders.

    The wave transitions from 'pending' → 'active' and tasks are created
    for all orders in the wave.
    """
    engine = _get_wave_engine()
    task_gen = _get_task_generator()
    db = _get_db()

    if engine is None or task_gen is None:
        raise HTTPException(status_code=503, detail="Wave engine not initialized")

    # Load wave
    wave = None
    if db is not None:
        wave = await db["waves"].find_one({"wave_id": wave_id}, {"_id": 0})

    if wave is None:
        raise HTTPException(status_code=404, detail=f"Wave {wave_id} not found")

    if wave.get("status") != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Wave {wave_id} is {wave.get('status')}, not pending",
        )

    # Load orders for this wave
    orders = []
    if db is not None:
        order_ids = wave.get("order_ids", [])
        if order_ids:
            orders = await db["orders"].find(
                {"order_id": {"$in": order_ids}}, {"_id": 0}
            ).to_list(length=10000)

    # Release wave → generate tasks
    updated_wave, tasks = engine.release_wave(wave, orders, task_gen)

    # Persist updated wave + new tasks
    if db is not None:
        await db["waves"].update_one(
            {"wave_id": wave_id},
            {"$set": {
                "status": updated_wave["status"],
                "released_at": updated_wave["released_at"],
                "task_ids": updated_wave["task_ids"],
            }},
        )
        if tasks:
            await db["tasks"].insert_many([dict(t) for t in tasks])

        # Mark orders as "waved" to prevent duplicate task generation
        # and infinite re-waving
        order_ids = wave.get("order_ids", [])
        if order_ids:
            await db["orders"].update_many(
                {"order_id": {"$in": order_ids}},
                {"$set": {"status": "waved"}},
            )

    return {
        "wave_id": wave_id,
        "status": updated_wave["status"],
        "tasks_created": len(tasks),
        "task_ids": updated_wave["task_ids"],
    }


# ── Rule endpoints ───────────────────────────────────────


@router.post("/wave-rules")
async def create_wave_rule(body: WaveRuleCreate):
    """Create a new wave rule."""
    engine = _get_wave_engine()
    db = _get_db()

    if engine is None:
        raise HTTPException(status_code=503, detail="Wave engine not initialized")

    rule = engine.add_rule({
        "name": body.name,
        "conditions": body.conditions,
        "action": body.action,
        "enabled": body.enabled,
    })

    # Persist to MongoDB
    if db is not None:
        await db["wave_rules"].insert_one(dict(rule))

    return {"rule": _strip_id(rule)}


@router.get("/wave-rules")
async def list_wave_rules():
    """List all wave rules."""
    engine = _get_wave_engine()

    if engine is None:
        return {"rules": []}

    return {
        "rules": engine.get_rules(),
        "count": len(engine.get_rules()),
    }


# ── Helpers ──────────────────────────────────────────────


def _strip_id(doc: dict) -> dict:
    """Remove MongoDB _id field if present."""
    return {k: v for k, v in doc.items() if k != "_id"}
