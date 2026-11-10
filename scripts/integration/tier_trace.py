#!/usr/bin/env python3
"""Engine-neutral tier trace for experimental model loads and conversations.

Run: tier_trace.py run --output DIR --placement layout.json -- COMMAND ...
Mark: tier_trace.py mark --output DIR --phase load --event begin|end
Summarize: tier_trace.py summarize --output DIR
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

GPU_FIELDS = ("index", "memory.used", "utilization.gpu", "utilization.memory",
              "power.draw", "temperature.gpu", "pcie.link.gen.current",
              "pcie.link.width.current")
MEM_FIELDS = ("MemAvailable", "Cached", "SwapFree", "SwapTotal")
BLOCK_NAMES = ("nvme0n1", "sda")


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def append_jsonl(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()


def number(value):
    value = value.strip()
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return None


def snapshot():
    host = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in MEM_FIELDS:
            host[key + "_kib"] = int(value.split()[0])
    disks = {}
    for name in BLOCK_NAMES:
        path = Path("/sys/block") / name / "stat"
        if path.is_file():
            parts = [int(x) for x in path.read_text().split()]
            disks[name] = {"read_bytes": parts[2] * 512,
                           "write_bytes": parts[6] * 512,
                           "reads": parts[0], "read_ms": parts[3]}
    gpu_result = subprocess.run(
        ["nvidia-smi", "--query-gpu=" + ",".join(GPU_FIELDS),
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5)
    gpus = {}
    if gpu_result.returncode == 0:
        for line in gpu_result.stdout.splitlines():
            parts = [number(part) for part in line.split(",")]
            if len(parts) == len(GPU_FIELDS) and isinstance(parts[0], int):
                gpus[str(parts[0])] = dict(zip(GPU_FIELDS[1:], parts[1:]))
    process_result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_gpu_memory",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5)
    processes = []
    if process_result.returncode == 0:
        for line in process_result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) == 3:
                processes.append({"gpu_uuid": parts[0], "pid": number(parts[1]),
                                  "used_gpu_memory_mib": number(parts[2])})
    return {"utc": utc(), "monotonic_ns": time.monotonic_ns(),
            "host": host, "disks": disks, "gpus": gpus,
            "compute_processes": processes,
            "gpu_error": None if gpu_result.returncode == 0 else gpu_result.stderr[-300:],
            "process_error": None if process_result.returncode == 0 else process_result.stderr[-300:]}


def mark(output: Path, phase: str, event: str, details=None):
    if event not in ("begin", "end"):
        raise ValueError("event must be begin or end")
    before_ns, before_utc = time.monotonic_ns(), utc()
    snap = snapshot()
    boundary_ns, boundary_utc = ((time.monotonic_ns(), utc()) if event == "begin"
                                 else (before_ns, before_utc))
    item = {"phase": phase, "event": event, "snapshot": snap,
            "boundary_monotonic_ns": boundary_ns, "boundary_utc": boundary_utc}
    if details:
        item["details"] = details
    append_jsonl(output / "events.jsonl", item)
    return item


def rows(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(output: Path):
    samples = rows(output / "samples.jsonl")
    events = rows(output / "events.jsonl")
    starts = {}
    phases = []
    for item in events:
        key = item["phase"]
        if item["event"] == "begin":
            starts.setdefault(key, []).append(item)
            continue
        if not starts.get(key):
            phases.append({"phase": key, "error": "end without begin"})
            continue
        first = starts[key].pop(0)
        a, b = first["snapshot"], item["snapshot"]
        interval = [sample for sample in samples
                    if first["boundary_monotonic_ns"] <= sample["monotonic_ns"] <= item["boundary_monotonic_ns"]]
        interval = [a, *interval, b]
        disk_delta = {name: {
            "read_bytes": b["disks"][name]["read_bytes"] - a["disks"][name]["read_bytes"],
            "write_bytes": b["disks"][name]["write_bytes"] - a["disks"][name]["write_bytes"]}
            for name in a["disks"].keys() & b["disks"].keys()}
        ids = set().union(*(sample["gpus"].keys() for sample in interval))
        gpu = {}
        for ident in sorted(ids, key=int):
            memories = [sample["gpus"][ident].get("memory.used") for sample in interval
                        if ident in sample["gpus"]]
            utils = [sample["gpus"][ident].get("utilization.gpu") for sample in interval
                     if ident in sample["gpus"]]
            gpu[ident] = {"peak_used_mib": max((x for x in memories if x is not None), default=None),
                          "peak_util_pct": max((x for x in utils if x is not None), default=None)}
        available = [sample["host"].get("MemAvailable_kib") for sample in interval]
        phases.append({"phase": key, "started_at": first["boundary_utc"],
                       "ended_at": item["boundary_utc"],
                       "elapsed_s": round((item["boundary_monotonic_ns"] -
                                           first["boundary_monotonic_ns"]) / 1e9, 3),
                       "disks": disk_delta, "gpus": gpu,
                       "min_mem_available_kib": min((x for x in available if x is not None), default=None),
                       "begin_details": first.get("details"), "end_details": item.get("details")})
    for key, pending in starts.items():
        phases += [{"phase": key, "error": "begin without end", "started_at": i["snapshot"]["utc"]}
                   for i in pending]
    return {"sample_count": len(samples), "event_count": len(events), "phases": phases,
            "scope": "whole-device disk counters and GPU samples; other rig activity can contribute",
            "rate_note": "Use engine token timings for decode tok/s; phase wall includes API, staging and waits."}


def run(args):
    output = args.output.resolve()
    if (output / "terminal.json").exists() or (output / "samples.jsonl").exists():
        raise SystemExit(f"trace output already exists: {output}")
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        raise SystemExit("run needs a command after --")
    placement = json.loads(args.placement.read_text()) if args.placement else {}
    if not isinstance(placement, dict):
        raise SystemExit("placement must be a JSON object")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "placement.json", placement)
    stopped = threading.Event()
    errors = []
    initial = snapshot()
    append_jsonl(output / "samples.jsonl", initial)
    record = {"started_at": initial["utc"], "command": command, "placement": placement,
              "interval_s": args.interval_s, "status": "running"}
    write_json(output / "checkpoint.json", record)

    def sample_loop():
        while not stopped.wait(args.interval_s):
            try:
                append_jsonl(output / "samples.jsonl", snapshot())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                break

    thread = threading.Thread(target=sample_loop, daemon=True)
    thread.start()
    child = None
    interrupted = False

    def terminate(signum, _frame):
        nonlocal interrupted
        interrupted = True
        if child and child.poll() is None:
            child.send_signal(signum)

    old_term = signal.signal(signal.SIGTERM, terminate)
    old_int = signal.signal(signal.SIGINT, terminate)
    try:
        child = subprocess.Popen(command,
                                 env=dict(os.environ, TIER_TRACE_DIR=str(output)))
        code = child.wait()
        record["exit_code"] = code
        record["status"] = "interrupted" if interrupted else ("passed" if code == 0 else "failed")
    except BaseException as exc:
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["exit_code"] = child.returncode if child else None
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
        stopped.set()
        thread.join(timeout=10)
        append_jsonl(output / "samples.jsonl", snapshot())
        record["finished_at"] = utc()
        record["sample_errors"] = errors
        record["summary"] = summarize(output)
        write_json(output / "terminal.json", record)
    return 0 if record["status"] == "passed" else (record.get("exit_code") or 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="action", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--placement", type=Path)
    runner.add_argument("--interval-s", type=float, default=1.0)
    runner.add_argument("command", nargs=argparse.REMAINDER)
    marker = sub.add_parser("mark")
    marker.add_argument("--output", type=Path,
                        help="trace directory; defaults to TIER_TRACE_DIR when wrapped by run")
    marker.add_argument("--phase", required=True)
    marker.add_argument("--event", choices=("begin", "end"), required=True)
    marker.add_argument("--details", help="optional JSON object such as token counts")
    summary = sub.add_parser("summarize")
    summary.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.action == "run":
        if args.interval_s < 0.2:
            ap.error("--interval-s must be at least 0.2")
        return run(args)
    if args.action == "mark":
        output = args.output or (Path(os.environ["TIER_TRACE_DIR"]) if "TIER_TRACE_DIR" in os.environ else None)
        if output is None:
            ap.error("mark needs --output or TIER_TRACE_DIR")
        details = json.loads(args.details) if args.details else None
        if details is not None and not isinstance(details, dict):
            ap.error("--details must be a JSON object")
        print(json.dumps(mark(output, args.phase, args.event, details)))
        return 0
    print(json.dumps(summarize(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
