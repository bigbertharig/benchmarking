#!/usr/bin/env python3
"""Capacity run: the most a model can do on a set of cards (NEW_MODEL_INTEGRATION.md, "Capacity run").

The rig manager plans the largest context that fits on the cards (`rigctl fit --use chat --profile default`,
its largest-that-fits rule), the model is loaded at exactly that context as a benchmark load (bench mode),
and two probes measure it: a short prompt (decode speed, power) and a prompt filling about --fraction of the
context with a code planted at its start, repeated at several depths (--fractions): prefill speed, time to
first token, decode speed and recall at each depth. Prompt caching is off for every probe. The record goes to results/runtime_experiments/<model>_capacity_g<cards>_ctx<context>_<date>.json (quality_ledger false), and
the model is always unloaded.

Run on the rig (it talks to the runtime port and reads nvidia-smi), as a run so it is in the rig's report:
  rigctl run-start --run capacity-NAME -- python3 \\
    /mnt/shared/plans/shoulders/benchmarking/scripts/integration/capacity_run.py MODEL [--gpus 0,1,2] [--cards N]
Cards: --gpus pins them, --cards N lets the manager pick N (smallest first), neither uses every card.
Context: the largest that fits (capped at the model's trained context), or exactly --ctx N, so runs on
different card sets compare at the same context (a bottleneck matrix: one card vs splits). --depth-of N
probes at the fractions of N instead of the loaded context: the same token counts as runs loaded at N, for a
card set that cannot hold N itself (probes that would not fit the loaded context are skipped).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shlex
import signal
import string
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RX = ROOT / "results" / "runtime_experiments"
HOST = "pi"
RIGCTL = "~/llm-gateway/tools/rigctl.py"
SHORT_PROMPT = ("Write a detailed technical explanation of how a B-tree index works in a relational database: "
                "node structure, search, insertion with node splits, deletion with merges, and why it suits disk "
                "storage. Use numbered sections and keep going until every part is covered thoroughly.")
FILLER = ("Section {n}. The rig log records routine status for each card: fan speed, temperature, power draw "
          "and memory in use. Nothing in this section changes the task. Entries repeat with new numbers, "
          "such as reading {n} at {m} watts and {k} degrees, to make the document long. ")
QUESTION_TOKENS = 256  # question, chat template and answer room left free in the context
DECODE_TOKENS = 160    # tokens generated per depth probe (forced past the answer, for a steady decode rate)
FRACTIONS = "0.1,0.25,0.5,0.75,0.9"


def rigctl(*args: str, timeout: float = 7200) -> tuple[int, dict]:
    """rigctl on the Pi over ssh (arguments quoted for the remote shell); its JSON answer."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", HOST, "python3", RIGCTL,
           *[shlex.quote(str(a)) for a in args]]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try:
        return proc.returncode, json.loads(proc.stdout or "{}")
    except ValueError:
        return proc.returncode, {"error": {"message": (proc.stderr or proc.stdout).strip()[-500:]}}


def fit_args(model: str, gpus: list[int] | None, cards: int | None, margin_mb: int | None,
             ctx: int | None = None) -> list[str]:
    """`rigctl fit` for the largest context on the chosen cards (the default profile's batch and args), or for
    exactly ctx."""
    args = ["fit", model, "--use", "chat", "--profile", "default", "--json"]
    if ctx:
        args += ["--ctx", str(ctx)]
    if gpus:
        args += ["--gpus", ",".join(str(g) for g in gpus)]
    elif cards:
        args += ["--cards", str(cards)]
    if margin_mb is not None:
        args += ["--margin-mb", str(margin_mb)]
    return args


def load_args(model: str, gpus: list[int], ctx: int, owner: str, margin_mb: int | None) -> list[str]:
    """Load exactly what the fit planned, as a benchmark load (bench mode, no prompt cache)."""
    args = ["load-model", model, "--gpus", ",".join(str(g) for g in gpus), "--ctx", str(ctx), "--use", "benchmark",
            "--profile", "default", "--json", "--owner", owner]
    if margin_mb is not None:
        args += ["--margin-mb", str(margin_mb)]
    return args


def repeats_for(target_tokens: int, chunk_tokens: int, head_tokens: int) -> int:
    """Filler chunks that bring the prompt to target_tokens after the head (never fewer than one)."""
    return max(1, (target_tokens - head_tokens) // max(1, chunk_tokens))


def all_gpus() -> list[int]:
    out = subprocess.run(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], capture_output=True,
                         text=True, check=True).stdout
    return [int(x) for x in out.split()]


def post(port: int, path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


class Sampler:
    """1 s nvidia-smi samples of the model's cards: power, temperature, utilization, memory."""

    def __init__(self, gpus: list[int]):
        self.gpus, self.rows, self._stop = gpus, [], threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            out = subprocess.run(["nvidia-smi", "--query-gpu=index,power.draw,temperature.gpu,utilization.gpu,"
                                  "memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                i, p, t, u, m = [x.strip() for x in line.split(",")]
                if int(i) in self.gpus:
                    self.rows.append((int(i), float(p), float(t), float(u), float(m)))
            self._stop.wait(1.0)

    def __enter__(self) -> "Sampler":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()

    def summary(self) -> list[dict]:
        out = []
        for g in self.gpus:
            s = [r for r in self.rows if r[0] == g]
            if not s:
                continue
            busy = [r for r in s if r[3] > 0] or s
            out.append({"gpu": g, "samples": len(s), "avg_power_w": round(sum(r[1] for r in busy) / len(busy), 1),
                        "peak_power_w": max(r[1] for r in s), "peak_temperature_c": max(r[2] for r in s),
                        "peak_memory_mb": max(r[4] for r in s)})
        return out


def chat(port: int, prompt: str, max_tokens: int, timeout: float, force: bool = False) -> tuple[dict, float]:
    """One completion with prompt caching off, so prefill is measured over the whole prompt; force keeps
    generating past the end of the answer, for a steady decode rate."""
    body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens,
            "cache_prompt": False}
    if force:
        body["ignore_eos"] = True
    t0 = time.time()
    resp = post(port, "/v1/chat/completions", body, timeout)
    return resp, time.time() - t0


def probe_result(resp: dict, wall: float, sampler: Sampler) -> dict:
    timings, usage = resp.get("timings", {}), resp.get("usage", {})
    return {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens_per_second": round(timings.get("prompt_per_second", 0), 2),
            "generation_tokens_per_second": round(timings.get("predicted_per_second", 0), 2),
            "time_to_first_token_seconds": round(timings.get("prompt_ms", 0) / 1000, 1),
            "wall_seconds": round(wall, 1), "finish_reason": resp["choices"][0].get("finish_reason"),
            "gpu_envelope": sampler.summary()}


def depth_probe(port: int, ctx: int, fraction: float, gpus: list[int]) -> dict:
    """A prompt of about fraction * ctx tokens with a code at its start; the model must repeat the code."""
    code = "".join(random.choice(string.ascii_uppercase) for _ in range(4)) + str(random.randint(1000, 9999))
    head = f"Remember this code: {code}. You will be asked for it at the end.\n\n"
    question = f"\n\nWhat is the code given at the very start of this document? Reply with only the code."
    chunk = FILLER.format(n=1, m=100, k=50)
    chunk_tokens = len(post(port, "/tokenize", {"content": chunk}, 60)["tokens"])
    head_tokens = len(post(port, "/tokenize", {"content": head + question}, 60)["tokens"])
    target = int(ctx * fraction) - QUESTION_TOKENS  # ctx: the loaded context, or --depth-of's reference
    n = repeats_for(target, chunk_tokens, head_tokens)
    body = "".join(FILLER.format(n=i, m=100 + i % 200, k=40 + i % 40) for i in range(n))
    prompt = head + body + question
    with Sampler(gpus) as s:
        resp, wall = chat(port, prompt, DECODE_TOKENS, timeout=4 * 3600, force=True)
    message = resp["choices"][0]["message"]
    answer = (message.get("content") or "").strip()
    # A thinking model can spend the forced tokens in its reasoning; the code counts as recalled there too.
    reasoning = (message.get("reasoning_content") or "").strip()
    result = probe_result(resp, wall, s)
    result.update(target_fraction=fraction, recall_code=code, answer=answer[:80],
                  recall_ok=code in answer or code in reasoning,
                  recall_in="answer" if code in answer else ("reasoning" if code in reasoning else None))
    return result


def fits_depth(depth_ctx: int, fraction: float, loaded_ctx: int) -> bool:
    """A probe at fraction of depth_ctx fits a runtime loaded at loaded_ctx (with room for the answer)."""
    return int(depth_ctx * fraction) + DECODE_TOKENS <= loaded_ctx


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", model.replace(":", "_").replace(".", "_"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model")
    cards = ap.add_mutually_exclusive_group()
    cards.add_argument("--gpus", help="pin these cards, e.g. 0,1,2,3")
    cards.add_argument("--cards", type=int, help="let the manager pick this many cards")
    ap.add_argument("--ctx", type=int, help="load at exactly this context instead of the largest that fits")
    ap.add_argument("--depth-of", type=int, help="probe at fractions of this context (match runs loaded at it)")
    ap.add_argument("--fractions", default=FRACTIONS, help="depth probes as shares of the context, comma separated")
    ap.add_argument("--margin-mb", type=int, help="headroom per card for the fit (manager default when omitted)")
    ap.add_argument("--skip-depth", action="store_true", help="only the load and the short probe")
    ap.add_argument("--out", help="record path (default results/runtime_experiments/...)")
    a = ap.parse_args()

    gpus = [int(g) for g in a.gpus.split(",")] if a.gpus else (None if a.cards else all_gpus())
    rc, plan = rigctl(*fit_args(a.model, gpus, a.cards, a.margin_mb, a.ctx))
    if rc != 0 or not plan.get("fits"):
        print(f"won't fit: {(plan.get('error') or {}).get('message') or plan.get('reason')}", file=sys.stderr)
        return 4
    gpus, ctx = plan["gpus"], int(plan["ctx"])
    print(f"plan: {a.model} on GPU {gpus} at ctx {ctx} ({plan.get('ctx_limit')}), split {plan.get('tensor_split')}",
          flush=True)

    owner = f"capacity-{slug(a.model)}"[:64]
    # A stopped run (rigctl run-stop, SIGTERM) still cleans up: the finally blocks below run.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(143)))
    t0 = time.time()
    try:
        rc, loaded = rigctl(*load_args(a.model, gpus, ctx, owner, a.margin_mb))
    except BaseException:
        rigctl("cancel-owner", owner, "--reason", "capacity run stopped while loading", timeout=900)
        raise
    load_s = round(time.time() - t0, 1)
    if rc != 0 or loaded.get("state") != "ready":
        print(f"load failed: {(loaded.get('error') or {}).get('message')}", file=sys.stderr)
        rigctl("cancel-owner", owner, "--reason", "capacity run load failed", timeout=900)
        return 1
    port, profile = int(loaded["port"]), loaded["profile"]
    print(f"loaded {profile} on :{port} in {load_s}s, ctx {loaded.get('ctx')}", flush=True)

    record = {
        "schema_version": 1,
        "kind": "capacity",
        "quality_ledger": False,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "Capacity run: the largest context on these cards and how the model runs at it.",
        "methodology": {"id": "llama-server/capacity", "version": "1.0.0", "sampling_interval_seconds": 1,
                        "plan": ("rigctl fit --use chat --profile default "
                                 + (f"--ctx {a.ctx} (fixed)" if a.ctx else "(largest that fits)")),
                        "depth_fractions": [float(f) for f in a.fractions.split(",")],
                        "depth_of_ctx": a.depth_of,
                        "decode_tokens_per_depth_probe": DECODE_TOKENS, "cache_prompt": False},
        "model": a.model,
        "cards": gpus,
        "plan": {k: plan.get(k) for k in ("ctx", "ctx_limit", "tensor_split", "margin_mb", "weights_mb", "n_ctx_train",
                                          "cards")},
        "load": {"seconds": load_s, "profile": profile, "port": port, "ctx_allocated": loaded.get("ctx"),
                 "measured": loaded.get("measured")},
    }
    try:
        with Sampler(gpus) as s:
            resp, wall = chat(port, SHORT_PROMPT, 512, timeout=1800)
        record["short_probe"] = probe_result(resp, wall, s)
        print(f"short: decode {record['short_probe']['generation_tokens_per_second']} tok/s", flush=True)
        if not a.skip_depth:
            record["depth_probes"] = []
            loaded_ctx = int(loaded.get("ctx") or ctx)
            depth_ctx = a.depth_of or loaded_ctx
            for fraction in sorted(float(f) for f in a.fractions.split(",")):
                if not fits_depth(depth_ctx, fraction, loaded_ctx):
                    print(f"depth {fraction:.2f} of {depth_ctx}: skipped, more than the loaded ctx {loaded_ctx}",
                          flush=True)
                    continue
                lp = depth_probe(port, depth_ctx, fraction, gpus)
                record["depth_probes"].append(lp)
                print(f"depth {fraction:.2f}: {lp['prompt_tokens']} prompt tokens, prefill "
                      f"{lp['prompt_tokens_per_second']} tok/s, first token {lp['time_to_first_token_seconds']} s, "
                      f"decode {lp['generation_tokens_per_second']} tok/s, recall "
                      f"{'ok' if lp['recall_ok'] else 'FAILED'}", flush=True)
    except Exception as exc:  # keep what was measured; the unload below still runs
        record["error"] = f"{type(exc).__name__}: {exc}"
        print(f"probe failed: {record['error']}", file=sys.stderr)
    finally:
        rigctl("unload", profile, timeout=900)

    stamp = datetime.now().strftime("%Y%m%d")
    out = Path(a.out) if a.out else RX / (f"{slug(a.model)}_capacity_g{'-'.join(str(g) for g in gpus)}"
                                          f"_ctx{loaded.get('ctx') or ctx}_{stamp}.json")
    record["experiment_id"] = out.stem
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"record: {out}")
    # Keep the generated runtime reference current (results/RUNTIME_REFERENCE.md).
    subprocess.run([sys.executable, str(ROOT / "scripts" / "active" / "build_runtime_reference.py")], check=False)
    return 1 if "error" in record else 0


if __name__ == "__main__":
    raise SystemExit(main())
