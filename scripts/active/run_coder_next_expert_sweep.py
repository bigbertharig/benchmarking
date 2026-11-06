#!/usr/bin/env python3
"""Run matched Coder Next placement comparisons on an otherwise idle rig."""
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path("/mnt/shared/plans/shoulders/benchmarking")
OUT = ROOT / "results/runtime_experiments/coder_next_expert_sweep_20261106"
LAUNCH = "/home/bryan/llm_orchestration/shared/scripts/rig/experiments/qwen3_coder_next_expert_sweep.py"
STOP = "/home/bryan/llm_orchestration/shared/scripts/llama_runtime/stop_runtime.sh"
LAYOUTS = ("24x5", "28x5", "24x4", "28round")

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def run_logged(argv, path, timeout):
    with path.open("w") as log:
        result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return result.returncode

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"schema": "coder-next-expert-sweep/1", "started_at": utc(), "runs": []}
    for index, layout in enumerate(LAYOUTS):
        port = 11520 + index
        name = f"coder-sweep-{layout}-{port}"
        row = {"layout": layout, "port": port, "started_at": utc(), "artifacts": {}}
        summary["runs"].append(row)
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"START {layout} port={port}", flush=True)
        try:
            load_log = OUT / f"{layout}_load.log"
            row["artifacts"]["load_log"] = str(load_log)
            row["load_exit"] = run_logged([sys.executable, LAUNCH, layout, str(port)], load_log, 900)
            if row["load_exit"] != 0:
                row["status"] = "load_failed"
                continue
            gpu = OUT / f"{layout}_gpu.csv"
            with gpu.open("w") as handle:
                subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu,temperature.gpu", "--format=csv,noheader"], stdout=handle, check=True)
            row["artifacts"]["gpu"] = str(gpu)
            probe = OUT / f"{layout}_workload32.json"
            row["artifacts"]["workload"] = str(probe)
            row["workload_exit"] = run_logged([
                sys.executable, str(ROOT / "scripts/active/probe_coder_next_placement.py"),
                "--port", str(port), "--label", layout, "--case-set", "workload32", "--output", str(probe)
            ], OUT / f"{layout}_workload.log", 1800)
            task = OUT / f"{layout}_practical.json"
            row["artifacts"]["practical"] = str(task)
            row["practical_exit"] = run_logged([
                sys.executable, str(ROOT / "scripts/active/probe_coder_next_practical_task.py"),
                "--port", str(port), "--label", layout, "--output", str(task)
            ], OUT / f"{layout}_practical.log", 900)
            row["status"] = "complete" if row["workload_exit"] == row["practical_exit"] == 0 else "probe_failed"
        except Exception as exc:
            row["status"] = "error"
            row["error"] = repr(exc)
        finally:
            stop = subprocess.run([STOP, name], capture_output=True, text=True, timeout=120)
            row["stop_exit"] = stop.returncode
            row["finished_at"] = utc()
            (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(f"END {layout} status={row['status']} stop={stop.returncode}", flush=True)
    summary["finished_at"] = utc()
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"FINISHED {OUT / 'summary.json'}", flush=True)

if __name__ == "__main__":
    main()