#!/usr/bin/env python3
"""Guarded rig survey with model-free small and deep work scans.

Run on the rig. Reuses rig observe, the benchmark lease, the existing CUDA copy
probe, and the existing host RAM headroom probe. Storage is optional and uses
bounded direct I/O against a caller-selected directory. Synthetic work classes
exercise weight, expert, KV, and lookup access without loading a model.
"""
from __future__ import annotations

import argparse
import csv
import json
import mmap
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import benchmark_session


HERE = Path(__file__).resolve().parent
LEASE = HERE / "harness_lease.sh"
LINK = HERE / "run_cuda_link_probe.py"
RAM = HERE / "probe_host_ram_budget.py"
DETAIL = HERE.parent / "analysis" / "snapshot_expert_hardware.py"
WORK = HERE / "run_synthetic_work_probe.py"
DEFAULT_BINARY = Path("/data/bench-staging/cuda-link-probe")


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def meminfo() -> dict[str, int]:
    result = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"MemTotal", "MemAvailable", "SwapFree"}:
            result[key + "_kib"] = int(value.split()[0])
    if len(result) != 3:
        raise RuntimeError("incomplete /proc/meminfo")
    return result


def selected_cards(snapshot: dict, requested: str) -> list[int]:
    detected = {card["index"] for card in snapshot["cards"]}
    if requested == "all":
        return sorted(detected)
    try:
        ids = [int(part.strip()) for part in requested.split(",")]
    except ValueError as exc:
        raise ValueError("--gpus must be 'all' or comma-separated host GPU indexes") from exc
    if not ids or len(ids) != len(set(ids)) or set(ids) - detected:
        raise ValueError(f"GPU selection {ids} does not match live indexes {sorted(detected)}")
    return ids


def plan(args: argparse.Namespace) -> dict:
    snapshot = benchmark_session.scan()
    ids = selected_cards(snapshot, args.gpus)
    memory = meminfo()
    target = args.ram_target_gb
    if target is None:
        available = memory["MemAvailable_kib"] * 1024
        total = memory["MemTotal_kib"] * 1024
        floor = args.min_available_gib * 1024**3
        target = max(0, min(0.9 * total, available - floor - 1024**3)) / 1e9
        target = round(target, 2)
    if target <= 0 and not args.skip_ram:
        raise RuntimeError("no RAM headroom above the configured guard")
    storage = Path(args.storage_dir).resolve() if args.storage_dir else None
    if storage and not storage.is_dir():
        raise RuntimeError("--storage-dir must be an existing directory")
    if storage and not hasattr(os, "O_DIRECT"):
        raise RuntimeError("this host does not expose O_DIRECT for the storage probe")
    if storage and shutil.disk_usage(storage).free < (args.storage_size_mib * 4 + 2048) * 1024**2:
        raise RuntimeError("storage path needs probe size x4 plus 2 GiB free")
    return {"schema": "rig-limit-plan/1", "created_at": stamp(), "hardware": snapshot,
            "selected_gpu_ids": ids, "memory_before": memory,
            "ram_target_gb_decimal": target, "min_available_gib": args.min_available_gib,
            "link_probe": not args.skip_link, "link_binary": str(args.link_binary),
            "ram_probe": not args.skip_ram, "storage_dir": str(storage) if storage else None,
            "storage_size_mib": args.storage_size_mib if storage else None,
            "work_scan": args.scan,
            "availability": {"link_binary": args.link_binary.is_file(),
                             "docker": shutil.which("docker") is not None,
                             "direct_io": hasattr(os, "O_DIRECT")}}


def run_command(command: list[str], output: Path, timeout: int) -> dict:
    started = stamp()
    start = time.monotonic()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        status = "passed" if proc.returncode == 0 else "failed"
        code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        status, code = "timeout", None
        stdout = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    output.mkdir(parents=True, exist_ok=True)
    (output / "stdout.log").write_text(stdout)
    (output / "stderr.log").write_text(stderr)
    result = {"status": status, "exit_code": code, "started_at": started,
              "finished_at": stamp(), "duration_s": round(time.monotonic() - start, 3),
              "command": command, "output": str(output)}
    save(output / "stage.json", result)
    return result


def storage_probe(directory: Path, output: Path, size_mib: int) -> dict:
    """Bounded depth-one direct I/O. Only our unique temporary file is removed."""
    started = stamp()
    start = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < (size_mib * 4 + 2048) * 1024**2:
        raise RuntimeError("storage free space fell below probe size x4 plus 2 GiB")
    stages: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="rig-limit-", dir=directory) as temporary:
        data_file = Path(temporary) / "probe.bin"
        descriptor = os.open(data_file, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_DIRECT, 0o600)
        try:
            chunk = 1024**2
            with mmap.mmap(-1, chunk) as buffer:
                buffer[:] = bytes(range(256)) * (chunk // 256)
                begin = time.monotonic()
                for index in range(size_mib):
                    if os.pwritev(descriptor, [buffer], index * chunk) != chunk:
                        raise OSError("short direct write")
                os.fsync(descriptor)
                elapsed = time.monotonic() - begin
                stages["sequential_write"] = {"bytes": size_mib * chunk,
                                               "seconds": elapsed,
                                               "gbps": size_mib * chunk / elapsed / 1e9}
                begin = time.monotonic()
                for index in range(size_mib):
                    if os.preadv(descriptor, [buffer], index * chunk) != chunk:
                        raise OSError("short direct read")
                elapsed = time.monotonic() - begin
                stages["sequential_read"] = {"bytes": size_mib * chunk,
                                              "seconds": elapsed,
                                              "gbps": size_mib * chunk / elapsed / 1e9}
                small = memoryview(buffer)[:4096]
                try:
                    rng = random.Random(0)
                    block_count = size_mib * 256
                    operations = 4096
                    begin = time.monotonic()
                    for _ in range(operations):
                        offset = rng.randrange(block_count) * 4096
                        if os.preadv(descriptor, [small], offset) != 4096:
                            raise OSError("short direct random read")
                    elapsed = time.monotonic() - begin
                    stages["random_read"] = {"operations": operations, "seconds": elapsed,
                                              "iops": operations / elapsed,
                                              "mean_ms": elapsed * 1000 / operations}
                finally:
                    small.release()
        finally:
            os.close(descriptor)
    result = {"status": "passed", "measurement": "O_DIRECT, queue depth 1",
              "started_at": started, "finished_at": stamp(),
              "duration_s": round(time.monotonic() - start, 3), "stages": stages,
              "direct_io": True, "size_mib": size_mib, "directory": str(directory)}
    save(output / "stage.json", result)
    return result


def lease(action: str, *arguments: str) -> str:
    result = subprocess.run(["bash", str(LEASE), action, *arguments],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"Manager lease {action} refused: {result.stderr.strip()}")
    return result.stdout.strip()


def compact_link(path: Path) -> list[dict]:
    csv_path = path / "copies.csv"
    if not csv_path.is_file():
        return []
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [{"kind": row["kind"], "src": row["src"], "dst": row["dst"],
             "gbps": float(row["GBps"]), "median_ms": float(row["median_ms"])}
            for row in rows if int(row["bytes"]) == 128 * 1024**2]


def physical_link_labels(path: Path) -> dict[str, str]:
    """Resolve CUDA ordinals using PCI buses, not host GPU ordering."""
    inventory_file = path / "inventory.json"
    diagnostics_file = path / "diagnostics.log"
    if not inventory_file.is_file() or not diagnostics_file.is_file():
        return {"-1": "host RAM"}
    inventory = json.loads(inventory_file.read_text())
    by_bus = {card["pci_bus_id"].lower()[-7:]: int(host_id)
              for host_id, card in inventory.items()}
    labels = {"-1": "host RAM"}
    for cuda_id, bus in re.findall(r"DEVICE id=(\d+).*? bus=(\S+)",
                                   diagnostics_file.read_text()):
        host_id = by_bus.get(bus.lower()[-7:])
        if host_id is not None:
            labels[cuda_id] = f"host GPU {host_id}"
    return labels


def report(output: Path) -> None:
    state = json.loads((output / "terminal.json").read_text())
    plan_data = json.loads((output / "plan.json").read_text())
    hardware = plan_data["hardware"]
    lines = ["# Rig limit survey: starting guidance", "",
             f"Run: `{output.name}`; status: **{state['status']}**; observed: {plan_data['created_at']}", "",
             "## Hardware map", "",
             "| Host GPU | Card | VRAM MiB | PCI bus | UUID |", "|---:|---|---:|---|---|"]
    for card in hardware["cards"]:
        lines.append(f"| {card['index']} | {card['name']} | {card['total_mb']} | "
                     f"{card.get('bus', '?')} | `{card['uuid']}` |")
    lines.extend(["", "## Measured limits", ""])
    ram_stage = state["stages"].get("ram")
    ram_file = output / "ram" / "terminal.json"
    if ram_stage and ram_stage["status"] == "passed" and ram_file.is_file():
        ram = json.loads(ram_file.read_text())
        lines.append(f"- Host RAM: {ram['max_allocated_mib'] / 1024:.2f} GiB touched; "
                     f"stop: `{ram['status']}`; minimum guard {ram['min_available_gib']} GiB. "
                     "This is observed headroom during this run, not an allocation guarantee.")
    elif not plan_data.get("ram_probe"):
        lines.append("- Host RAM: skipped in this run.")
    else:
        lines.append("- Host RAM: probe failed or incomplete; inspect `ram/` and `terminal.json`.")
    link_stage = state["stages"].get("link")
    links = compact_link(output / "link") if link_stage and link_stage["status"] == "passed" else []
    if links:
        labels = physical_link_labels(output / "link")
        lines.extend(["- GPU copy paths: 128 MiB pinned-copy medians below. "
                      "Physical labels come from saved PCI buses; unresolved labels retain CUDA IDs.", "",
                      "| Path | Source | Destination | GB/s |", "|---|---|---|---:|"])
        for row in links:
            src = labels.get(row["src"], f"CUDA {row['src']}")
            dst = labels.get(row["dst"], f"CUDA {row['dst']}")
            if row["kind"] == "d2h":
                dst = "host RAM"
            lines.append(f"| {row['kind']} | {src} | {dst} | {row['gbps']:.3f} |")
        lines.append("")
    elif not plan_data.get("link_probe"):
        lines.append("- GPU transfer paths: skipped in this run.")
    else:
        lines.append("- GPU transfer paths: probe failed or incomplete; inspect `link/`.")
    storage_stage = state["stages"].get("storage")
    if storage_stage and storage_stage["status"] == "passed":
        measurements = storage_stage["stages"]
        for name in ("sequential_write", "sequential_read"):
            lines.append(f"- Storage {name}: {measurements[name]['gbps']:.3f} GB/s "
                         f"(direct I/O, {storage_stage['size_mib']} MiB file).")
        lines.append(f"- Storage random read: {measurements['random_read']['iops']:.0f} "
                     "4 KiB IOPS at queue depth 1 (direct I/O).")
    elif not plan_data.get("storage_dir"):
        lines.append("- Storage: skipped in this run.")
    else:
        lines.append("- Storage: probe failed or incomplete; inspect `storage/`.")
    work_stage = state["stages"].get("work")
    work_dir = output / "synthetic"
    work_file = work_dir / "gpu.jsonl"
    if work_stage and work_stage["status"] == "passed" and work_file.is_file():
        inventory = json.loads((work_dir / "inventory.json").read_text())
        by_bus = {card["pci_bus_id"].lower()[-7:]: f"host GPU {index}"
                  for index, card in inventory.items()}
        rows = [json.loads(line) for line in work_file.read_text().splitlines() if line.strip()]
        lines.extend(["", f"## Synthetic work scan ({plan_data['work_scan']})", "",
                      "Patterned data, no model loaded. Times are median microseconds per "
                      "operation and are not token-speed predictions. All samples and p95 values "
                      "are in `synthetic/gpu.jsonl`.", "",
                      "| GPU | Weight resident | Weight RAM upload | Long KV scan | 16-row GPU lookup |",
                      "|---|---:|---:|---:|---:|"])
        for bus, location in by_bus.items():
            gpu_rows = [row for row in rows if row.get("bus", "").lower()[-7:] == bus]
            def value(kind: str) -> str:
                matches = [row for row in gpu_rows if row["kind"] == kind]
                return f"{max(matches, key=lambda row: row['bytes'])['p50_us']:.1f}" if matches else "—"
            lines.append(f"| {location} | {value('weight_resident')} | "
                         f"{value('weight_ram_upload')} | {value('kv_scan_one_head')} | "
                         f"{value('lookup_gpu_gather')} |")
        lines.extend(["", "Weight arrays are 32/128 MiB in small/deep; the long one-head KV "
                      "scan covers 32K/128K positions; the GPU lookup gathers sixteen 128-byte "
                      "rows from a 64/256 MiB table.", "",
                      "| GPU | Expert cache hit µs | RAM miss µs | Realized hit rate |",
                      "|---|---:|---:|---:|"])
        for bus, location in by_bus.items():
            matched = {row["kind"]: row for row in rows
                       if row.get("bus", "").lower()[-7:] == bus}
            route = matched.get("expert_route_80pct_hot", {})
            rate = (f"{route['hits'] / route['samples']:.0%}" if route.get("samples") else "—")
            hit = matched.get("expert_cache_hit", {}).get("p50_us")
            miss = matched.get("expert_ram_miss", {}).get("p50_us")
            lines.append(f"| {location} | {hit:.1f} | {miss:.1f} | {rate} |"
                         if hit is not None and miss is not None else
                         f"| {location} | — | — | {rate} |")
        ram_lookup = next((row for row in rows if row["kind"] == "lookup_pinned_ram"), None)
        if ram_lookup:
            lines.append(f"\n- Sixteen-row pinned RAM lookup: median {ram_lookup['p50_us']:.1f} µs "
                         f"(p95 {ram_lookup['p95_us']:.1f} µs).")
        contention = next((row for row in rows if row["kind"] == "concurrent_h2d"), None)
        if contention:
            lines.extend(["", "Matched 32 MiB pinned uploads, serial then simultaneous "
                          "(GB/s on each physical card):", "",
                          "| GPU | Alone | Simultaneous | Slowdown |",
                          "|---|---:|---:|---:|"])
            for bus, location in by_bus.items():
                solo = next((row for row in rows if row["kind"] == "h2d_serial_device"
                             and row["bus"].lower()[-7:] == bus), None)
                parallel = next((row for row in rows if row["kind"] == "h2d_parallel_device"
                                 and row["bus"].lower()[-7:] == bus), None)
                if solo and parallel:
                    lines.append(f"| {location} | {solo['gbps']:.3f} | "
                                 f"{parallel['gbps']:.3f} | "
                                 f"{solo['gbps'] / parallel['gbps']:.2f}× |")
            lines.append("\nThe comparison isolates measured shared-traffic effects; "
                         "a slowdown above 1 can also include CPU scheduling and pinned-memory pressure.")
        storage_file = work_dir / "storage.json"
        if storage_file.is_file():
            storage = json.loads(storage_file.read_text())
            for key, label in (("warm_buffered_128b_per_row", "warm page-cache rows"),
                               ("direct_4k_per_row", "direct storage rows")):
                metric = storage[key]
                lines.append(f"- 16-row {label}: median {metric['p50_us']:.1f} µs; "
                             f"p95 {metric['p95_us']:.1f} µs. "
                             "Direct reads use 4 KiB per row; buffered reads use 128 bytes per row.")
        lines.append("\nInterpret weight results as resident compute versus upload on the same card. "
                     "Expert timings use a synthetic 80%-hot route and an LRU cache; "
                     "real models have different routes and kernels. KV scans are one-head "
                     "access proxies. The next model-specific stage verifies actual placement.")
    elif plan_data.get("work_scan") == "off":
        lines.append("- Synthetic work scan: skipped in this run.")
    else:
        lines.append("- Synthetic work scan: failed or incomplete; inspect `synthetic/`.")
    lines.extend(["", "## Start here", "",
                  "1. Start with the GPU that has enough **free** VRAM for the workload. "
                  "Add other GPUs only when capacity or measured execution benefits justify them.",
                  "2. For data that must cross devices repeatedly, use the measured copy paths above. "
                  "A slow PCIe path can make helper VRAM expensive to access remotely.",
                  "3. Keep the tested RAM headroom and a storage free-space margin. "
                  "Retest after changing cards, slots, RAM, drives, or the runtime.",
                  "", "These are hardware starting rules. Model fit, context, chat count, "
                  "and tokens per second require the later model placement tests.", ""])
    (output / "START_HERE.md").write_text("\n".join(lines))


def run(args: argparse.Namespace) -> int:
    planned = plan(args)
    ids = planned["selected_gpu_ids"]
    if args.skip_link and args.skip_ram and not args.storage_dir and args.scan == "off":
        raise RuntimeError("select at least one limit probe")
    if not args.skip_link and (not planned["availability"]["link_binary"]
                               or not planned["availability"]["docker"]):
        raise RuntimeError("CUDA link probe binary and Docker are required; use --skip-link to omit")
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError("output directory must be new or empty; use a new run ID")
    args.output.mkdir(parents=True, exist_ok=True)
    save(args.output / "plan.json", planned)
    save(args.output / "session_hardware.json", planned["hardware"])
    state = {"schema": "rig-limit-test/1", "started_at": stamp(), "status": "running",
             "selected_gpu_ids": ids, "stages": {}}
    save(args.output / "checkpoint.json", state)
    lease_id = ""
    owner = f"rig-limit-{args.output.name}"
    try:
        if not args.skip_link or args.scan != "off":
            lease_id = lease("acquire", ",".join(map(str, ids)), owner, args.output.name)
            if not lease_id:
                raise RuntimeError("Manager unreachable: refusing GPU probe without a lease")
        state["stages"]["hardware_detail"] = run_command(
            [sys.executable, str(DETAIL), "--output", str(args.output / "hardware_detail.json")],
            args.output / "hardware_detail", 30)
        save(args.output / "checkpoint.json", state)
        if not args.skip_link:
            benchmark_session.verify_saved(planned["hardware"], benchmark_session.scan(), set(ids))
            state["stages"]["link"] = run_command(
                [sys.executable, str(LINK), "--output", str(args.output / "link"),
                 "--gpus", ",".join(map(str, ids)), "--binary", str(args.link_binary)],
                args.output / "link_wrapper", 330)
            save(args.output / "checkpoint.json", state)
        if args.scan != "off":
            benchmark_session.verify_saved(planned["hardware"], benchmark_session.scan(), set(ids))
            work_command = [sys.executable, str(WORK), "--output", str(args.output / "synthetic"),
                            "--preset", args.scan, "--gpus", ",".join(map(str, ids))]
            if args.storage_dir:
                work_command.extend(["--storage-dir", planned["storage_dir"]])
            state["stages"]["work"] = run_command(
                work_command, args.output / "synthetic_wrapper",
                1200 if args.scan == "deep" else 600)
            save(args.output / "checkpoint.json", state)
        if lease_id:
            lease("release", lease_id, owner)
            lease_id = ""
        if not args.skip_ram:
            state["stages"]["ram"] = run_command(
                [sys.executable, str(RAM), "--output", str(args.output / "ram"),
                 "--target-gb-decimal", str(planned["ram_target_gb_decimal"]),
                 "--min-available-gib", str(args.min_available_gib)],
                args.output / "ram_wrapper", 600)
            save(args.output / "checkpoint.json", state)
        if args.storage_dir:
            try:
                state["stages"]["storage"] = storage_probe(
                    Path(planned["storage_dir"]), args.output / "storage", args.storage_size_mib)
            except Exception as exc:
                state["stages"]["storage"] = {"status": "failed", "error":
                                                f"{type(exc).__name__}: {exc}",
                                                "finished_at": stamp()}
                save(args.output / "storage/stage.json", state["stages"]["storage"])
            save(args.output / "checkpoint.json", state)
        state["status"] = "passed" if all(
            stage["status"] == "passed" for stage in state["stages"].values()) else "partial"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if lease_id:
            try:
                lease("release", lease_id, owner)
            except Exception as exc:
                state["release_error"] = str(exc)
                state["status"] = "partial" if state["status"] == "passed" else state["status"]
        state["finished_at"] = stamp()
        save(args.output / "terminal.json", state)
        report(args.output)
        print(json.dumps({"status": state["status"], "output": str(args.output),
                          "report": str(args.output / "START_HERE.md")}))
    return 0 if state["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["check", "run", "report"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gpus", default="all", help="host GPU indexes; default all")
    parser.add_argument("--link-binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--scan", choices=["small", "deep", "off"], default="small",
                        help="model-free work classes; default small")
    parser.add_argument("--skip-link", action="store_true")
    parser.add_argument("--skip-ram", action="store_true")
    parser.add_argument("--ram-target-gb", type=float, help="decimal GB; default from live headroom")
    parser.add_argument("--min-available-gib", type=float, default=4)
    parser.add_argument("--storage-dir", help="existing directory to test with bounded direct I/O")
    parser.add_argument("--storage-size-mib", type=int, default=512)
    args = parser.parse_args()
    if args.min_available_gib < 3 or args.storage_size_mib < 64:
        parser.error("RAM guard must be at least 3 GiB; storage size at least 64 MiB")
    if args.mode in {"run", "report"} and args.output is None:
        parser.error("--output is required for run and report")
    if args.mode == "report":
        report(args.output)
        return 0
    if args.mode == "check":
        print(json.dumps(plan(args), indent=2))
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
