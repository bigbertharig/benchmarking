#!/usr/bin/env python3
"""Summarize UUID-verified CUDA work in one model weight-split decode trace."""
import argparse
import json
import re
import sqlite3
from pathlib import Path


def ms(ns):
    return round((ns or 0) / 1_000_000, 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sqlite", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--cuda-map", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    log = args.log.read_text(errors="replace")
    cuda_map = json.loads(args.cuda_map.read_text())
    host_by_cuda = {int(cuda): int(host) for host, cuda in cuda_map["host_to_cuda"].items()}
    identity_by_cuda = {int(item["cuda_id"]): item for item in cuda_map["cuda_devices"]}
    metric = re.search(r"GEN_METRIC phase=(\S+) name=(\w+) used=(\d+) tokens=(\d+) "
                       r"seconds=([\d.]+) tps=([\d.]+) first_ms=([\d.]+) "
                       r"p50_ms=([\d.]+) p95_ms=([\d.]+)", log)
    if not metric:
        raise RuntimeError("decode metric absent")
    placement = re.search(r"MODEL_PLACEMENT devices=([^\s]+) split=([^\s]+)", log)
    if not placement:
        raise RuntimeError("model split placement absent")
    buffers = {int(cuda): float(mib) for cuda, mib in re.findall(
        r"CUDA(\d+) model buffer size =\s*([\d.]+) MiB", log
    )}
    db = sqlite3.connect(args.sqlite)
    devices = {}
    rows = db.execute("SELECT cuDevice,name,busLocation,uuid FROM TARGET_INFO_GPU ORDER BY cuDevice")
    for cuda, name, bus, uuid in rows:
        identity = identity_by_cuda.get(cuda)
        host = host_by_cuda.get(cuda)
        if (identity is None or host is None or identity["pci_bus_id"].lower() != bus.lower()
                or cuda_map["host_gpu_uuids"][str(host)].removeprefix("GPU-").lower() != uuid.lower()):
            raise RuntimeError(f"Nsight CUDA device {cuda} disagrees with captured PCI/UUID map")
        kernel_rows = db.execute(
            "SELECT k.start,k.end,s.value FROM CUPTI_ACTIVITY_KIND_KERNEL k "
            "JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId=?", (cuda,)
        ).fetchall()
        copy_rows = db.execute(
            "SELECT start,end,bytes,copyKind FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE deviceId=?",
            (cuda,)
        ).fetchall()
        copies = {}
        for kind, label in ((1, "h2d"), (2, "d2h"), (3, "d2d")):
            selected = [(start, end, size) for start, end, size, copy_kind in copy_rows if copy_kind == kind]
            copies[label] = {"count": len(selected),
                             "MB": round(sum(size for _, _, size in selected) / 1e6, 3),
                             "duration_ms": ms(sum(end-start for start, end, _ in selected))}
        top = db.execute(
            "SELECT s.value,COUNT(*),SUM(k.end-k.start) FROM CUPTI_ACTIVITY_KIND_KERNEL k "
            "JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId=? "
            "GROUP BY s.value ORDER BY SUM(k.end-k.start) DESC LIMIT 5", (cuda,)
        ).fetchall()
        large_d2h = db.execute(
            "SELECT COUNT(*),SUM(end-start) FROM CUPTI_ACTIVITY_KIND_MEMCPY "
            "WHERE deviceId=? AND copyKind=2 AND bytes=993280", (cuda,)
        ).fetchone()
        devices[str(cuda)] = {
            "host_gpu": host, "name": name, "bus": bus, "uuid": uuid,
            "model_buffer_mib": buffers.get(cuda, 0.0),
            "kernel_count": len(kernel_rows),
            "kernel_duration_ms": ms(sum(end-start for start, end, _ in kernel_rows)),
            "top_kernels": [{"name": kernel_name, "count": count, "duration_ms": ms(duration)}
                            for kernel_name, count, duration in top],
            "copies": copies,
            "d2h_993280_byte_copies": {"count": large_d2h[0], "duration_ms": ms(large_d2h[1])},
        }
    result = {
        "model_placement": {"cuda_devices": placement.group(1), "split": placement.group(2)},
        "decode": {"phase": metric.group(1), "chat": metric.group(2),
                   "used": int(metric.group(3)), "tokens": int(metric.group(4)),
                   "seconds": float(metric.group(5)), "tps": float(metric.group(6)),
                   "first_ms": float(metric.group(7)), "p50_ms": float(metric.group(8)),
                   "p95_ms": float(metric.group(9))},
        "devices": devices,
        "note": "Kernel and copy durations are summed GPU activities, not a wall-time decomposition. D2H/H2D are CUPTI copy directions; a direct peer endpoint is not inferred.",
    }
    db.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "tps": result["decode"]["tps"],
                      "devices": {key: {"name": item["name"], "weight_mib": item["model_buffer_mib"],
                                        "kernels": item["kernel_count"],
                                        "d2h_MB": item["copies"]["d2h"]["MB"]}
                                  for key, item in devices.items()}}))


if __name__ == "__main__":
    main()
