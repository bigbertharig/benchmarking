#!/usr/bin/env python3
"""Record rig GPU telemetry during one or more image benchmark runs."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--watch", type=Path, action="append", required=True)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--max-seconds", type=int, default=7200)
    args = parser.parse_args()
    if args.receipt.exists():
        raise SystemExit(f"refusing to overwrite {args.receipt}")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_seconds
    with args.receipt.open("x", encoding="utf-8") as out:
        while time.monotonic() < deadline:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu,power.draw,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=15,
            )
            sample = {"at": datetime.now(timezone.utc).isoformat(), "gpus": []}
            memory = {}
            for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
                key, _, value = line.partition(':')
                if key in {'MemTotal', 'MemAvailable'}:
                    memory[key] = round(int(value.split()[0]) / 1024)
            sample['host_memory_mib'] = memory
            sample['watched_processes'] = []
            for run in args.watch:
                context_path = run / 'run_context.json'
                if not context_path.exists():
                    continue
                try:
                    pid = int(json.loads(context_path.read_text(encoding='utf-8')).get('pid', 0))
                    status_path = Path('/proc') / str(pid) / 'status'
                    if pid and status_path.is_file():
                        values = {}
                        for line in status_path.read_text(encoding='utf-8').splitlines():
                            key, _, value = line.partition(':')
                            if key in {'VmRSS', 'VmHWM'}:
                                values[key] = round(int(value.split()[0]) / 1024)
                        sample['watched_processes'].append({'run': str(run), 'pid': pid,
                                                             'memory_mib': values})
                except (OSError, ValueError):
                    pass
            if proc.returncode:
                sample["error"] = proc.stderr.strip()[-300:]
            else:
                for line in proc.stdout.splitlines():
                    values = [part.strip() for part in line.split(",")]
                    if len(values) == 5:
                        sample["gpus"].append(dict(zip(
                            ("index", "memory_mib", "util_pct", "power_w", "temperature_c"),
                            (int(values[0]), int(values[1]), int(values[2]), float(values[3]), int(values[4])),
                        )))
            out.write(json.dumps(sample) + "\n")
            out.flush()
            os.fsync(out.fileno())
            states = []
            for run in args.watch:
                context = run / "run_context.json"
                if context.exists():
                    try:
                        states.append(json.loads(context.read_text(encoding="utf-8")).get("status"))
                    except (OSError, ValueError):
                        states.append("running")
                else:
                    states.append("waiting")
            if states and all(state in {"complete", "complete_with_blocks", "complete_with_failures", "failed"} for state in states):
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
