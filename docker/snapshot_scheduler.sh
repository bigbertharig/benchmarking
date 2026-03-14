#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: snapshot_scheduler.sh --run-root <path> [options]

Write timed progress snapshots for any benchmark run directory.

Required:
  --run-root PATH            Run directory (contains results/ and manifest.tsv)

Options:
  --specs "600:10m ..."      Space-separated seconds:label entries.
                             Default: "600:10m 1800:30m 3600:1h 7200:2h 10800:3h 14400:4h 18000:5h 21600:6h"
  --name NAME                Output prefix. Default: snapshot
  --background               Detach and write logs to <run-root>/<name>_monitor.out (default)
  --foreground               Run attached
  --help                     Show this help
EOF
}

RUN_ROOT=""
SPECS="600:10m 1800:30m 3600:1h 7200:2h 10800:3h 14400:4h 18000:5h 21600:6h"
NAME="snapshot"
BACKGROUND=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-root) RUN_ROOT="${2:-}"; shift 2 ;;
    --specs) SPECS="${2:-}"; shift 2 ;;
    --name) NAME="${2:-}"; shift 2 ;;
    --background) BACKGROUND=1; shift 1 ;;
    --foreground) BACKGROUND=0; shift 1 ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$RUN_ROOT" ]]; then
  echo "ERROR: --run-root is required" >&2
  usage
  exit 2
fi

if [[ ! -d "$RUN_ROOT" ]]; then
  echo "ERROR: run root not found: $RUN_ROOT" >&2
  exit 1
fi

SNAP_DIR="$RUN_ROOT/snapshots"
mkdir -p "$SNAP_DIR"

capture_snapshot() {
  local label="$1"
  local ts
  ts="$(date -Iseconds)"
  local out="$SNAP_DIR/${NAME}_${label}.json"
  local out_txt="$SNAP_DIR/${NAME}_${label}.txt"
  python3 - "$RUN_ROOT" "$label" "$ts" "$out_txt" <<'PY' > "$out"
import datetime
import glob
import json
import os
import sys
from typing import Dict, Any, List

run_root, label, ts, out_txt = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
manifest_path = os.path.join(run_root, "manifest.tsv")
manifest_rows = []
if os.path.exists(manifest_path):
    with open(manifest_path, "r", encoding="utf-8", errors="replace") as f:
        lines = [ln.rstrip("\n") for ln in f]
    if lines:
        hdr = lines[0].split("\t")
        for ln in lines[1:]:
            if not ln.strip():
                continue
            vals = ln.split("\t")
            row = {hdr[i]: vals[i] if i < len(vals) else "" for i in range(len(hdr))}
            manifest_rows.append(row)

snap_dir = os.path.join(run_root, "snapshots")
state_path = os.path.join(snap_dir, ".snapshot_state.json")
captured_dt = datetime.datetime.fromisoformat(ts)
captured_epoch = captured_dt.timestamp()

state: Dict[str, Any] = {"run_start_epoch": captured_epoch, "models": {}}
if os.path.exists(state_path):
    try:
        with open(state_path, "r", encoding="utf-8", errors="replace") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            state.update(loaded)
    except Exception:
        pass

def read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)

def count_jsonl_rows(path: str) -> int:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)

def find_eval(path_glob: str) -> bool:
    return bool(glob.glob(path_glob))

def fmt_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

def load_manifest_rows() -> List[Dict[str, str]]:
    return [r for r in manifest_rows if r.get("port") and r.get("model")]

bench_code_progress: List[Dict[str, Any]] = []
manifest_items = load_manifest_rows()
if manifest_items:
    history_root = os.path.dirname(run_root)
    for row in manifest_items:
        port = row.get("port", "").strip()
        model = row.get("model", "").strip()
        run_name = row.get("run_name", "").strip()
        if not run_name:
            continue
        result_root = os.path.join(history_root, f"bench-code_{model}_{run_name}")
        he_jsonl = glob.glob(os.path.join(result_root, "humaneval", "*.jsonl"))
        mb_jsonl = glob.glob(os.path.join(result_root, "mbpp", "*.jsonl"))

        he_count = count_jsonl_rows(he_jsonl[0]) if he_jsonl else 0
        mb_count = count_jsonl_rows(mb_jsonl[0]) if mb_jsonl else 0
        he_scored = find_eval(os.path.join(result_root, "humaneval", "*_eval_results.json"))
        mb_scored = find_eval(os.path.join(result_root, "mbpp", "*_eval_results.json"))

        he_total = 164
        mb_total = 378
        total_units = he_total + mb_total
        done_units = min(he_count, he_total) + min(mb_count, mb_total)
        remaining_units = max(0, total_units - done_units)

        key = f"{port}|{model}|{run_name}"
        model_state = state["models"].get(key, {})
        baseline_units = int(model_state.get("baseline_units", done_units))
        last_units = int(model_state.get("last_units", done_units))
        last_epoch = float(model_state.get("last_epoch", captured_epoch))
        run_start_epoch = float(state.get("run_start_epoch", captured_epoch))

        delta_units = done_units - last_units
        delta_time = max(0.0, captured_epoch - last_epoch)
        instant_rate = (delta_units / delta_time) if delta_time > 0 and delta_units > 0 else 0.0

        run_units = max(0, done_units - baseline_units)
        run_elapsed = max(0.0, captured_epoch - run_start_epoch)
        avg_rate = (run_units / run_elapsed) if run_elapsed > 0 and run_units > 0 else 0.0

        rate = instant_rate if instant_rate > 0 else avg_rate
        eta_seconds = (remaining_units / rate) if rate > 0 and remaining_units > 0 else None

        state["models"][key] = {
            "baseline_units": baseline_units,
            "last_units": done_units,
            "last_epoch": captured_epoch,
        }

        bench_code_progress.append(
            {
                "port": port,
                "model": model,
                "run_name": run_name,
                "humaneval": {"completed": he_count, "total": he_total, "scored": he_scored},
                "mbpp": {"completed": mb_count, "total": mb_total, "scored": mb_scored},
                "overall": {
                    "completed_units": done_units,
                    "total_units": total_units,
                    "remaining_units": remaining_units,
                    "eta_seconds": eta_seconds,
                },
                "line": (
                    f"{port} {model}: humaneval {he_count}/{he_total}"
                    f"{' scored' if he_scored else ''}, mbpp {mb_count}/{mb_total}"
                    f"{' scored' if mb_scored else ''}"
                    + (f", est remaining {fmt_duration(eta_seconds)}" if eta_seconds is not None else "")
                ),
            }
        )

status_items = []
generic_progress: List[Dict[str, Any]] = []
for p in sorted(glob.glob(os.path.join(run_root, "results", "*_status.json"))):
    try:
        d = read_json(p)
    except Exception as e:
        status_items.append({"file": os.path.basename(p), "parse_error": str(e)})
        continue
    status_items.append(
        {
            "file": os.path.basename(p),
            "model": d.get("model"),
            "runtime": d.get("runtime"),
            "current_test": d.get("current_test"),
            "completed_stages": d.get("completed_stages"),
            "total_stages": d.get("total_stages"),
            "passed_stages": d.get("passed_stages"),
            "failed_stages": d.get("failed_stages"),
            "skipped_stages": d.get("skipped_stages"),
            "last_status": d.get("last_status"),
            "last_duration_seconds": d.get("last_duration_seconds"),
            "elapsed_total_seconds": d.get("elapsed_total_seconds"),
            "checkpoint_file": d.get("checkpoint_file"),
        }
    )

    # Generic progress extraction for bench-pipeline/bench-reasoning/bench-knowledge style status files.
    model = d.get("model") or d.get("model_name") or "unknown-model"
    runtime = d.get("runtime") or ""
    key = f"status|{os.path.basename(p)}|{model}|{runtime}"

    completed = d.get("completed_stages")
    total = d.get("total_stages")
    failed = d.get("failed_stages")
    current = d.get("current_test")

    if completed is None or total is None:
        tasks = d.get("tasks") if isinstance(d.get("tasks"), dict) else {}
        req = d.get("tasks_requested") if isinstance(d.get("tasks_requested"), list) else sorted(tasks.keys())
        total = len(req)
        completed = sum(1 for t in req if (tasks.get(t) or {}).get("state") == "completed")
        failed = sum(1 for t in req if (tasks.get(t) or {}).get("state") == "failed")
        if not current:
            current = next((t for t in req if (tasks.get(t) or {}).get("state") not in ("completed", "failed")), "done")

    try:
        completed = int(completed)
    except Exception:
        completed = 0
    try:
        total = int(total)
    except Exception:
        total = 0
    try:
        failed = int(failed) if failed is not None else 0
    except Exception:
        failed = 0
    current = str(current or "unknown")

    remaining = max(0, total - completed)
    model_state = state["models"].get(key, {})
    baseline_units = int(model_state.get("baseline_units", completed))
    last_units = int(model_state.get("last_units", completed))
    last_epoch = float(model_state.get("last_epoch", captured_epoch))
    run_start_epoch = float(state.get("run_start_epoch", captured_epoch))

    delta_units = completed - last_units
    delta_time = max(0.0, captured_epoch - last_epoch)
    instant_rate = (delta_units / delta_time) if delta_time > 0 and delta_units > 0 else 0.0
    run_units = max(0, completed - baseline_units)
    run_elapsed = max(0.0, captured_epoch - run_start_epoch)
    avg_rate = (run_units / run_elapsed) if run_elapsed > 0 and run_units > 0 else 0.0
    rate = instant_rate if instant_rate > 0 else avg_rate
    eta_seconds = (remaining / rate) if rate > 0 and remaining > 0 else None

    state["models"][key] = {
        "baseline_units": baseline_units,
        "last_units": completed,
        "last_epoch": captured_epoch,
    }

    line = f"{model}: {completed}/{total} stages"
    if failed:
        line += f", failed {failed}"
    line += f", current {current}"
    if eta_seconds is not None:
        line += f", est remaining {fmt_duration(eta_seconds)}"

    generic_progress.append(
        {
            "file": os.path.basename(p),
            "model": model,
            "runtime": runtime,
            "completed": completed,
            "total": total,
            "failed": failed,
            "current": current,
            "eta_seconds": eta_seconds,
            "line": line,
        }
    )

checkpoint_items = []
for p in sorted(glob.glob(os.path.join(run_root, "results", "*_checkpoint.json"))):
    st = os.stat(p)
    checkpoint_items.append(
        {
            "file": os.path.basename(p),
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).isoformat(),
            "size": st.st_size,
        }
    )

out = {
    "snapshot_label": label,
    "captured_at": ts,
    "run_root": run_root,
    "manifest": manifest_rows,
    "bench_code_progress": bench_code_progress,
    "generic_progress": generic_progress,
    "human_summary_lines": [item["line"] for item in bench_code_progress] if bench_code_progress else [item["line"] for item in generic_progress],
    "status": status_items,
    "checkpoints": checkpoint_items,
}

with open(out_txt, "w", encoding="utf-8") as f:
    if bench_code_progress:
        for item in bench_code_progress:
            f.write(f"- {item['line']}\n")
    elif generic_progress:
        for item in generic_progress:
            f.write(f"- {item['line']}\n")
    else:
        f.write("No bench-code progress rows detected in this snapshot.\n")

with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)

print(json.dumps(out, indent=2))
PY
  echo "[$(date -Iseconds)] wrote $out and $out_txt"
}

run_scheduler() {
  capture_snapshot "now"
  local start_epoch now target sec label spec
  start_epoch="$(date +%s)"
  for spec in $SPECS; do
    sec="${spec%%:*}"
    label="${spec##*:}"
    target=$((start_epoch + sec))
    now="$(date +%s)"
    if (( target > now )); then
      sleep $((target - now))
    fi
    capture_snapshot "$label"
  done
}

if [[ "$BACKGROUND" -eq 1 ]]; then
  LOG="$RUN_ROOT/${NAME}_monitor.out"
  nohup "$0" --foreground --run-root "$RUN_ROOT" --specs "$SPECS" --name "$NAME" > "$LOG" 2>&1 &
  echo "SNAPSHOT_MONITOR_PID=$!"
  echo "SNAPSHOT_LOG=$LOG"
  exit 0
fi

run_scheduler
