#!/usr/bin/env python3
"""Run a checkpointed, sequential capacity matrix through the existing managed capacity runner.

Each case loads one model, probes short output and 10%/90% depth recall, and unloads.
Run as a rigctl run-start job. Re-running skips completed cases and retries only an
interrupted case. The summary reports observations; it does not promote profiles.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPACITY = ROOT / "scripts" / "integration" / "capacity_run.py"
DEFAULT_MANIFEST = ROOT / "campaigns" / "context_capacity_matrix_20261026.json"
DEFAULT_OUTPUT = ROOT / "results" / "context_capacity_matrix_20261026"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def hardware_check(expected: dict) -> None:
    cmd = ["nvidia-smi", "--query-gpu=index,name,memory.total,power.limit",
           "--format=csv,noheader,nounits"]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    cards = {}
    for line in out.splitlines():
        fields = [v.strip() for v in line.split(",")]
        if len(fields) != 4:
            raise RuntimeError(f"unexpected nvidia-smi row: {line}")
        cards[int(fields[0])] = (fields[1], int(fields[2]), float(fields[3]))
    required = set(expected["brain"] + expected["worker"])
    if set(cards) != required:
        raise RuntimeError(f"GPU indices changed: expected {sorted(required)}, got {sorted(cards)}")
    for index in expected["brain"]:
        name, memory, power = cards[index]
        if "3090" not in name or memory < 20000 or abs(power - expected["power_caps_w"][str(index)]) > 0.5:
            raise RuntimeError(f"brain GPU{index} identity/power cap changed: {cards[index]}")
    for index in expected["worker"]:
        name, memory, power = cards[index]
        if "1060" not in name or memory < 5800 or abs(power - expected["power_caps_w"][str(index)]) > 0.5:
            raise RuntimeError(f"worker GPU{index} identity/power cap changed: {cards[index]}")


def result_from_receipt(path: Path, rc: int) -> dict:
    result = {"returncode": rc, "receipt": str(path) if path.exists() else None,
              "recall_ok": None, "load_seconds": None, "error": None}
    if not path.exists():
        result["error"] = "capacity runner wrote no receipt; inspect case log"
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result["error"] = f"invalid capacity receipt: {exc}"
        return result
    probes = data.get("depth_probes") or []
    fractions = {round(float(p.get("target_fraction", -1)), 2) for p in probes}
    result["recall_ok"] = all(bool(p.get("recall_ok")) for p in probes) if probes else False
    result["load_seconds"] = (data.get("load") or {}).get("seconds")
    result["observed_ctx"] = (data.get("load") or {}).get("ctx_allocated")
    result["depth_fractions"] = sorted(fractions)
    if rc:
        result["error"] = data.get("error") or f"capacity runner exit {rc}"
    elif data.get("error"):
        result["error"] = data["error"]
    elif fractions != {0.1, 0.9}:
        result["error"] = f"missing depth probes: {sorted(fractions)}"
    elif not result["recall_ok"]:
        result["error"] = "one or more depth recall probes failed"
    return result


def run_case(case: dict, output: Path) -> dict:
    receipt = output / "receipts" / f"{case['id']}.json"
    log = output / "logs" / f"{case['id']}.log"
    cmd = [sys.executable, str(CAPACITY), case["model"], "--gpus",
           ",".join(map(str, case["gpus"])), "--ctx", str(case["ctx"]),
           "--fractions", "0.1,0.9", "--out", str(receipt)]
    with log.open("w", encoding="utf-8") as stream:
        stream.write("command: " + " ".join(cmd) + "\n")
        stream.flush()
        rc = subprocess.run(cmd, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
    result = result_from_receipt(receipt, rc)
    return {"case": case, "log": str(log), **result}


def summary(manifest: dict, state: dict, output: Path) -> str:
    lines = ["# Context capacity matrix results", "",
             f"Manifest: `{manifest['id']}`. Results as of {now()}.",
             "These are observed loads and 10%/90% recall probes, not automatic library promotions.", "",
             "| Model | Target | GPUs | Planned ctx | Observed ctx | Load s | Recall | Status |",
             "|---|---|---|---:|---:|---:|---|---|"]
    for case in manifest["cases"]:
        row = state["cases"].get(case["id"], {})
        result = row.get("result") or {}
        status = row.get("status", "pending")
        recall = ("pass" if result.get("recall_ok") is True else
                  "fail" if result.get("recall_ok") is False else "—")
        lines.append(f"| `{case['model']}` | {case['target']} | {','.join(map(str, case['gpus']))} | "
                     f"{case['ctx']} | {result.get('observed_ctx') or '—'} | "
                     f"{result.get('load_seconds') or '—'} | {recall} | {status} |")
    lines += ["", "Failed cases remain unpromoted; inspect their individual logs and receipts. "
              "A projected trained ceiling that fails to load needs a lower-context follow-up. "
              "Fast/slow paired speed tests are a separate step at the same context.", ""]
    path = output / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    output = args.output
    # The maximum-load job already schedules this command. Defer its depth probes
    # until the separate minimum-load pass has completed successfully.
    if manifest["id"] == "context-capacity-validated-20261026":
        min_terminal = ROOT / "results/context_capacity_min_sizing_20261026/terminal.json"
        if not min_terminal.exists():
            import capacity_run as capacity
            min_runner = ROOT / "scripts/integration/run_context_capacity_min_sizing.py"
            rc, launched = capacity.rigctl(
                "run-start", "--run", "context-capacity-min-sizing-20261026",
                "--auto-resume", "--cwd", str(ROOT),
                "--note", "Minimum-context loads after maximum sizing; depth held", "--",
                sys.executable, str(min_runner))
            atomic_json(output / "deferred_to_min.json",
                        {"at": now(), "min_run_started": rc == 0, "response": launched})
            print("depth deferred: starting minimum-context load pass", flush=True)
            return 0 if rc == 0 else 1
        min_result = json.loads(min_terminal.read_text(encoding="utf-8"))
        if min_result.get("failed") or min_result.get("passed") != min_result.get("cases"):
            print("depth held: minimum-context loads did not all pass", flush=True)
            return 1
    (output / "logs").mkdir(parents=True, exist_ok=True)
    (output / "receipts").mkdir(parents=True, exist_ok=True)
    state_path = output / "checkpoint.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "run": manifest["id"], "started_at": now(), "cases": {}}
    if state["run"] != manifest["id"]:
        raise RuntimeError(f"checkpoint belongs to {state['run']}, not {manifest['id']}")
    try:
        hardware_check(manifest["hardware"])
    except Exception as exc:
        state["preflight_error"] = str(exc)
        state["finished_at"] = now()
        atomic_json(state_path, state)
        atomic_json(output / "terminal.json", {"run": manifest["id"], "status": "failed",
                                                "finished_at": now(), "error": str(exc)})
        print(f"preflight failed: {exc}", flush=True)
        return 1
    for index, case in enumerate(manifest["cases"], 1):
        old = state["cases"].get(case["id"], {})
        if old.get("status") in ("passed", "failed") and old.get("result"):
            continue
        try:
            hardware_check(manifest["hardware"])  # keep the requested power caps throughout the campaign
        except Exception as exc:
            state["preflight_error"] = str(exc)
            state["finished_at"] = now()
            atomic_json(state_path, state)
            atomic_json(output / "terminal.json", {"run": manifest["id"], "status": "failed",
                                                    "finished_at": now(), "error": str(exc)})
            print(f"preflight failed before {case['id']}: {exc}", flush=True)
            return 1
        state["cases"][case["id"]] = {"status": "running", "started_at": now()}
        atomic_json(state_path, state)
        print(f"[{index}/{len(manifest['cases'])}] {case['id']} GPU {case['gpus']} ctx {case['ctx']}",
              flush=True)
        try:
            result = run_case(case, output)
        except Exception as exc:
            result = {"case": case, "error": f"runner error: {type(exc).__name__}: {exc}",
                      "returncode": None, "receipt": None, "log": None, "recall_ok": None}
        status = "failed" if result["error"] else "passed"
        state["cases"][case["id"]] = {"status": status, "started_at": state["cases"][case["id"]]["started_at"],
                                      "finished_at": now(), "result": result}
        atomic_json(state_path, state)
        print(f"[{index}/{len(manifest['cases'])}] {status}: {result.get('error') or 'load and recall passed'}",
              flush=True)
    state["finished_at"] = now()
    atomic_json(state_path, state)
    report = summary(manifest, state, output)
    passed = sum(r.get("status") == "passed" for r in state["cases"].values())
    failed = sum(r.get("status") == "failed" for r in state["cases"].values())
    terminal = {"run": manifest["id"], "status": "passed" if failed == 0 else "failed",
                "finished_at": now(), "passed": passed, "failed": failed,
                "cases": len(manifest["cases"]), "summary": report, "checkpoint": str(state_path)}
    atomic_json(output / "terminal.json", terminal)
    print(json.dumps(terminal), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
