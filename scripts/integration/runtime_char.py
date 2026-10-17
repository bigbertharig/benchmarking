"""NEW_MODEL_INTEGRATION Phase 3.5: sustained decode + 1 s GPU envelope for the model on a port.

usage: runtime_char.py <model-id> <port> <gpu-index[,gpu...]> <load_s> <load_source> <out.json> [k=v runtime facts...]
"""
import json, subprocess, sys, threading, time, urllib.request
from datetime import datetime

model, port, gpus, load_s, load_source, out = sys.argv[1:7]
facts = dict(a.split("=", 1) for a in sys.argv[7:])
gpu_ids = [int(g) for g in gpus.split(",")]
PROMPT = ("Write a detailed technical explanation of how a B-tree index works in a relational database: "
          "node structure, search, insertion with node splits, deletion with merges, and why it suits disk "
          "storage. Use numbered sections and keep going until every part is covered thoroughly.")

samples, stop = [], threading.Event()
def sample():
    while not stop.is_set():
        out_ = subprocess.run(["nvidia-smi", "--query-gpu=index,power.draw,temperature.gpu,utilization.gpu,clocks.sm",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
        t = time.time()
        for line in out_.splitlines():
            i, p, temp, util, clk = [x.strip() for x in line.split(",")]
            if int(i) in gpu_ids:
                samples.append((t, int(i), float(p), float(temp), float(util), float(clk)))
        stop.wait(1.0)

body = {"messages": [{"role": "user", "content": PROMPT}], "temperature": 0, "max_tokens": 768,
        "min_tokens": 512, "ignore_eos": False}
th = threading.Thread(target=sample); th.start()
t0 = time.time()
req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", json.dumps(body).encode(),
                             {"Content-Type": "application/json"})
resp = json.load(urllib.request.urlopen(req, timeout=900))
wall = time.time() - t0
stop.set(); th.join()

timings = resp.get("timings", {})
usage = resp.get("usage", {})
per_gpu = []
for g in gpu_ids:
    s = [x for x in samples if x[1] == g]
    busy = [x for x in s if x[4] > 0] or s
    per_gpu.append({
        "gpu": g,
        "samples": len(s),
        "avg_power_w": round(sum(x[2] for x in busy) / len(busy), 1),
        "peak_power_w": max(x[2] for x in s),
        "peak_temperature_c": max(x[3] for x in s),
        "avg_utilization_pct": round(sum(x[4] for x in busy) / len(busy), 1),
        "avg_sm_clock_mhz": round(sum(x[5] for x in busy) / len(busy)),
    })
combined_avg = round(sum(g["avg_power_w"] for g in per_gpu), 1)
record = {
    "schema_version": 1,
    "experiment_id": out.rsplit("/", 1)[-1].removesuffix(".json"),
    "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "purpose": "NEW_MODEL_INTEGRATION Phase 3.5 runtime characterization (first load, sustained decode, GPU envelope).",
    "kind": "runtime_characterization",
    "quality_ledger": False,
    "methodology": {"id": "llama-server/sustained-decode-envelope", "version": "1.0.0",
                    "sampling_interval_seconds": 1},
    "model": model,
    "runtime": facts,
    "first_load": {"seconds": float(load_s), "source": load_source},
    "decode": {
        "completion_tokens": usage.get("completion_tokens"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "generation_tokens_per_second": round(timings.get("predicted_per_second", 0), 2),
        "prompt_tokens_per_second": round(timings.get("prompt_per_second", 0), 2),
        "wall_seconds": round(wall, 1),
        "finish_reason": resp["choices"][0].get("finish_reason"),
    },
    "gpu_envelope": per_gpu,
    "combined_avg_gpu_power_w": combined_avg,
    "decode_energy_wh": round(combined_avg * wall / 3600, 3),
}
open(out, "w").write(json.dumps(record, indent=2) + "\n")
print(json.dumps({k: record[k] for k in ("first_load", "decode", "gpu_envelope", "combined_avg_gpu_power_w", "decode_energy_wh")}, indent=1))
