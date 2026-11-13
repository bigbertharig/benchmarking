"""Freeze the rig's physical GPU inventory and benchmark role assignments per run.

The rig hardware layer owns discovery. Benchmarking consumes ``rig observe`` and
keeps an immutable selection receipt; live admission remains with the Manager.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
from pathlib import Path


TOKEN = re.compile(r"\{(gpu|uuid):([a-z][a-z0-9_]*)\}")


def scan() -> dict:
    result = subprocess.run(["rig", "observe"], capture_output=True, text=True,
                            timeout=30, check=True)
    return inventory(json.loads(result.stdout))


def inventory(observation: dict) -> dict:
    gpu_scan = observation.get("gpu_scan") or {}
    if not gpu_scan.get("ok"):
        raise RuntimeError(f"rig GPU scan failed: {gpu_scan.get('errors')}")
    cards = gpu_scan.get("cards") or []
    if not cards:
        raise RuntimeError("rig observe returned no GPU cards")
    by_id = {}
    uuids = set()
    for card in cards:
        index, uuid = card.get("index"), card.get("uuid")
        if (type(index) is not int or index < 0 or not isinstance(uuid, str)
                or not uuid.startswith("GPU-") or index in by_id or uuid in uuids
                or not isinstance(card.get("total_mb"), int) or card["total_mb"] < 1):
            raise RuntimeError(f"invalid or duplicate rig GPU card: {card}")
        by_id[index] = dict(card)
        uuids.add(uuid)
    held = set()
    for entry in [*(observation.get("claims") or []), *(observation.get("leases") or [])]:
        held.update(entry.get("gpu_ids") or [])
    usage = {row["index"]: row.get("used_mb", 0) for row in observation.get("gpus") or []
             if type(row.get("index")) is int}
    return {"schema": 1, "source": "rig observe", "rig_host": socket.gethostname(),
            "observed_at": observation.get("observed_at"),
            "cards": [by_id[i] for i in sorted(by_id)], "held_gpu_ids": sorted(held),
            "used_mb": {str(i): usage.get(i) for i in sorted(by_id)},
            "roles": {}}


def assign_roles(snapshot: dict, roles: dict) -> dict:
    if not isinstance(roles, dict):
        raise ValueError("hardware_roles must be an object")
    assigned = {}
    selected = set()
    for role, spec in roles.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", role) or not isinstance(spec, dict):
            raise ValueError(f"invalid hardware role: {role}")
        allowed = {"min_vram_mb", "max_vram_mb", "name_contains", "prefer", "available_only"}
        if set(spec) - allowed:
            raise ValueError(f"{role}: unknown selectors {sorted(set(spec) - allowed)}")
        low, high = spec.get("min_vram_mb", 1), spec.get("max_vram_mb", 2**63)
        prefer = spec.get("prefer", "most_vram")
        if (type(low) is not int or type(high) is not int or low < 1 or high < low
                or prefer not in ("most_vram", "least_vram")
                or type(spec.get("available_only", False)) is not bool
                or not isinstance(spec.get("name_contains", ""), str)):
            raise ValueError(f"{role}: invalid hardware selector")
        candidates = [card for card in snapshot["cards"]
                      if low <= card["total_mb"] <= high
                      and spec.get("name_contains", "").casefold() in card.get("name", "").casefold()
                      and card["index"] not in selected
                      and (not spec.get("available_only", False)
                           or (card["index"] not in snapshot["held_gpu_ids"]
                               and (snapshot["used_mb"].get(str(card["index"])) or 0) < 1000))]
        candidates.sort(key=lambda c: ((-1 if prefer == "most_vram" else 1) * c["total_mb"],
                                       c.get("bus") or "", c["uuid"]))
        if not candidates:
            raise RuntimeError(f"{role}: no GPU matches selector {spec}")
        card = candidates[0]
        assigned[role] = {"index": card["index"], "uuid": card["uuid"],
                          "bus": card.get("bus"), "name": card.get("name")}
        selected.add(card["index"])
    snapshot["roles"] = assigned
    return snapshot


def expand(value, roles: dict):
    """Resolve {gpu:role} and {uuid:role} in command/env/output strings."""
    if isinstance(value, str):
        def replace(match):
            role = match.group(2)
            if role not in roles:
                raise ValueError(f"unknown hardware role: {role}")
            return str(roles[role]["index" if match.group(1) == "gpu" else "uuid"])
        return TOKEN.sub(replace, value)
    if isinstance(value, list):
        return [expand(item, roles) for item in value]
    if isinstance(value, dict):
        return {key: expand(item, roles) for key, item in value.items()}
    return value


def verify_saved(saved: dict, current: dict, requested_ids: set[int]) -> None:
    if saved.get("rig_host") != current.get("rig_host"):
        raise RuntimeError("benchmark session moved to another rig; use a new run ID")
    previous = {card["index"]: card for card in saved["cards"]}
    now = {card["index"]: card for card in current["cards"]}
    for index in requested_ids:
        before, after = previous.get(index), now.get(index)
        if not before or not after or (before["uuid"], before.get("bus")) != (after["uuid"], after.get("bus")):
            raise RuntimeError(f"GPU {index} changed since this session began; use a new run ID")


def load_snapshot(path: Path) -> dict:
    saved = json.loads(path.read_text())
    if saved.get("schema") != 1 or saved.get("source") != "rig observe":
        raise RuntimeError(f"unsupported session hardware receipt: {path}")
    return saved
