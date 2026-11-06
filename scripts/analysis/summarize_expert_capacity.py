#!/usr/bin/env python3
"""Capacity bounds for tiered expert placement; never claims a runnable fit."""
import argparse
import json
import math
import pathlib

GIB = 1024 ** 3

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hardware", type=pathlib.Path, required=True)
    p.add_argument("--model", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    p.add_argument("--gpu-reserve-mib", type=int, default=512,
                   help="reserved bytes on each GPU for CUDA/runtime/context")
    p.add_argument("--primary-extra-mib", type=int, default=1536,
                   help="extra reserve on the largest GPU")
    p.add_argument("--ram-reserve-fraction", type=float, default=0.15)
    p.add_argument("--ram-reserve-min-gib", type=float, default=4)
    p.add_argument("--ram-budget-gb", type=float,
                   help="optional measured host allocation ceiling in decimal GB")
    a = p.parse_args()
    if a.gpu_reserve_mib < 0 or a.primary_extra_mib < 0 or not 0 <= a.ram_reserve_fraction < 1:
        p.error("invalid reserve")
    h = json.loads(a.hardware.read_text())
    m = json.loads(a.model.read_text())
    gpus = sorted(h["gpus"], key=lambda x: (-x["memory.total_bytes"], x["index"]))
    gpu_budgets = []
    for i, g in enumerate(gpus):
        reserve = (a.gpu_reserve_mib + (a.primary_extra_mib if i == 0 else 0)) * 1024 ** 2
        gpu_budgets.append({"index": g["index"], "name": g["name"],
                            "total_bytes": g["memory.total_bytes"],
                            "reserve_bytes": reserve,
                            "budget_bytes": max(0, g["memory.total_bytes"] - reserve)})
    mem = h["memory"]
    installed = mem["MemTotal_bytes"]
    available = mem["MemAvailable_bytes"]
    reserved = max(math.ceil(installed * a.ram_reserve_fraction),
                   math.ceil(a.ram_reserve_min_gib * GIB))
    ram_budget = max(0, available - reserved)
    if a.ram_budget_gb is not None:
        ram_budget = min(ram_budget, math.floor(a.ram_budget_gb * 1_000_000_000))
    total = m["model_file_bytes"]
    ngram = m["ngram_tensor_bytes"]
    if ngram > total:
        p.error("ngram tensor bytes exceed model file bytes")
    resident_candidate = total - ngram
    gpu_total = sum(g["budget_bytes"] for g in gpu_budgets)
    after_gpu = max(0, resident_candidate - gpu_total)
    after_ram = max(0, after_gpu - ram_budget)
    report = {"schema": "expert-capacity-bounds/1",
              "hardware_source": str(a.hardware), "model_source": str(a.model),
              "assumptions": {
                  "gpu_reserve_mib": a.gpu_reserve_mib,
                  "primary_extra_mib": a.primary_extra_mib,
                  "ram_reserve_fraction": a.ram_reserve_fraction,
                  "ram_reserve_min_gib": a.ram_reserve_min_gib,
                  "ram_budget_gb": a.ram_budget_gb,
                  "ngram_assigned_to_storage": ngram > 0},
              "gpu_budgets": gpu_budgets, "gpu_budget_sum_bytes": gpu_total,
              "host_installed_bytes": installed, "host_available_bytes": available,
              "host_reserve_bytes": reserved, "host_budget_bytes": ram_budget,
              "model_file_bytes": total, "ngram_tensor_bytes": ngram,
              "model_bytes_for_gpu_or_ram": resident_candidate,
              "unplaced_after_gpu_bytes": after_gpu,
              "unplaced_after_gpu_and_ram_bytes": after_ram,
              "live_storage_read_lower_bound_bytes": ngram + after_ram,
              "fit_status": "unknown",
              "limits": [
                  "Arithmetic capacity bound only: does not compute KV/cache, nonuniform layer sizes, dense copies, compute buffers or quantization kernel support.",
                  "Summed GPU memory is not a unified pool; the selected runtime must implement a feasible model split.",
                  "Storage only extends runnable capacity when the runtime supports streaming the required tensors.",
                  "A validated load, recall test, and measured latency are required before recommending a placement."]}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(a.output), "fit_status": "unknown",
                      "gpu_budget_gib": round(gpu_total/GIB, 2),
                      "ram_budget_gib": round(ram_budget/GIB, 2),
                      "storage_read_floor_gib": round((ngram+after_ram)/GIB, 2)}))

if __name__ == "__main__":
    main()
