#!/usr/bin/env python3
"""power_cap_sweep: speed and power of one card at a series of power caps, run from the controller.

    python3 tools/power_cap_sweep.py --gpu 0 --model qwen3.6:27b --caps 450,400,350,300
    python3 tools/power_cap_sweep.py --gpu 3 --model qwen2.5-coder:7b --caps 120,100,90,80

The model is loaded once with `rigctl load-model`. For each cap the card's limit is set through the rig's
temporary override (/run/rig/power_override.json, by_index; cleared at boot, so a crash brings the planned
caps back), then --runs requests are timed after one warm-up: llama-server's own timings give decode and
prompt-processing tokens/s, and nvidia-smi on the rig samples the card every 500 ms during the requests.
Decode is mostly memory-bound and prompt processing compute-bound, so a cap shows up in them differently.

Output: ~/rig_stress/power_cap_<time>/summary.json (per cap: tok/s, average and peak power, joules per
generated token, SM clock, temperature) and samples.csv. The override is removed and the model unloaded
at the end unless --keep-loaded.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RIGCTL = [sys.executable, str(HERE / "rigctl.py")]
RIG = "10.0.0.3"
# A long prompt (prompt processing is measured on it) asking for a long answer (decode).
PROMPT = ("Here is a log of a lighthouse keeper's week. " * 120 +
          "\n\nWrite a long, detailed continuation of this log, day by day, with dialogue. Do not summarize.")


def sh(cmd: str, timeout: int = 120) -> str:
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=10", RIG, cmd], capture_output=True, text=True, timeout=timeout)
    return (p.stdout + p.stderr).strip()


def set_cap(gpu: int, watts: int | None) -> str:
    if watts is None:
        sh("sudo -n rm -f /run/rig/power_override.json && sudo -n systemctl restart rig-power.service")
    else:
        rules = json.dumps({"by_model": {}, "by_index": {str(gpu): watts}})
        sh(f"sudo -n mkdir -p /run/rig && echo '{rules}' | sudo -n tee /run/rig/power_override.json >/dev/null"
           " && sudo -n systemctl restart rig-power.service")
    return sh(f"nvidia-smi -i {gpu} --query-gpu=power.limit --format=csv,noheader,nounits").strip()


def request(port: int, max_tokens: int) -> dict:
    body = json.dumps({"model": "x", "messages": [{"role": "user", "content": PROMPT}],
                       "max_tokens": max_tokens, "temperature": 0.7, "cache_prompt": False}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read()).get("timings") or {}


class Sampler:
    def __init__(self, gpu: int, out: Path):
        self.gpu, self.label, self.rows, self.stop = gpu, "setup", [], threading.Event()
        self.file = open(out, "w", newline="")
        self.w = csv.writer(self.file)
        self.w.writerow(["t", "label", "power_w", "sm_mhz", "temp_c", "fan_pct"])

    def run(self) -> None:
        cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=5", RIG,
               f"nvidia-smi -i {self.gpu} --query-gpu=power.draw.instant,clocks.sm,temperature.gpu,fan.speed "
               "--format=csv,noheader,nounits -lms 500"]
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as p:
            for line in p.stdout:
                if self.stop.is_set():
                    break
                parts = [x.strip() for x in line.split(",")]
                try:
                    vals = [float(x) for x in parts]
                except ValueError:
                    continue
                row = [round(time.time(), 2), self.label, *vals]
                self.rows.append(row)
                self.w.writerow(row)
                self.file.flush()
            p.terminate()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--caps", required=True, help="watts, comma separated, in the order to run them")
    ap.add_argument("--runs", type=int, default=3, help="timed requests per cap (after one warm-up)")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--keep-loaded", action="store_true")
    a = ap.parse_args()
    caps = [int(c) for c in a.caps.split(",")]
    out = Path.home() / "rig_stress" / time.strftime("power_cap_%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(out / "events.log", "a") as f:
            f.write(line + "\n")

    p = subprocess.run(RIGCTL + ["load-model", a.model, "--gpus", str(a.gpu), "--use", "benchmark", "--json"],
                       capture_output=True, text=True)
    loaded = json.loads(p.stdout or "{}")
    if loaded.get("state") != "ready":
        log(f"load failed: {p.stdout[-400:]}{p.stderr[-400:]}")
        return 1
    port = int(loaded.get("port") or 11434 + a.gpu)
    log(f"loaded {a.model} on GPU {a.gpu} :{port} ctx {loaded.get('ctx')}; caps {caps}")
    sampler = Sampler(a.gpu, out / "samples.csv")
    threading.Thread(target=sampler.run, daemon=True).start()
    results = []
    try:
        for cap in caps:
            limit = set_cap(a.gpu, cap)
            sampler.label = f"warm{cap}"
            request(port, a.max_tokens)
            sampler.label = f"cap{cap}"
            t0 = time.time()
            timings = [request(port, a.max_tokens) for _ in range(a.runs)]
            t1 = time.time()
            rows = [r for r in sampler.rows if r[1] == f"cap{cap}" and t0 <= r[0] <= t1]
            power = [r[2] for r in rows]
            decode = sum(t.get("predicted_per_second", 0) for t in timings) / len(timings)
            prompt = sum(t.get("prompt_per_second", 0) for t in timings) / len(timings)
            avg_w = sum(power) / len(power) if power else None
            res = {"cap_w": cap, "limit_reported_w": limit, "runs": a.runs,
                   "decode_tok_s": round(decode, 2), "prompt_tok_s": round(prompt, 1),
                   "prompt_tokens": timings[0].get("prompt_n"), "generated_tokens": timings[0].get("predicted_n"),
                   "power_avg_w": round(avg_w, 1) if avg_w else None, "power_max_w": max(power) if power else None,
                   "joules_per_token": round(avg_w / decode, 2) if avg_w and decode else None,
                   "sm_avg_mhz": round(sum(r[3] for r in rows) / len(rows)) if rows else None,
                   "temp_max_c": max(r[4] for r in rows) if rows else None,
                   "fan_max_pct": max(r[5] for r in rows) if rows else None, "samples": len(rows)}
            results.append(res)
            log(f"cap {cap} W (reported {limit}): decode {res['decode_tok_s']} tok/s, prompt {res['prompt_tok_s']} "
                f"tok/s, power avg {res['power_avg_w']} max {res['power_max_w']} W, {res['joules_per_token']} J/token, "
                f"SM {res['sm_avg_mhz']} MHz, max {res['temp_max_c']} C")
    finally:
        sampler.stop.set()
        log("caps restored: " + set_cap(a.gpu, None) + " W on GPU " + str(a.gpu))
        if not a.keep_loaded and loaded.get("profile"):
            subprocess.run(RIGCTL + ["unload", loaded["profile"]], capture_output=True, text=True)
            log("model unloaded")
    base = results[0] if results else None
    for r in results:
        if base and base["decode_tok_s"]:
            r["decode_vs_first_pct"] = round(100 * (r["decode_tok_s"] / base["decode_tok_s"] - 1), 1)
            r["prompt_vs_first_pct"] = round(100 * (r["prompt_tok_s"] / base["prompt_tok_s"] - 1), 1)
    (out / "summary.json").write_text(json.dumps({"gpu": a.gpu, "model": a.model, "max_tokens": a.max_tokens,
                                                  "results": results}, indent=2))
    log(f"summary {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
