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
  python3 - "$RUN_ROOT" "$label" "$ts" <<'PY' > "$out"
import datetime
import glob
import json
import os
import sys

run_root, label, ts = sys.argv[1], sys.argv[2], sys.argv[3]
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

status_items = []
for p in sorted(glob.glob(os.path.join(run_root, "results", "*_status.json"))):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            d = json.load(f)
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
    "status": status_items,
    "checkpoints": checkpoint_items,
}
print(json.dumps(out, indent=2))
PY
  echo "[$(date -Iseconds)] wrote $out"
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
