#!/usr/bin/env python3
"""Bounded, GPU-free host RAM headroom probe for the rig."""
from __future__ import annotations

import argparse
import json
import mmap
import os
from datetime import datetime, timezone
from pathlib import Path


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def meminfo() -> dict[str, int]:
    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "Cached"}
    result = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, _, value = line.partition(":")
        if name in wanted:
            result[name + "_kib"] = int(value.split()[0])
    return result


def save(path: Path, state: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    os.replace(temporary, path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--target-gib", type=float, default=26)
    ap.add_argument("--target-gb-decimal", type=float,
                    help="override target using decimal GB (1 GB = 1,000,000,000 bytes)")
    ap.add_argument("--min-available-gib", type=float, default=4)
    ap.add_argument("--step-mib", type=int, default=256)
    args = ap.parse_args()
    if args.step_mib <= 0 or args.min_available_gib < 3:
        ap.error("positive step and at least 3 GiB guard headroom required")
    args.output.mkdir(parents=True, exist_ok=True)
    before = meminfo()
    target = (int(args.target_gb_decimal * 1_000_000_000)
              if args.target_gb_decimal is not None else int(args.target_gib * 1024**3))
    state = {"started_at": stamp(), "status": "running",
             "target_gib": round(target / 1024**3, 4),
             "target_gb_decimal": args.target_gb_decimal, "target_bytes": target,
             "min_available_gib": args.min_available_gib, "step_mib": args.step_mib,
             "accounting_reserve_gib": 1,
             "before": before, "samples": []}
    save(args.output / "checkpoint.json", state)
    blocks = []
    allocated = 0
    step = args.step_mib * 1024**2
    floor = int(args.min_available_gib * 1024**2)
    try:
        if before["MemAvailable_kib"] * 1024 < floor + step:
            raise RuntimeError("insufficient idle memory for a safe first step")
        while allocated < target:
            current = meminfo()
            remaining = min(step, target - allocated)
            conservative_available = min(current["MemAvailable_kib"] * 1024,
                                         before["MemAvailable_kib"] * 1024
                                         - allocated - 1024**3)
            if conservative_available < floor + remaining:
                state["status"] = "headroom_stop"
                state["stop_reason"] = "next allocation could cross minimum MemAvailable"
                break
            if before["SwapFree_kib"] - current["SwapFree_kib"] > 256 * 1024:
                state["status"] = "swap_stop"
                state["stop_reason"] = "swap use grew by more than 256 MiB"
                break
            block = mmap.mmap(-1, remaining,
                              flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                              prot=mmap.PROT_READ | mmap.PROT_WRITE)
            for offset in range(0, remaining, 4096):
                block[offset:offset + 1] = b"x"
            blocks.append(block)
            allocated += remaining
            after = meminfo()
            state["samples"].append({"at": stamp(), "allocated_mib": allocated // 1024**2,
                                     "mem_available_mib": after["MemAvailable_kib"] // 1024,
                                     "swap_free_mib": after["SwapFree_kib"] // 1024})
            save(args.output / "checkpoint.json", state)
            if after["MemAvailable_kib"] * 1024 < floor:
                state["status"] = "headroom_stop"
                state["stop_reason"] = "measured MemAvailable reached minimum headroom"
                break
        else:
            state["status"] = "target_reached"
        state["max_allocated_mib"] = allocated // 1024**2
        state["peak_allocation_meminfo"] = meminfo()
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for block in reversed(blocks):
            block.close()
        state["after_release"] = meminfo()
        state["finished_at"] = stamp()
        save(args.output / "terminal.json", state)
        print(f"RAM budget probe: {state['status']}, {allocated // 1024**2} MiB touched", flush=True)
    return 0 if state["status"] in {"headroom_stop", "target_reached"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
