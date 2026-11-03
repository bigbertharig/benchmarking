#!/usr/bin/env python3
"""Compare one GGUF on CPU RAM, partial GPU offload, and two full GPU placements.

Run on the idle rig. This is an experimental llama-server load outside the
gateway's full-offload policy; it does not alter published model profiles.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

IMAGE = "llama-runtime:b11669"
MODEL = Path("/data/model-hotset/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf")
PORT = 18123
NAME = "ram-offload-comparison"
MODES = (
    ("cpu_ram", "-1", "0"),
    ("1060_partial_20", "1", "20"),
    ("1060_full", "1", "all"),
    ("3090_full", "0", "all"),
)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


def write(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def gpu_memory_mib() -> list[int]:
    output = run("nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits").stdout
    return [int(line.strip()) for line in output.splitlines()]


def request(path: str, body: dict | None = None, timeout: float = 30) -> dict:
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def ready(timeout: float = 240) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if run("docker", "inspect", "-f", "{{.State.Running}}", NAME, check=False).stdout.strip() != "true":
            log_tail = run("docker", "logs", NAME, check=False).stderr[-1200:]
            raise RuntimeError(f"llama-server exited before ready: {log_tail}")
        try:
            if request("/health", timeout=2).get("status") == "ok":
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise TimeoutError("llama-server did not become ready within 240s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--model", type=Path, default=MODEL,
                    help="GGUF file to test (default: Qwen3.5 4B)")
    ap.add_argument("--ctx", type=int, default=32768,
                    help="llama.cpp context size (default: 32768)")
    ap.add_argument("--only-mode", choices=[mode for mode, _, _ in MODES],
                    help="run only one placement, for a targeted repeat")
    args = ap.parse_args()
    if args.ctx < 512:
        ap.error("--ctx must be at least 512")
    modes = tuple(mode for mode in MODES if not args.only_mode or mode[0] == args.only_mode)
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    containers = run("docker", "ps", "--format", "{{.Names}}").stdout.splitlines()
    if NAME in containers:
        raise RuntimeError(f"benchmark container {NAME} is already running")
    if gpu_memory_mib()[0] > 1024:
        raise RuntimeError("GPU 0 is in use; wait for a free 3090")
    power = run("nvidia-smi", "--query-gpu=index,power.limit", "--format=csv,noheader,nounits").stdout
    actual = [round(float(line.split(",")[1])) for line in power.splitlines()]
    if actual != [350, 100, 100, 100, 100, 100]:
        raise RuntimeError(f"unexpected power caps {actual}")
    state: dict = {"model": str(args.model), "image": IMAGE, "started_at": stamp(),
                   "context": args.ctx, "batch": 64, "threads": 4,
                   "power_caps_w": actual, "baseline_gpu_memory_mib": gpu_memory_mib(), "modes": {}}
    write(args.output / "checkpoint.json", state)
    prompt = ("Explain how a B-tree index serves searches, inserts, and deletes in a database. "
              "Include what happens during node splits and merges. " * 55)
    body = {"prompt": prompt, "n_predict": 128, "temperature": 0,
            "cache_prompt": False, "ignore_eos": True, "stream": False}
    for mode, visible, layers in modes:
        row: dict = {"started_at": stamp(), "gpu_visible": visible,
                     "gpu_layers_requested": layers, "status": "running"}
        state["modes"][mode] = row
        write(args.output / "checkpoint.json", state)
        run("docker", "rm", "-f", NAME, check=False)
        cmd = ["docker", "run", "--detach", "--gpus", "all", "--network", "host",
               "--name", NAME, "--env", f"CUDA_VISIBLE_DEVICES={visible}",
               "--volume", f"{args.model.parent}:/models:ro", "--entrypoint", "/opt/llama/bin/llama-server",
               IMAGE, "--model", f"/models/{args.model.name}", "--host", "127.0.0.1",
               "--port", str(PORT), "--ctx-size", str(args.ctx), "--batch-size", "64",
               "--ubatch-size", "64", "--parallel", "1", "--threads", "4",
               "--threads-batch", "4", "--load-mode", "none", "--gpu-layers", layers,
               "--slot-prompt-similarity", "0", "--log-verbosity", "4"]
        try:
            t0 = time.monotonic()
            launched = run(*cmd)
            row["container_id"] = launched.stdout.strip()[:12]
            ready()
            row["load_seconds"] = round(time.monotonic() - t0, 2)
            row["gpu_memory_after_load_mib"] = gpu_memory_mib()
            row["server_log"] = str(args.output / f"{mode}.log")
            for repeat in (1, 2):
                t1 = time.monotonic()
                response = request("/completion", body, timeout=600)
                row[f"repeat_{repeat}"] = {
                    "wall_seconds": round(time.monotonic() - t1, 2),
                    "timings": response.get("timings"),
                    "tokens_predicted": response.get("tokens_predicted"),
                    "tokens_evaluated": response.get("tokens_evaluated"),
                    "stopped_eos": response.get("stopped_eos"),
                    "stopped_limit": response.get("stopped_limit"),
                }
            row["status"] = "passed"
            print(f"{mode}: {row['repeat_2']['timings']}", flush=True)
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"{mode}: {row['error']}", flush=True)
        finally:
            (args.output / f"{mode}.log").write_text(
                run("docker", "logs", NAME, check=False).stderr, encoding="utf-8")
            run("docker", "rm", "-f", NAME, check=False)
            row["finished_at"] = stamp()
            write(args.output / "checkpoint.json", state)
            if row["status"] != "passed":
                break
    state["finished_at"] = stamp()
    state["status"] = ("passed" if len(state["modes"]) == len(modes) and
                       all(row["status"] == "passed" for row in state["modes"].values()) else "failed")
    write(args.output / "terminal.json", state)
    return 0 if state["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
