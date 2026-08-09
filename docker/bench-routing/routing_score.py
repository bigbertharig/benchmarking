#!/usr/bin/env python3
"""Cost-aware routing score primitives."""

from __future__ import annotations

from typing import Any


def index_tiers(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tiers = config.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("routing config must contain a non-empty tiers array")
    indexed: dict[str, dict[str, Any]] = {}
    for tier in tiers:
        tier_id = str(tier.get("id", ""))
        if not tier_id or tier_id in indexed:
            raise ValueError(f"invalid or duplicate tier id: {tier_id}")
        rank = tier.get("capability_rank")
        cost = tier.get("cost_units")
        if not isinstance(rank, int) or not isinstance(cost, (int, float)) or cost <= 0:
            raise ValueError(f"tier {tier_id} requires integer capability_rank and positive cost_units")
        indexed[tier_id] = tier
    return indexed


def score_route(case: dict[str, Any], selected_tier: str, tiers: dict[str, dict[str, Any]]) -> dict[str, float]:
    chosen = tiers.get(selected_tier)
    minimum = tiers.get(str(case.get("minimum_tier", "")))
    if minimum is None:
        raise ValueError(f"case {case.get('id')} references an unknown minimum tier")
    requires_human = bool(case.get("requires_human"))
    if chosen is None:
        return {"task_success": 0.0, "routing_efficiency": 0.0, "routing_value": 0.0}
    if requires_human:
        success = selected_tier == "human_escalation"
    else:
        success = int(chosen["capability_rank"]) >= int(minimum["capability_rank"])
    efficiency = float(minimum["cost_units"]) / float(chosen["cost_units"]) if success else 0.0
    efficiency = min(1.0, efficiency)
    return {
        "task_success": float(success),
        "routing_efficiency": efficiency,
        "routing_value": float(success) * efficiency,
    }
