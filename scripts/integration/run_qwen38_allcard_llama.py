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

from hardware_inventory import scan_cards, require_ids, docker_devices, check_planned_power

IMAGE = "llama-runtime:b11669"
MODEL = Path("/data/model-hotset/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf")
PORT = 18123
NAME = "ram-offload-comparison"
MODES = (
    ("cpu_ram", "-1", "0"),
    ("1060_partial_20", "1", "20"),
    ("1060_full", "1", "all"),
    ("3090_full", "0", "all"),
    ("four_gpus", "0,1,2,3", "all"),
    ("five_gpus", "0,1,2,3,4", "all"),
    ("all_gpus", "0,1,2,3,4,5", "all"),
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


def memory() -> dict[str, int]:
    result = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"MemAvailable", "SwapFree", "SwapTotal", "Cached"}:
            result[key + "_kib"] = int(value.split()[0])
    return result


def nvme_read_bytes() -> int:
    return int(Path("/sys/block/nvme0n1/stat").read_text().split()[2]) * 512


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
    ap.add_argument("--gpu-layers", type=int,
                    help="override GPU layer count for --only-mode 3090_full; records a partial placement")
    ap.add_argument("--load-timeout", type=float, default=240,
                    help="seconds to wait for server readiness (default: 240)")
    ap.add_argument("--depth-fractions", help="Run the existing capacity_run 10%/90% marker probes")
    ap.add_argument("--kv-type", choices=("f16", "q8_0", "q4_0"), default="f16")
    ap.add_argument("--resident-ngram", action="store_true",
                    help="load per_layer_token_embd into CPU RAM instead of lazy file reads")
    ap.add_argument("--memory-limit-gib", type=float,
                    help="Docker RAM and RAM+swap ceiling; required for --resident-ngram")
    args = ap.parse_args()
    if args.resident_ngram and not args.memory_limit_gib:
        ap.error("--resident-ngram requires --memory-limit-gib")
    if args.ctx < 512:
        ap.error("--ctx must be at least 512")
    cards = scan_cards()
    modes = tuple(mode for mode in MODES if not args.only_mode or mode[0] == args.only_mode)
    modes = tuple((name, ",".join(map(str, sorted(cards))) if name == "all_gpus" else visible, layers)
                  for name, visible, layers in modes)
    if args.gpu_layers is not None:
        if args.only_mode != "3090_full" or args.gpu_layers < 0:
            ap.error("--gpu-layers requires --only-mode 3090_full and a nonnegative count")
        modes = ((f"3090_partial_{args.gpu_layers}", "0", str(args.gpu_layers)),)
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    containers = run("docker", "ps", "--format", "{{.Names}}").stdout.splitlines()
    if NAME in containers:
        raise RuntimeError(f"benchmark container {NAME} is already running")
    selected = sorted({int(part) for _, visible, _ in modes
                       for part in visible.split(",") if part != "-1"})
    require_ids(selected, cards)
    if any(cards[index]["used_mib"] > 1024 for index in selected):
        raise RuntimeError("selected GPU is in use")
    check_planned_power(selected)
    actual = {index: round(card["power_limit_w"]) for index, card in cards.items()}
    state: dict = {"model": str(args.model), "image": IMAGE, "started_at": stamp(),
                   "context": args.ctx, "batch": 64, "threads": 4,
                   "kv_type": args.kv_type, "depth_fractions": args.depth_fractions,
                   "resident_ngram": args.resident_ngram,
                   "memory_limit_gib": args.memory_limit_gib,
                   "power_caps_w": actual, "gpu_inventory": cards,
                   "baseline_gpu_memory_mib": gpu_memory_mib(),
                   "host_before": memory(), "nvme_read_bytes_before": nvme_read_bytes(), "modes": {}}
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
        requested = [int(part) for part in visible.split(",")] if visible != "-1" else []
        visibility = (["--gpus", docker_devices(requested, cards)] if requested
                      else ["--gpus", "all", "--env", "CUDA_VISIBLE_DEVICES=-1"])
        cmd = ["docker", "run", "--detach", *visibility, "--network", "host",
               "--name", NAME,
               "--volume", f"{args.model.parent}:/models:ro", "--entrypoint", "/opt/llama/bin/llama-server",
               IMAGE, "--model", f"/models/{args.model.name}", "--host", "127.0.0.1",
               "--port", str(PORT), "--ctx-size", str(args.ctx), "--batch-size", "64",
               "--ubatch-size", "64", "--parallel", "1", "--threads", "4",
               "--threads-batch", "4", "--load-mode", "none", "--gpu-layers", layers,
               "--slot-prompt-similarity", "0", "--log-verbosity", "4"]
        if args.memory_limit_gib:
            limit = f"{int(args.memory_limit_gib * 1024)}m"
            cmd[2:2] = ["--memory", limit, "--memory-swap", limit]
        if args.resident_ngram:
            cmd += ["--lazy-mode", "off", "--override-tensor",
                    "per_layer_token_embd=CPU"]
        if args.kv_type != "f16":
            cmd += ["--cache-type-k", args.kv_type, "--cache-type-v", args.kv_type,
                    "--flash-attn", "on"]
        try:
            t0 = time.monotonic()
            launched = run(*cmd)
            row["container_id"] = launched.stdout.strip()[:12]
            ready(timeout=args.load_timeout)
            row["load_seconds"] = round(time.monotonic() - t0, 2)
            row["gpu_memory_after_load_mib"] = gpu_memory_mib()
            row["host_after_load"] = memory()
            row["nvme_read_bytes_after_load"] = nvme_read_bytes()
            row["server_log"] = str(args.output / f"{mode}.log")
            if args.depth_fractions:
                from capacity_run import depth_probe
                row["depth_probes"] = []
                for fraction in (float(value) for value in args.depth_fractions.split(",")):
                    disk_before = nvme_read_bytes()
                    result = depth_probe(PORT, args.ctx, fraction, list(selected), 160,
                                         allow_eos=True, concise_instruction=True)
                    result["nvme_read_bytes"] = nvme_read_bytes() - disk_before
                    result["host"] = memory()
                    row["depth_probes"].append(result)
                    write(args.output / "checkpoint.json", state)
            else:
                for repeat in (1, 2):
                    disk_before = nvme_read_bytes()
                    t1 = time.monotonic()
                    response = request("/completion", body, timeout=600)
                    row[f"repeat_{repeat}"] = {
                        "wall_seconds": round(time.monotonic() - t1, 2),
                        "timings": response.get("timings"),
                        "tokens_predicted": response.get("tokens_predicted"),
                        "tokens_evaluated": response.get("tokens_evaluated"),
                        "stopped_eos": response.get("stopped_eos"),
                        "stopped_limit": response.get("stopped_limit"),
                        "nvme_read_bytes": nvme_read_bytes() - disk_before,
                        "host": memory(),
                    }
            row["status"] = "passed"
            print(f"{mode}: {row.get('depth_probes') or row['repeat_2']['timings']}", flush=True)
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"{mode}: {row['error']}", flush=True)
        finally:
            inspection = run("docker", "inspect", "-f", "{{json .State}}", NAME,
                             check=False).stdout.strip()
            if inspection:
                try:
                    row["container_state"] = json.loads(inspection)
                except ValueError:
                    row["container_state_raw"] = inspection[:500]
            (args.output / f"{mode}.log").write_text(
                run("docker", "logs", NAME, check=False).stderr, encoding="utf-8")
            run("docker", "rm", "-f", NAME, check=False)
            row["host_after"] = memory()
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
