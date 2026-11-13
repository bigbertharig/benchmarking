#!/usr/bin/env python3
"""Summarize a simultaneous two-chat Nsight CUDA capture by device."""
import argparse
import json
import re
import sqlite3
from pathlib import Path


def ms(ns):
    return round((ns or 0) / 1_000_000, 3)


def union_ns(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return sum(end - start for start, end in merged)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sqlite", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--cuda-map", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    cuda_map = json.loads(args.cuda_map.read_text())
    host_by_cuda = {int(cuda): int(host) for host, cuda in cuda_map["host_to_cuda"].items()}
    identity_by_cuda = {int(item["cuda_id"]): item for item in cuda_map["cuda_devices"]}
    log = args.log.read_text(errors="replace")
    metrics = {}
    pattern = (r"GEN_METRIC phase=(\S+) name=(\w+) used=(\d+) tokens=(\d+) "
               r"seconds=([\d.]+) tps=([\d.]+)")
    for phase, name, used, tokens, seconds, tps in re.findall(pattern, log):
        if phase.endswith("_two"):
            metrics[name] = {"phase": phase, "used": int(used), "tokens": int(tokens),
                             "seconds": float(seconds), "tps": float(tps)}
    if len(metrics) != 2:
        raise RuntimeError(f"expected two paired chat metrics, got {len(metrics)}")
    aggregate = re.search(r"GEN_AGGREGATE phase=(\S+_two) chats=2 tokens_each=(\d+) "
                          r"seconds=([\d.]+) aggregate_tps=([\d.]+) ok=1", log)
    if not aggregate:
        raise RuntimeError("successful paired aggregate metric absent")

    db = sqlite3.connect(args.sqlite)
    # CUPTI deviceId is the container CUDA ordinal (cuDevice), not the
    # TARGET_INFO_GPU row id, which can follow host enumeration instead.
    gpu_rows = db.execute("SELECT cuDevice,name,busLocation,uuid FROM TARGET_INFO_GPU ORDER BY cuDevice").fetchall()
    devices = {}
    for device, name, bus, uuid in gpu_rows:
        identity = identity_by_cuda.get(device)
        host = host_by_cuda.get(device)
        if (identity is None or host is None or
                identity["pci_bus_id"].lower() != bus.lower() or
                cuda_map["host_gpu_uuids"][str(host)].removeprefix("GPU-").lower() != uuid.lower()):
            raise RuntimeError(f"Nsight CUDA device {device} disagrees with captured PCI/UUID map")
        kernels = db.execute(
            "SELECT k.start,k.end,s.value FROM CUPTI_ACTIVITY_KIND_KERNEL k "
            "JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId=?", (device,)
        ).fetchall()
        graphs = db.execute(
            "SELECT start,end FROM CUPTI_ACTIVITY_KIND_GRAPH_TRACE WHERE deviceId=?", (device,)
        ).fetchall()
        copy_rows = db.execute(
            "SELECT start,end,bytes,copyKind FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE deviceId=?",
            (device,)
        ).fetchall()
        intervals = [(start, end) for start, end, _ in kernels]
        intervals += graphs
        intervals += [(start, end) for start, end, _, _ in copy_rows]
        span_ns = max(end for _, end in intervals) - min(start for start, _ in intervals) if intervals else 0
        active_ns = union_ns(intervals)
        copies = {}
        for kind, label in ((1, "h2d"), (2, "d2h"), (3, "d2d")):
            rows = [(start, end, size) for start, end, size, row_kind in copy_rows if row_kind == kind]
            copies[label] = {"count": len(rows), "MB": round(sum(row[2] for row in rows) / 1e6, 3),
                             "duration_ms": ms(sum(end - start for start, end, _ in rows))}
        devices[str(device)] = {
            "name": name, "bus": bus, "uuid": uuid, "host_gpu": host,
            "activity_span_ms": ms(span_ns), "activity_union_ms": ms(active_ns),
            "activity_gap_ms": ms(span_ns - active_ns),
            "kernels": {
                "count": len(kernels),
                "all_ms": ms(sum(end - start for start, end, _ in kernels)),
                "attention_tile_ms": ms(sum(end - start for start, end, name in kernels
                                              if "flash_attn_tile" in name)),
                "q41_dequant_ms": ms(sum(end - start for start, end, name in kernels
                                          if "dequantize_block_q4_1" in name)),
                "model_graph_ms": ms(sum(end - start for start, end in graphs)),
            },
            "copies": copies,
        }
    runtime = db.execute(
        "SELECT s.value,COUNT(*),SUM(r.end-r.start) FROM CUPTI_ACTIVITY_KIND_RUNTIME r "
        "JOIN StringIds s ON r.nameId=s.id GROUP BY s.value ORDER BY SUM(r.end-r.start) DESC LIMIT 12"
    ).fetchall()
    result = {
        "chats": metrics,
        "aggregate": {"phase": aggregate.group(1), "tokens_each": int(aggregate.group(2)),
                      "seconds": float(aggregate.group(3)), "tps": float(aggregate.group(4))},
        "devices": devices,
        "runtime_api_top": [{"name": name, "count": count, "total_ms": ms(duration)}
                            for name, count, duration in runtime],
        "note": "CUDA activity intervals can overlap; kernel and copy duration sums are not a wall-time decomposition. Runtime API sums can also overlap across CPU threads.",
    }
    db.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "wall_s": result["aggregate"]["seconds"],
                      "devices": {k: {"name": v["name"], "activity_ms": v["activity_union_ms"],
                                      "h2d_MB": v["copies"]["h2d"]["MB"]}
                                  for k, v in devices.items()}}))


if __name__ == "__main__":
    main()
