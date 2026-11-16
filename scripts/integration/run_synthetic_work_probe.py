#!/usr/bin/env python3
"""Run bounded model-free work classes on selected physical GPUs and storage.

This probe has no Manager dependency. The caller owns leases and service state.
GPU identity is frozen by PCI bus; output is raw latency, not model tokens/s.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
import random
import shutil
import statistics
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from hardware_inventory import scan_cards, require_ids, check_planned_power


SOURCE = Path(__file__).with_name("synthetic_work_probe.cu")
DEFAULT_BINARY = Path("/data/bench-staging/synthetic-work-probe")
DEFAULT_IMAGE = "nvidia/cuda:12.9.2-devel-ubuntu24.04"


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def summarize(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {"samples": len(ordered), "mean_us": statistics.fmean(ordered),
            "p50_us": ordered[int(.50 * (len(ordered) - 1))],
            "p95_us": ordered[int(.95 * (len(ordered) - 1))]}


def storage_lookup(directory: Path, preset: str) -> dict:
    """Identical 16-row random batches through page cache and direct I/O.

    Direct I/O reads 4 KiB for each 128-byte row. The buffered case reads 128
    bytes from page cache, deliberately expressing the difference in I/O unit.
    """
    if not hasattr(os, "O_DIRECT"):
        raise RuntimeError("O_DIRECT unavailable")
    size_mib = 256 if preset == "deep" else 64
    if shutil.disk_usage(directory).free < (size_mib + 2048) * 1024**2:
        raise RuntimeError("storage path requires probe size plus 2 GiB free")
    calls = 120 if preset == "deep" else 40
    size = size_mib * 1024**2
    rng = random.Random(104729)
    batches = [[rng.randrange(size // 128) * 128 for _ in range(16)]
               for _ in range(calls + 3)]
    started = stamp()
    with tempfile.TemporaryDirectory(prefix="synthetic-work-", dir=directory) as temporary:
        path = Path(temporary) / "rows.bin"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_DIRECT, 0o600)
        try:
            with mmap.mmap(-1, 1024**2) as buffer:
                buffer[:] = b"\x25" * len(buffer)
                for index in range(size_mib):
                    if os.pwritev(fd, [buffer], index * len(buffer)) != len(buffer):
                        raise OSError("short direct write")
                os.fsync(fd)
                fourk = memoryview(buffer)[:4096]
                try:
                    direct = []
                    for offsets in batches:
                        begin = time.perf_counter_ns()
                        for offset in offsets:
                            if os.preadv(fd, [fourk], offset & ~4095) != 4096:
                                raise OSError("short direct row read")
                        direct.append((time.perf_counter_ns() - begin) / 1000)
                finally:
                    fourk.release()
        finally:
            os.close(fd)
        with path.open("rb", buffering=0) as stream:
            # Warm precisely the selected pages; do not claim a cold page-cache
            # result merely because the direct reads bypassed that cache.
            for offsets in batches:
                for offset in offsets:
                    if len(os.pread(stream.fileno(), 128, offset)) != 128:
                        raise OSError("short buffered row read")
            buffered = []
            for offsets in batches:
                begin = time.perf_counter_ns()
                for offset in offsets:
                    data = os.pread(stream.fileno(), 128, offset)
                    if data != b"\x25" * 128:
                        raise RuntimeError("buffered row correctness check failed")
                buffered.append((time.perf_counter_ns() - begin) / 1000)
    return {"status": "passed", "started_at": started, "finished_at": stamp(),
            "directory": str(directory), "size_mib": size_mib,
            "rows_per_call": 16, "row_bytes": 128,
            "direct_4k_per_row": summarize(direct[3:]),
            "warm_buffered_128b_per_row": summarize(buffered[3:])}


def build(binary: Path, image: str, output: Path) -> None:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    marker = binary.with_suffix(binary.suffix + ".sha256")
    if binary.is_file() and marker.is_file() and marker.read_text().strip() == digest:
        return
    binary.parent.mkdir(parents=True, exist_ok=True)
    command = ["docker", "run", "--rm", "--network", "none",
               "-v", f"{SOURCE.parent}:/source:ro",
               "-v", f"{binary.parent}:/output",
               image, "nvcc", "-O3", "-std=c++17",
               "-gencode", "arch=compute_61,code=sm_61",
               "-gencode", "arch=compute_86,code=sm_86",
               "-gencode", "arch=compute_86,code=compute_86",
               "/source/synthetic_work_probe.cu", "-o", f"/output/{binary.name}"]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
    (output / "build.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f"CUDA probe build failed ({proc.returncode}); see build.log")
    marker.write_text(digest + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preset", choices=("small", "deep"), required=True)
    parser.add_argument("--gpus", required=True, help="comma-separated host GPU IDs")
    parser.add_argument("--storage-dir", type=Path)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--cuda-image", default=DEFAULT_IMAGE)
    args = parser.parse_args()
    ids = [int(part) for part in args.gpus.split(",")]
    if not ids or len(ids) != len(set(ids)):
        parser.error("GPU IDs must be unique")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("output must be new or empty")
    cards = scan_cards()
    require_ids(ids, cards)
    check_planned_power(ids)
    busy = [index for index in ids if cards[index]["used_mib"] > 1024]
    if busy:
        raise RuntimeError(f"selected GPUs busy: {busy}")
    observed = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,pci.bus_id", "--format=csv,noheader"],
        capture_output=True, text=True, check=True, timeout=10).stdout
    buses = {}
    for line in observed.splitlines():
        index, bus = [part.strip() for part in line.split(",")]
        buses[int(index)] = bus
    require_ids(ids, buses)
    args.output.mkdir(parents=True, exist_ok=True)
    save(args.output / "inventory.json",
         {index: {**cards[index], "pci_bus_id": buses[index]} for index in ids})
    state = {"schema": "synthetic-work/1", "preset": args.preset,
             "started_at": stamp(), "status": "running", "selected_gpus": ids,
             "stages": {}}
    save(args.output / "checkpoint.json", state)
    try:
        build(args.binary, args.cuda_image, args.output)
        command = ["docker", "run", "--rm", "--gpus", "all", "--network", "none",
                   "-v", f"{args.binary.parent}:/probe:ro",
                   "--entrypoint", f"/probe/{args.binary.name}", args.cuda_image,
                   args.preset, *(buses[index] for index in ids)]
        begin = time.monotonic()
        proc = subprocess.run(command, capture_output=True, text=True,
                              timeout=900 if args.preset == "deep" else 360)
        (args.output / "gpu.jsonl").write_text(proc.stdout)
        (args.output / "gpu.log").write_text(proc.stderr)
        rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        state["stages"]["gpu"] = {"status": "passed" if proc.returncode == 0 else "failed",
                                    "exit_code": proc.returncode,
                                    "duration_s": round(time.monotonic() - begin, 3),
                                    "measurements": len(rows)}
        save(args.output / "checkpoint.json", state)
        if proc.returncode:
            raise RuntimeError(f"GPU work probe failed ({proc.returncode}); see gpu.log")
        if args.storage_dir:
            state["stages"]["storage"] = storage_lookup(args.storage_dir.resolve(), args.preset)
            save(args.output / "storage.json", state["stages"]["storage"])
        state["status"] = "passed"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        state["finished_at"] = stamp()
        save(args.output / "terminal.json", state)
        print(json.dumps({"status": state["status"], "output": str(args.output)}))
    return 0 if state["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
