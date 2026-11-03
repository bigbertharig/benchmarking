#!/usr/bin/env python3
"""Run a bounded Qwen3.6 expert-VRAM sweep under one manager GPU lease."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state = {"started_at": stamp(), "status": "running", "cases": []}
    write(args.output / "checkpoint.json", state)
    probe = Path(__file__).with_name("run_strata_qwen36_probe.py")
    for budget in (16, 8, 0):
        name = f"expert_vram_{budget}gib"
        child = args.output / name
        cmd = ["/usr/bin/python3", str(probe), "--output", str(child),
               "--expert-vram", str(budget)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        (args.output / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (args.output / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        row = {"expert_vram_gib": budget, "exit_code": result.returncode,
               "terminal": str(child / "terminal.json")}
        if (child / "terminal.json").is_file():
            terminal = json.loads((child / "terminal.json").read_text())
            row["status"] = terminal.get("status")
            row["gpu_loaded_mib"] = terminal.get("gpu_loaded_mib")
            host = terminal.get("host_loaded", {})
            row["mem_available_kib"] = host.get("MemAvailable_kib")
            before = terminal.get("host_before", {})
            if "SwapFree_kib" in host and "SwapFree_kib" in before:
                row["swap_free_drop_kib"] = before["SwapFree_kib"] - host["SwapFree_kib"]
            row["request_wall_seconds"] = [r["wall_seconds"] for r in terminal.get("requests", [])]
            row["nvme_request_read_bytes"] = [
                r["nvme_after"]["read_bytes"] - r["nvme_before"]["read_bytes"]
                for r in terminal.get("requests", [])]
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
    state["status"] = "passed" if len(state["cases"]) == 3 and not state.get("stop_reason") else "stopped"
    write(args.output / "terminal.json", state)
    print(f"Strata sweep: {state['status']} {state.get('stop_reason', '')}", flush=True)
    return 0 if state["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
