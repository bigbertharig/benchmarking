#!/usr/bin/env python3
"""Sweep Qwen3.8 resident RAM budgets on one leased 3090."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state = {"started_at": stamp(), "status": "running", "cases": []}
    write(args.output / "checkpoint.json", state)
    probe = Path(__file__).with_name("run_strata_qwen38_probe.py")
    for budget in (12, 8, 4, 0.1):
        name = f"resident_budget_{str(budget).replace('.', 'p')}gib"
        child = args.output / name
        command = ["/usr/bin/python3", str(probe), "--output", str(child),
                   "--resident-budget-gib", str(budget)]
        result = subprocess.run(command, capture_output=True, text=True)
        (args.output / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (args.output / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        row = {"resident_budget_gib": budget, "exit_code": result.returncode,
               "terminal": str(child / "terminal.json")}
        if (child / "terminal.json").is_file():
            terminal = json.loads((child / "terminal.json").read_text())
            row["status"] = terminal.get("status")
            row["error"] = terminal.get("error")
            row["gpu_loaded_mib"] = terminal.get("gpu_loaded_mib")
            host = terminal.get("host_loaded", {})
            row["mem_available_kib"] = host.get("MemAvailable_kib")
            before = terminal.get("host_before", {})
            if "SwapFree_kib" in host and "SwapFree_kib" in before:
                row["swap_free_drop_kib"] = before["SwapFree_kib"] - host["SwapFree_kib"]
            requests = terminal.get("requests", [])
            row["request_wall_seconds"] = [item["wall_seconds"] for item in requests]
            row["nvme_request_read_bytes"] = [
                item["nvme_after"]["read_bytes"] - item["nvme_before"]["read_bytes"]
                for item in requests]
            row["engine_request_read_bytes"] = [
                item["engine_io_after"]["read_bytes"] - item["engine_io_before"]["read_bytes"]
                if item.get("engine_io_after") and item.get("engine_io_before") else None
                for item in requests]
        state["cases"].append(row)
        write(args.output / "checkpoint.json", state)
        if result.returncode:
            state["stop_reason"] = f"{name} failed"
            break
        if row.get("mem_available_kib", 0) < 6 * 1024 * 1024:
            state["stop_reason"] = f"{name} left less than 6 GiB MemAvailable"
            break
        if row.get("swap_free_drop_kib", 0) > 3 * 1024 * 1024:
            state["stop_reason"] = f"{name} reduced SwapFree by over 3 GiB"
            break
    state["finished_at"] = stamp()
    state["status"] = "passed" if len(state["cases"]) == 4 and not state.get("stop_reason") else "stopped"
    write(args.output / "terminal.json", state)
    print(f"Strata Qwen3.8 RAM sweep: {state['status']} {state.get('stop_reason', '')}".rstrip(), flush=True)
    return 0 if state["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
