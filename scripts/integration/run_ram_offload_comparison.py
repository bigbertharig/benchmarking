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


def host_memory_mib() -> dict[str, int]:
    wanted = {"MemAvailable", "SwapFree", "SwapTotal"}
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in wanted:
            values[key + "_mib"] = int(value.strip().split()[0]) // 1024
    return values


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
    ap.add_argument("--prompt-repeat", type=int, default=55,
                    help="repeat the fixed B-tree prompt clause (default: 55)")
    ap.add_argument("--only-mode", choices=[mode for mode, _, _ in MODES],
                    help="run only one placement, for a targeted repeat")
    ap.add_argument("--gpu-layers", type=int,
                    help="override GPU layer count for --only-mode 3090_full; records a partial placement")
    ap.add_argument("--load-timeout", type=float, default=240,
                    help="seconds to wait for server readiness (default: 240)")
    ap.add_argument("--visible-gpus", help="override visible GPU IDs for a selected placement")
    ap.add_argument("--tensor-split", help="explicit llama.cpp split for a multi-GPU placement")
    ap.add_argument("--min-selected-vram-mib", type=int, default=512,
                    help="minimum observed VRAM increase on every selected card (default: 512)")
    ap.add_argument("--keep-loaded", action="store_true", help="leave the successful sole mode container running")
    args = ap.parse_args()
    if args.ctx < 512:
        ap.error("--ctx must be at least 512")
    if args.prompt_repeat < 1:
        ap.error("--prompt-repeat must be positive")
    if args.min_selected_vram_mib < 1:
        ap.error("--min-selected-vram-mib must be positive")
    if args.keep_loaded and not args.only_mode:
        ap.error("--keep-loaded requires --only-mode")
    modes = tuple(mode for mode in MODES if not args.only_mode or mode[0] == args.only_mode)
    if args.gpu_layers is not None:
        if args.only_mode != "3090_full" or args.gpu_layers < 0:
            ap.error("--gpu-layers requires --only-mode 3090_full and a nonnegative count")
        modes = ((f"3090_partial_{args.gpu_layers}", "0", str(args.gpu_layers)),)
    if args.visible_gpus:
        if args.only_mode != "3090_full":
            ap.error("--visible-gpus requires --only-mode 3090_full")
        modes = tuple((name, args.visible_gpus, layers) for name, _, layers in modes)
    if args.tensor_split and not args.visible_gpus:
        ap.error("--tensor-split requires --visible-gpus")
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    containers = run("docker", "ps", "--format", "{{.Names}}").stdout.splitlines()
    if NAME in containers:
        raise RuntimeError(f"benchmark container {NAME} is already running")
    visible_ids = {int(i) for _, visible, _ in modes for i in visible.split(",") if i != "-1"}
    inventory = run("nvidia-smi", "--query-gpu=index,uuid,name,memory.total",
                    "--format=csv,noheader,nounits").stdout
    cards = {}
    for line in inventory.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) != 4 or not fields[0].isdigit() or not fields[3].isdigit():
            raise RuntimeError(f"invalid GPU inventory row: {line}")
        cards[int(fields[0])] = {"uuid": fields[1], "name": fields[2], "total_mib": int(fields[3])}
    if not visible_ids.issubset(cards):
        raise RuntimeError(f"requested GPU IDs absent: {sorted(visible_ids - cards.keys())}")
    memory_now = gpu_memory_mib()
    busy = [i for i in sorted(visible_ids) if memory_now[i] > 1024]
    if busy:
        raise RuntimeError(f"GPUs in use: {busy}; wait for free cards")
    power = run("nvidia-smi", "--query-gpu=index,power.limit", "--format=csv,noheader,nounits").stdout
    actual = [round(float(line.split(",")[1])) for line in power.splitlines()]
    names = run("nvidia-smi", "--query-gpu=name", "--format=csv,noheader").stdout.splitlines()
    if len(actual) != len(names):
        raise RuntimeError(f"GPU inventory/power mismatch: {list(zip(names, actual))}")
    planned = run("python3", "/home/bryan/llm_orchestration/shared/scripts/rig/hw_power.py",
                  "check", "--gpus", ",".join(map(str, sorted(visible_ids))), check=False)
    if planned.returncode:
        raise RuntimeError(f"power cap differs from discovered card plan: {(planned.stderr or planned.stdout).strip()}")
    state: dict = {"model": str(args.model), "image": IMAGE, "started_at": stamp(),
                   "context": args.ctx, "batch": 64, "threads": 4,
                   "power_caps_w": actual, "gpu_names": names, "gpu_inventory": cards,
                   "prompt_repeat": args.prompt_repeat,
                   "baseline_gpu_memory_mib": gpu_memory_mib(), "modes": {}}
    write(args.output / "checkpoint.json", state)
    prompt = ("Explain how a B-tree index serves searches, inserts, and deletes in a database. "
              "Include what happens during node splits and merges. " * args.prompt_repeat)
    body = {"prompt": prompt, "n_predict": 128, "temperature": 0,
            "cache_prompt": False, "ignore_eos": True, "stream": False}
    for mode, visible, layers in modes:
        requested = [int(part) for part in visible.split(",")] if visible != "-1" else []
        uuids = [cards[index]["uuid"] for index in requested]
        row: dict = {"started_at": stamp(), "gpu_visible": visible,
                     "gpu_uuids": uuids, "gpu_layers_requested": layers, "status": "running",
                     "host_memory_before": host_memory_mib(),
                     "gpu_memory_before_load_mib": gpu_memory_mib()}
        state["modes"][mode] = row
        write(args.output / "checkpoint.json", state)
        run("docker", "rm", "-f", NAME, check=False)
        visibility = (["--gpus", '"device=' + ','.join(uuids) + '"'] if uuids
                      else ["--gpus", "all", "--env", "CUDA_VISIBLE_DEVICES=-1"])
        cmd = ["docker", "run", "--detach", *visibility, "--network", "host",
               "--name", NAME,
               "--volume", f"{args.model.parent}:/models:ro", "--entrypoint", "/opt/llama/bin/llama-server",
               IMAGE, "--model", f"/models/{args.model.name}", "--host", "127.0.0.1",
               "--port", str(PORT), "--ctx-size", str(args.ctx), "--batch-size", "64",
               "--ubatch-size", "64", "--parallel", "1", "--threads", "4",
               "--threads-batch", "4", "--load-mode", "none", "--gpu-layers", layers,
               "--slot-prompt-similarity", "0", "--log-verbosity", "4"]
        if args.tensor_split:
            cmd.extend(["--tensor-split", args.tensor_split])
        if args.visible_gpus or args.gpu_layers is not None:
            cmd.extend(["--fit", "off"])
        try:
            t0 = time.monotonic()
            launched = run(*cmd)
            row["container_id"] = launched.stdout.strip()[:12]
            ready(timeout=args.load_timeout)
            row["load_seconds"] = round(time.monotonic() - t0, 2)
            row["gpu_memory_after_load_mib"] = gpu_memory_mib()
            delta = [after - before for before, after in
                     zip(row["gpu_memory_before_load_mib"], row["gpu_memory_after_load_mib"])]
            row["gpu_memory_delta_mib"] = delta
            wrong = [index for index, change in enumerate(delta)
                     if (index in requested and change < args.min_selected_vram_mib)
                     or (index not in requested and change > 256)]
            if wrong:
                raise RuntimeError(f"loaded GPU placement differs from requested UUIDs at IDs {wrong}: {delta}")
            row["pcie_links_after_load"] = run("nvidia-smi",
                "--query-gpu=index,pcie.link.gen.current,pcie.link.width.current",
                "--format=csv,noheader").stdout.splitlines()
            row["host_memory_after_load"] = host_memory_mib()
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
            row["host_memory_after_requests"] = host_memory_mib()
            row["status"] = "passed"
            print(f"{mode}: {row['repeat_2']['timings']}", flush=True)
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"{mode}: {row['error']}", flush=True)
        finally:
            (args.output / f"{mode}.log").write_text(
                run("docker", "logs", NAME, check=False).stderr, encoding="utf-8")
            if not (args.keep_loaded and row["status"] == "passed"):
                run("docker", "rm", "-f", NAME, check=False)
            else:
                row["left_loaded"] = True
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
