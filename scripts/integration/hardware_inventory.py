"""Live rig GPU inventory for benchmark admission and UUID-stable Docker selection."""
from __future__ import annotations

import subprocess
from pathlib import Path

POWER_CHECK = Path("/home/bryan/llm_orchestration/shared/scripts/rig/hw_power.py")


def scan_cards() -> dict[int, dict]:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.used,power.limit",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10, check=True)
    cards = {}
    for line in result.stdout.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if len(fields) != 6:
            raise RuntimeError(f"invalid GPU inventory row: {line}")
        index, uuid, name, total, used, power = fields
        try:
            gpu = int(index)
            card = {"uuid": uuid, "name": name, "total_mib": int(total),
                    "used_mib": int(used), "power_limit_w": float(power)}
        except ValueError as exc:
            raise RuntimeError(f"invalid GPU inventory row: {line}") from exc
        if gpu < 0 or gpu in cards or not uuid.startswith("GPU-"):
            raise RuntimeError(f"invalid or duplicate GPU ID/UUID: {line}")
        cards[gpu] = card
    if not cards:
        raise RuntimeError("nvidia-smi reported no GPUs")
    return cards


def require_ids(gpus, cards: dict[int, dict]) -> None:
    requested = set(gpus)
    absent = requested - cards.keys()
    if absent:
        raise RuntimeError(f"GPU IDs absent from live inventory: {sorted(absent)}; detected {sorted(cards)}")


def docker_devices(gpus, cards: dict[int, dict]) -> str:
    """Docker --gpus argument; UUIDs avoid CUDA ordinal versus nvidia-smi index drift."""
    selected = list(gpus)
    require_ids(selected, cards)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Docker GPU selection needs distinct GPU IDs")
    return '"device=' + ",".join(cards[gpu]["uuid"] for gpu in selected) + '"'


def check_planned_power(gpus) -> None:
    selected = sorted(set(gpus))
    if not selected:
        return
    result = subprocess.run(
        ["python3", str(POWER_CHECK), "check", "--gpus", ",".join(map(str, selected))],
        capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError("GPU power caps differ from discovered card plan: "
                           + (result.stderr or result.stdout).strip())
