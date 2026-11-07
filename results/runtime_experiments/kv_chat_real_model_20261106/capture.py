from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

base = Path("/data/bench-staging/strata-v0.2.10/install/third_party/llama.cpp")
work = Path("/mnt/shared/experiments/kvchat-20261106")
private = work / "llama.cpp"
out = Path("/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/kv_chat_real_model_20261106")
out.mkdir(parents=True, exist_ok=True)

paths = ["src/llama-kv-cache.cpp", "src/llama-context.cpp", "src/llama-graph.cpp",
         "examples/simple/simple.cpp"]
diff = []
source_hashes = {}
for path in paths:
    old = (base / path).read_text().splitlines(keepends=True)
    new = (private / path).read_text().splitlines(keepends=True)
    source_hashes[path] = hashlib.sha256((base / path).read_bytes()).hexdigest()
    diff.extend(difflib.unified_diff(old, new, fromfile="a/" + path, tofile="b/" + path))
(out / "private_llama_kv.patch").write_text("".join(diff))

files = ["patch.py", "fix_devices.py", "extend_five.py", "build.sh", "run.sh", "run_moe.sh",
         "run_27b.sh", "build.log", "build.start", "build.finish", "build.exit",
         "run-v1.log", "run-v1.start", "run-v1.finish", "run-v1.exit", "gpu_samples-v1.csv",
         "run-v2.log", "run-v2.start", "run-v2.finish", "run-v2.exit", "gpu_samples-v2.csv",
         "run.log", "run.start", "run.finish", "run.exit", "gpu_samples.csv",
         "moe_run.log", "moe_run.start", "moe_run.finish", "moe_run.exit", "moe_gpu_samples.csv",
         "dense27_run.log", "dense27_run.start", "dense27_run.finish", "dense27_run.exit", "dense27_gpu_samples.csv"]
for name in files:
    source = work / name
    if source.is_file():
        shutil.copy2(source, out / name)

def summarize(prefix: str) -> dict:
    log = work / f"{prefix}.log"
    if not log.is_file():
        return {}
    text = log.read_text(errors="replace")
    sample = work / ("gpu_samples.csv" if prefix == "run" else f"{prefix.replace('_run', '')}_gpu_samples.csv")
    peaks = {}
    if sample.is_file():
        for line in sample.read_text(errors="replace").splitlines():
            match = re.search(r",\s*([0-5]),\s*(\d+) MiB", line)
            if match:
                gpu, used = match.groups()
                peaks[gpu] = max(peaks.get(gpu, 0), int(used))
    exit_path = work / f"{prefix}.exit"
    return {
        "exit": int(exit_path.read_text().strip()) if exit_path.is_file() else None,
        "chat_first_tokens": re.findall(r"CHAT (\d+) step 0 token \d+ text (.*)", text),
        "kv_buffers": re.findall(r"llama_kv_cache:\s+CUDA(\d+) KV buffer size =\s+([\d.]+) MiB", text),
        "model_buffer_mib": re.findall(r"CUDA0 model buffer size =\s+([\d.]+) MiB", text),
        "sampled_peak_mib": peaks,
    }

manifest = {
    "base": str(base),
    "private_source": str(private),
    "base_file_sha256": source_hashes,
    "runs": {"dense_1_7b_5x32k": summarize("run"),
             "moe_20b_5x32k": summarize("moe_run"),
             "dense_27b_5x32k": summarize("dense27_run")},
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest["runs"], indent=2))
