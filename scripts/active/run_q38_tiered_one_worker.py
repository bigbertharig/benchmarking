#!/usr/bin/env python3
"""Matched one-worker extension of the verified Qwen3.8 expert-tier probe."""
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path("/mnt/shared/plans/shoulders/benchmarking")
SOURCE = pathlib.Path("/data/bench-staging/q38_tiered_expert_probe_20261106")
SAMPLE = pathlib.Path("/data/bench-staging/q38_tiered_expert_probe_20261106_1worker")
OUT = ROOT / "results/runtime_experiments/q38_tiered_expert_probe_20261106/one_worker_20261106.json"
LOG = OUT.with_suffix(".log")
MODES = {"gpu0", "gpu0_ram", "gpu0_nvme", "resident", "ram", "nvme"}

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def main():
    record = {"schema": "q38-tiered-one-worker/1", "started_at": utc(),
              "source_sample": str(SOURCE), "sample": str(SAMPLE), "status": "running"}
    try:
        info = json.loads((SOURCE / "sample.json").read_text())
        full = (SOURCE / "full.bin").read_bytes()
        digest = hashlib.sha256(full).hexdigest()
        if digest != info["full_sha256"] or len(full) != 1382400:
            raise ValueError("source expert sample hash or size mismatch")
        SAMPLE.mkdir(parents=True, exist_ok=True)
        for name in ("full.bin", "full_direct.bin", "reference.f32"):
            shutil.copyfile(SOURCE / name, SAMPLE / name)
        shard = full + bytes(-len(full) % 4096)
        (SAMPLE / "shard_0.bin").write_bytes(shard)
        record["full_sha256"] = digest
        record["sample_bytes"] = len(full)
        cmd = ["docker", "run", "--rm", "--gpus", "all", "--network", "none",
               "-e", "WORKERS=1", "-v", f"{ROOT}:/bench:ro",
               "-v", f"{SAMPLE}:/sample",
               "nvidia/cuda:12.9.2-devel-ubuntu24.04",
               "bash", "/bench/scripts/active/run_q38_tiered_expert_probe.sh"]
        record["command"] = cmd
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        LOG.write_text(result.stdout + "\n--- STDERR ---\n" + result.stderr)
        record["exit_code"] = result.returncode
        rows = []
        for line in result.stdout.splitlines():
            if line.startswith("{"):
                rows.append(json.loads(line))
        record["runs"] = rows
        if result.returncode or {x["mode"] for x in rows} != MODES:
            raise RuntimeError("probe failed or missing mode; see log")
        if any(x.get("max_abs_error", 1) > 0.00012 for x in rows):
            raise RuntimeError("correctness tolerance exceeded")
        record["status"] = "passed"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = repr(exc)
    finally:
        record["finished_at"] = utc()
        OUT.write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps({"status": record["status"], "output": str(OUT),
                          "error": record.get("error")}), flush=True)
    return 0 if record["status"] == "passed" else 1

if __name__ == "__main__":
    sys.exit(main())
