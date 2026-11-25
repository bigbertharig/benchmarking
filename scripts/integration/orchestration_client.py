"""Consumer of installed Orchestration CLI contracts; no sibling imports or fallback."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess


def request(arguments: list[str], schema: str) -> dict:
    try:
        command = json.loads(os.environ.get("BENCHMARK_ORCHESTRATION_COMMAND", '["rig"]'))
    except ValueError as exc:
        raise RuntimeError("BENCHMARK_ORCHESTRATION_COMMAND must be a JSON argv array") from exc
    if (not isinstance(command, list) or not command
            or any(not isinstance(x, str) or not x or "\x00" in x for x in command)):
        raise RuntimeError("BENCHMARK_ORCHESTRATION_COMMAND must be a nonempty JSON argv array")
    try:
        result = subprocess.run([*command, "inspect", *arguments], capture_output=True,
                                text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Orchestration inspection unavailable ({type(exc).__name__}); no fallback") from exc
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError("Orchestration returned invalid JSON") from exc
    if (not isinstance(payload, dict) or payload.get("schema") != schema
            or type(payload.get("ok")) is not bool):
        raise RuntimeError("Orchestration returned an unsupported inspection contract")
    if result.returncode or not payload["ok"]:
        kind = payload.get("kind", "command_failed")
        error = str(payload.get("error", "inspection failed"))[:1000]
        raise RuntimeError(f"Orchestration inspection refused ({kind}): {error}")
    return payload


def check_power(gpus) -> None:
    selected = list(gpus)
    if not selected or any(type(g) is not int or g < 0 for g in selected) or len(set(selected)) != len(selected):
        raise ValueError("Power check needs distinct nonnegative GPU IDs")
    selected.sort()
    payload = request(["power", "--gpus", ",".join(map(str, selected))], "rig-power-check/1")
    rows = payload.get("checks")
    if (payload.get("gpu_ids") != selected or not isinstance(rows, list)
            or len(rows) != len(selected)):
        raise RuntimeError("Orchestration returned incomplete power-check coverage")
    for gpu, row in zip(selected, rows):
        if not isinstance(row, dict) or type(row.get("gpu_id")) is not int or row["gpu_id"] != gpu:
            raise RuntimeError("Orchestration returned mismatched GPU identity")
        values = [row.get("actual_w"), row.get("planned_w")]
        if (row.get("matches") is not True
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values)
                or abs(values[0] - values[1]) >= 0.5):
            raise RuntimeError("Orchestration returned invalid power-check evidence")


def resolve_model_path(path: str) -> str:
    payload = request(["model-path", "--path", path], "rig-model-path/1")
    resolved = payload.get("resolved_path")
    if (payload.get("requested_path") != path or not isinstance(resolved, str)
            or not Path(resolved).is_absolute()):
        raise RuntimeError("Orchestration returned invalid model-path identity")
    return resolved
