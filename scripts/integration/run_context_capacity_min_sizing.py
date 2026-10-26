#!/usr/bin/env python3
"""Load each model at the manager's minimum context after maximum sizing."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import capacity_run as capacity
import run_context_capacity_matrix as depth
import run_context_capacity_sizing as sizing

ROOT = Path(__file__).resolve().parents[2]
MAX_OUTPUT = ROOT / "results/context_capacity_sizing_20261026"
OUTPUT = ROOT / "results/context_capacity_min_sizing_20261026"
DEPTH_RUN = ROOT / "scripts/integration/run_context_capacity_matrix.py"
DEPTH_OUTPUT = ROOT / "results/context_capacity_validated_depth_20261026"


def run_case(case: dict, max_ctx: int) -> dict:
    model, gpus = case["model"], case["gpus"]
    result = {"case": case, "max_validated_ctx": max_ctx, "started_at": sizing.stamp(),
              "min_fit": None, "load": None, "unload": None, "error": None}
    rc, plan = sizing.fit(model, gpus, "min")
    result["min_fit"] = plan
    if rc or plan.get("fits") is not True or plan.get("gpus") != gpus:
        result["error"] = f"manager minimum fit failed or changed GPUs: {plan.get('reason') or plan.get('error')}"
        result["finished_at"] = sizing.stamp()
        return result
    ctx = int(plan["ctx"])
    result["suggested_min_ctx"] = ctx
    if ctx > max_ctx:
        result["error"] = f"manager minimum {ctx} exceeds validated compact maximum {max_ctx}"
        result["finished_at"] = sizing.stamp()
        return result
    owner = "capacity-min-" + case["id"]
    profile = None
    try:
        t0 = time.monotonic()
        rc, loaded = capacity.rigctl(*capacity.load_args(model, gpus, ctx, owner, None))
        result["load"] = {"returncode": rc, "seconds": round(time.monotonic() - t0, 1),
                          "response": loaded}
        if rc or loaded.get("state") != "ready":
            result["error"] = f"minimum load failed: {loaded.get('error') or loaded}"
            return result
        profile = loaded["profile"]
        if int(loaded.get("ctx") or -1) != ctx:
            result["error"] = f"loaded context {loaded.get('ctx')} differs from min suggestion {ctx}"
        if loaded.get("gpus") and loaded["gpus"] != gpus:
            result["error"] = f"loaded GPUs {loaded['gpus']} differ from {gpus}"
        measured = loaded.get("measured") or {}
        if not measured:
            result["error"] = "load ready but missing measured runtime allocation"
        elif measured.get("layers") is not None and measured.get("offloaded") != measured.get("layers"):
            result["error"] = f"partial offload: {measured.get('offloaded')}/{measured.get('layers')} layers"
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if profile:
            try:
                rc, unloaded = capacity.rigctl("unload", profile, timeout=900)
                result["unload"] = {"returncode": rc, "response": unloaded}
                if rc and not result["error"]:
                    result["error"] = f"unload failed: {unloaded}"
            except BaseException as exc:
                result["unload"] = {"error": f"{type(exc).__name__}: {exc}"}
                if not result["error"]:
                    result["error"] = "unload command failed"
        else:
            capacity.rigctl("cancel-owner", owner, "--reason", "minimum sizing cleanup", timeout=900)
        result["finished_at"] = sizing.stamp()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=MAX_OUTPUT / "validated_manifest.json")
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()
    max_terminal = json.loads((MAX_OUTPUT / "terminal.json").read_text(encoding="utf-8"))
    if max_terminal.get("failed") or max_terminal.get("passed") != max_terminal.get("cases"):
        raise RuntimeError("maximum sizing has not passed all cases")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    compact = [c for c in manifest["cases"] if c["target"] == "compact"]
    if len(compact) != len(manifest["models"]):
        raise RuntimeError(f"expected one compact case per model, got {len(compact)}")
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "checkpoint.json"
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {
        "run": "context-capacity-min-sizing-20261026", "started_at": sizing.stamp(), "cases": {}}
    if state["run"] != "context-capacity-min-sizing-20261026":
        raise RuntimeError("minimum sizing checkpoint belongs to another run")
    depth.hardware_check(manifest["hardware"])
    for n, case in enumerate(compact, 1):
        old = state["cases"].get(case["id"]) or {}
        if old.get("status") in ("passed", "failed") and old.get("result"):
            continue
        depth.hardware_check(manifest["hardware"])
        state["cases"][case["id"]] = {"status": "running", "started_at": sizing.stamp()}
        sizing.write_json(checkpoint, state)
        print(f"[{n}/{len(compact)}] minimum {case['id']} GPUs {case['gpus']}", flush=True)
        result = run_case(case, int(case["ctx"]))
        status = "failed" if result["error"] else "passed"
        state["cases"][case["id"]] = {"status": status, "result": result,
                                     "finished_at": sizing.stamp()}
        sizing.write_json(args.output / "receipts" / (case["id"] + ".json"), result)
        sizing.write_json(checkpoint, state)
        print(f"[{n}/{len(compact)}] {status}: min ctx {result.get('suggested_min_ctx')} "
              f"load {(result.get('load') or {}).get('seconds')}s {result['error'] or ''}", flush=True)
    state["finished_at"] = sizing.stamp()
    sizing.write_json(checkpoint, state)
    failed = [cid for cid, row in state["cases"].items() if row["status"] != "passed"]
    terminal = {"run": state["run"], "finished_at": sizing.stamp(), "cases": len(compact),
                "passed": len(state["cases"]) - len(failed), "failed": failed,
                "depth_started": False}
    if not failed and len(state["cases"]) == len(compact):
        # Publish the passed gate before scheduling depth: rigctl may launch it immediately.
        sizing.write_json(args.output / "terminal.json", terminal)
        command = ["run-start", "--run", "context-capacity-validated-depth-after-min-20261026",
                   "--auto-resume", "--cwd", str(ROOT),
                   "--note", "Depth probes after max and min load-only sizing passed", "--",
                   sys.executable, str(DEPTH_RUN), "--manifest", str(args.manifest),
                   "--output", str(DEPTH_OUTPUT)]
        rc, launched = capacity.rigctl(*command, timeout=900)
        terminal["depth_start_response"] = launched
        terminal["depth_started"] = rc == 0
        if rc:
            terminal["error"] = "validated depth run could not be scheduled"
    else:
        terminal["error"] = "minimum sizing failed or incomplete; depth held for correction"
    sizing.write_json(args.output / "terminal.json", terminal)
    print(json.dumps(terminal), flush=True)
    return 0 if terminal["depth_started"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
