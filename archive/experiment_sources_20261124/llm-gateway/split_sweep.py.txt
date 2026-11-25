"""Split-scaling sweep: same model on 1..5 cards, then prefill batch sizes on the 5-card split.

Usage: python3 split_sweep.py LABEL [--role ROLE | --model MODEL]   (writes ~/rig_stress/split_sweep_<LABEL>.json)
The model defaults to the benchmarking role single_1060 (tools/role_model.py), so it follows model_roles.json.
Run from the controller; loads go through the harness (rigctl.py next to this file).
"""
import argparse, json, random, statistics, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import role_model  # noqa: E402

_ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
_ap.add_argument("label", nargs="?", default="run")
_ap.add_argument("--role", default=role_model.DEFAULT_ROLE)
_ap.add_argument("--model", help="model id; overrides --role")
_args = _ap.parse_args()
LABEL = _args.label
MODEL = _args.model or role_model.resolve(_args.role)["model"]
CTX = 8192
RIGCTL = [sys.executable, str(Path(__file__).resolve().parent / "rigctl.py")]
OUT = Path.home() / f"rig_stress/split_sweep_{LABEL}.json"

HOP_CONFIGS = [[1], [1, 2], [1, 3], [1, 2, 4], [1, 2, 4, 5], [1, 2, 4, 5, 3]]
UBATCH_GPUS = [1, 2, 4, 5, 3]
UBATCHES = [128, 512, 2048]

FILLER = ("The rig logs temperature, fan speed, power draw and clock for every card each half second. "
          "Operators compare runs by card identity so moving boards between slots keeps history intact. ")


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def rigctl(*args, timeout=900):
    p = subprocess.run(RIGCTL + list(args), capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"rigctl {' '.join(args)} failed: {(p.stderr or p.stdout).strip()[-400:]}")
    return p.stdout


def chat(port, content, max_tokens):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps({
        "model": "x", "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens, "temperature": 0}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["timings"]


def bench(port, reps=3):
    chat(port, "warm up", 16)
    dec, pre = [], []
    for _ in range(reps):
        t = chat(port, f"Run {random.randint(0, 10**9)}. Explain PCIe link training step by step in detail.", 256)
        dec.append(t["predicted_per_second"])
    for _ in range(reps):
        t = chat(port, f"Run {random.randint(0, 10**9)}.\n" + FILLER * 110 + "\nReply with one word.", 1)
        pre.append(t["prompt_per_second"])
        prompt_n = t["prompt_n"]
    return {"decode_tps": round(statistics.median(dec), 2), "decode_ms_per_tok": round(1000 / statistics.median(dec), 2),
            "prefill_tps": round(statistics.median(pre), 1), "prefill_prompt_tokens": prompt_n,
            "decode_runs": [round(x, 2) for x in dec], "prefill_runs": [round(x, 1) for x in pre]}


def run_config(gpus, extra_args=None):
    args = ["load-model", MODEL, "--gpus", ",".join(map(str, gpus)), "--ctx", str(CTX), "--use", "benchmark", "--json"]
    if extra_args:
        args += ["--args", extra_args]
    t0 = time.time()
    info = json.loads(rigctl(*args))
    load_s = round(time.time() - t0)
    try:
        res = bench(info["port"])
    finally:
        rigctl("unload", info["profile"], timeout=300)
    row = {"gpus": gpus, "cards": len(gpus), "hops": len(gpus) - 1, "extra_args": extra_args,
           "tensor_split": info.get("tensor_split"), "load_s": load_s, **res}
    log(f"gpus {gpus} args {extra_args or '-'}: decode {res['decode_tps']} tok/s ({res['decode_ms_per_tok']} ms/tok), "
        f"prefill {res['prefill_tps']} tok/s on {res['prefill_prompt_tokens']} tokens, load {load_s} s")
    return row


rows = []
log(f"split sweep {LABEL}: {MODEL} ctx {CTX}")
for gpus in HOP_CONFIGS:
    rows.append(run_config(gpus))
    OUT.write_text(json.dumps({"label": LABEL, "model": MODEL, "ctx": CTX, "rows": rows}, indent=1))
for ub in UBATCHES:
    rows.append(run_config(UBATCH_GPUS, f"-b 2048 -ub {ub}"))
    OUT.write_text(json.dumps({"label": LABEL, "model": MODEL, "ctx": CTX, "rows": rows}, indent=1))
log(f"done: {OUT}")
