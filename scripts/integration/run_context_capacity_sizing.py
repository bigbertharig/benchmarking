#!/usr/bin/env python3
"""Verify manager compact/ceiling sizing by fit and load/unload before depth probes."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import capacity_run as capacity
import run_context_capacity_matrix as depth

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "campaigns/context_capacity_matrix_20261026.json"
OUTPUT = ROOT / "results/context_capacity_sizing_20261026"
DEPTH_RUN = ROOT / "scripts/integration/run_context_capacity_matrix.py"


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def fit(model: str, gpus: list[int], mode: str) -> tuple[int, dict]:
    return capacity.rigctl("fit", model, "--use", "chat", "--profile", "default",
                           "--gpus", ",".join(map(str, gpus)), "--context-mode", mode, "--json")


def check_case(case: dict) -> dict:
    result = {"case": case, "started_at": stamp(), "min_fit": None, "max_fit": None,
              "load": None, "unload": None, "error": None}
    model, gpus = case["model"], case["gpus"]
    for mode in ("min", "max"):
        rc, plan = fit(model, gpus, mode)
        result[mode + "_fit"] = plan
        if rc or plan.get("fits") is not True:
            result["error"] = f"manager {mode} fit failed: {plan.get('reason') or plan.get('error')}"
            result["finished_at"] = stamp()
            return result
        if plan.get("gpus") != gpus:
            result["error"] = f"manager {mode} fit changed GPUs: {plan.get('gpus')}"
            result["finished_at"] = stamp()
            return result

    ctx = int(result["max_fit"]["ctx"])
    trained = int(case["trained_ctx"])
    if ctx > trained:
        result["error"] = f"manager max {ctx} exceeds trained ceiling {trained}"
        result["finished_at"] = stamp()
        return result
    result["suggested_ctx"] = ctx
    result["planned_ctx"] = case["ctx"]
    result["plan_delta"] = ctx - int(case["ctx"])
    result["reaches_trained"] = ctx == trained
    owner = "capacity-sizing-" + case["id"]
    profile = None
    try:
        t0 = time.monotonic()
        rc, loaded = capacity.rigctl(*capacity.load_args(model, gpus, ctx, owner, None))
        seconds = round(time.monotonic() - t0, 1)
        result["load"] = {"returncode": rc, "seconds": seconds, "response": loaded}
        if rc or loaded.get("state") != "ready":
            result["error"] = f"load failed: {loaded.get('error') or loaded}"
            return result
        profile = loaded["profile"]
        if int(loaded.get("ctx") or -1) != ctx:
            result["error"] = f"loaded context {loaded.get('ctx')} differs from manager suggestion {ctx}"
        if loaded.get("gpus") and loaded["gpus"] != gpus:
            result["error"] = f"loaded GPU set {loaded['gpus']} differs from {gpus}"
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
            capacity.rigctl("cancel-owner", owner, "--reason", "sizing load cleanup", timeout=900)
        result["finished_at"] = stamp()
    return result


def validated_manifest(manifest: dict, state: dict, output: Path) -> Path:
    valid = []
    for case in manifest["cases"]:
        row = state["cases"][case["id"]]
        actual = dict(case)
        actual["ctx"] = row["result"]["suggested_ctx"]
        actual["sizing_receipt"] = str(output / "receipts" / (case["id"] + ".json"))
        if actual["ctx"] < actual["trained_ctx"] and actual["target"] == "trained_ceiling":
            actual["target"] = "frontier"
        valid.append(actual)
    doc = dict(manifest)
    doc["id"] = "context-capacity-validated-20261026"
    doc["method"] = "Each fixed context passed manager min/max fit, load, full GPU offload, and unload in sizing receipts."
    doc["cases"] = valid
    path = output / "validated_manifest.json"
    write_json(path, doc)
    return path


def report(manifest: dict, state: dict, output: Path) -> None:
    rows = ["# Context sizing pass", "",
            "Manager min/max fit and load/unload checks. No chat or recall probes.",
            "The compact case uses the fewest selected preferred-pool GPUs; max is the largest manager-suggested context on that set.",
            "The ceiling/frontier case uses the selected larger GPU set. Model library changes require depth validation.",
            "",
            "| Model | Target | GPUs | Planned ctx | Suggested ctx | Load s | Full offload | Status |",
            "|---|---|---|---:|---:|---:|---|---|"]
    for case in manifest["cases"]:
        row = state["cases"].get(case["id"], {})
        r = row.get("result") or {}
        measured = ((r.get("load") or {}).get("response") or {}).get("measured") or {}
        full = str(measured.get("offloaded")) + "/" + str(measured.get("layers")) if measured else "—"
        rows.append(f"| {case['model']} | {case['target']} | {','.join(map(str,case['gpus']))} | "
                    f"{case['ctx']} | {r.get('suggested_ctx','—')} | "
                    f"{(r.get('load') or {}).get('seconds','—')} | {full} | {row.get('status','pending')} |")
    (output / "SUMMARY.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--output", type=Path, default=OUTPUT)
    ap.add_argument("--limit", type=int, default=0, help="startup validation only; never chain depth")
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / "checkpoint.json"
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {
        "run": "context-capacity-sizing-20261026", "started_at": stamp(), "cases": {}}
    if state["run"] != "context-capacity-sizing-20261026":
        raise RuntimeError("checkpoint belongs to another run")
    depth.hardware_check(manifest["hardware"])
    for n, case in enumerate(manifest["cases"], 1):
        if args.limit and n > args.limit:
            break
        old = state["cases"].get(case["id"]) or {}
        if old.get("status") in ("passed", "failed") and old.get("result"):
            continue
        depth.hardware_check(manifest["hardware"])
        state["cases"][case["id"]] = {"status": "running", "started_at": stamp()}
        write_json(checkpoint, state)
        print(f"[{n}/{len(manifest['cases'])}] {case['id']} GPUs {case['gpus']}", flush=True)
        result = check_case(case)
        status = "failed" if result["error"] else "passed"
        state["cases"][case["id"]] = {"status": status, "result": result, "finished_at": stamp()}
        write_json(output / "receipts" / (case["id"] + ".json"), result)
        write_json(checkpoint, state)
        print(f"[{n}/{len(manifest['cases'])}] {status}: ctx {result.get('suggested_ctx')} "
              f"load {(result.get('load') or {}).get('seconds')}s {result['error'] or ''}", flush=True)
    report(manifest, state, output)
    if args.limit:
        return 0
    state["finished_at"] = stamp()
    write_json(checkpoint, state)
    failures = [cid for cid, r in state["cases"].items() if r["status"] != "passed"]
    terminal = {"run": state["run"], "finished_at": stamp(), "passed": len(state["cases"]) - len(failures),
                "failed": failures, "cases": len(manifest["cases"]), "depth_started": False}
    if not failures and len(state["cases"]) == len(manifest["cases"]):
        valid = validated_manifest(manifest, state, output)
        out2 = ROOT / "results/context_capacity_validated_depth_20261026"
        command = ["run-start", "--run", "context-capacity-validated-depth-20261026",
                   "--auto-resume", "--cwd", str(ROOT),
                   "--note", "Depth probes after all compact and ceiling sizing loads passed", "--",
                   sys.executable, str(DEPTH_RUN), "--manifest", str(valid), "--output", str(out2)]
        rc, launch = capacity.rigctl(*command, timeout=900)
        terminal["depth_start_response"] = launch
        terminal["depth_started"] = rc == 0
        if rc:
            terminal["error"] = "validated depth run could not be scheduled"
    else:
        terminal["error"] = "sizing incomplete or failed; depth held for correction"
    write_json(output / "terminal.json", terminal)
    print(json.dumps(terminal), flush=True)
    return 0 if terminal["depth_started"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
