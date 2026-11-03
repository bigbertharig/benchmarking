#!/usr/bin/env python3
"""One supervised Strata Qwen3.6 placement probe on the leased 3090."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONTROL = Path("/data/bench-staging/strata-v0.2.10/control/bin/strata")
COMPONENTS = "/data/bench-staging/strata-v0.2.10/components"
MODEL = Path("/data/model-hotset/qwen3.6-35b-a3b-strata-xl/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf")
PORT = 18130
NVME_STAT = Path("/sys/block/nvme0n1/stat")
PROMPT = ("Explain how a B-tree index serves searches, inserts, and deletes in a database. "
          "Include what happens during node splits and merges. " * 55)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def gpu_used() -> int:
    result = subprocess.run(["nvidia-smi", "-i", "0", "--query-gpu=memory.used",
                             "--format=csv,noheader,nounits"], text=True, capture_output=True, check=True)
    return int(result.stdout.strip())


def meminfo() -> dict[str, int]:
    wanted = {"MemAvailable", "Cached", "SwapFree", "SwapTotal"}
    result = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in wanted:
            result[key + "_kib"] = int(value.split()[0])
    return result


def nvme_bytes() -> dict[str, int]:
    # Host-wide block counters; concurrent workloads must be recorded separately.
    fields = [int(value) for value in NVME_STAT.read_text().split()]
    return {"read_bytes": fields[2] * 512, "written_bytes": fields[6] * 512}


def get(path: str, body: dict | None = None, timeout: int = 10) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--expert-vram", type=float,
                    help="Qwen3.6 routed-expert VRAM budget in GiB; omit for Strata default")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state = {"started_at": stamp(), "status": "running", "model": str(MODEL),
             "gpu": 0, "context": 8192, "parallel": 1, "mtp": "off",
             "requested_expert_vram_gib": args.expert_vram, "port": PORT,
             "nvme_counter": str(NVME_STAT), "nvme_counter_scope": "host-wide"}
    save(args.output / "checkpoint.json", state)
    home = Path("/data/bench-staging/strata-v0.2.10/home-benchmark")
    env = dict(os.environ, STRATA_HOME=str(home), STRATA_COMPONENTS_DIR=COMPONENTS,
               CUDA_VISIBLE_DEVICES="0", CUDA_DEVICE_ORDER="PCI_BUS_ID")
    base = [str(CONTROL), "launch"]
    launch = base + ["--family", "qwen36", "--model", "ud-q4_k_xl",
                     "--model-path", str(MODEL), "--gpu", "0", "--backend", "nvidia",
                     "--vision", "off", "--context", "8192", "--parallel", "1",
                     "--mtp", "off", "--port", str(PORT), "--access", "local",
                     "--no-api-key", "--tune", "skip", "--no-tui", "--yes", "--output", "json"]
    if args.expert_vram is not None:
        launch += ["--set", f"expert-vram={args.expert_vram:g}"]
    state["launch_args"] = launch[2:]
    launched = False
    try:
        if not MODEL.is_file():
            raise FileNotFoundError(MODEL)
        if gpu_used() > 1024:
            raise RuntimeError("GPU 0 is already in use")
        state["gpu_idle_mib"] = gpu_used()
        state["host_before"] = meminfo()
        state["nvme_before"] = nvme_bytes()
        t0 = time.monotonic()
        launched = True
        proc = subprocess.run(launch, env=env, text=True, capture_output=True, timeout=300)
        (args.output / "launch_stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (args.output / "launch_stderr.txt").write_text(proc.stderr, encoding="utf-8")
        state["launch_exit"] = proc.returncode
        state["launch_seconds"] = round(time.monotonic() - t0, 2)
        if proc.returncode:
            raise RuntimeError(f"Strata launch exited {proc.returncode}")
        for _ in range(30):
            try:
                health = get("/health", timeout=2)
                if health:
                    state["health"] = health
                    break
            except (OSError, ValueError):
                time.sleep(2)
        else:
            raise RuntimeError("Strata API did not become ready")
        state["gpu_loaded_mib"] = gpu_used()
        state["host_loaded"] = meminfo()
        state["nvme_loaded"] = nvme_bytes()
        state["requests"] = []
        for repeat in (1, 2):
            disk_before_request = nvme_bytes()
            t1 = time.monotonic()
            response = get("/v1/chat/completions", {"model": "strata", "messages": [
                {"role": "user", "content": PROMPT}], "max_tokens": 128, "temperature": 0}, timeout=600)
            save(args.output / f"response_{repeat}.json", response)
            state["requests"].append({"repeat": repeat,
                                      "wall_seconds": round(time.monotonic() - t1, 3),
                                      "usage": response.get("usage"),
                                      "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
                                      "gpu_mib": gpu_used(), "host": meminfo(),
                                      "nvme_before": disk_before_request,
                                      "nvme_after": nvme_bytes()})
            save(args.output / "checkpoint.json", state)
        state["status"] = "passed"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if launched:
            try:
                stopped = subprocess.run(base + ["--stop", "--output", "json"], env=env,
                                         text=True, capture_output=True, timeout=60)
                (args.output / "stop_stdout.txt").write_text(stopped.stdout, encoding="utf-8")
                (args.output / "stop_stderr.txt").write_text(stopped.stderr, encoding="utf-8")
                state["stop_exit"] = stopped.returncode
            except Exception as exc:
                state["stop_error"] = f"{type(exc).__name__}: {exc}"
        log_root = Path("/home/bryan/.local/state/strata")
        for source, name in ((log_root / "launch/ud-q4_k_xl-8k.engine.log", "engine.log"),
                             (log_root / "runtime/launch-ud-q4_k_xl-8k.server.log", "server.log")):
            if source.is_file():
                shutil.copy2(source, args.output / name)
        state["gpu_after_mib"] = gpu_used()
        state["host_after"] = meminfo()
        state["nvme_after"] = nvme_bytes()
        state["finished_at"] = stamp()
        save(args.output / "terminal.json", state)
        message = f"Strata probe: {state['status']}"
        if state.get("error"):
            message += f" {state['error']}"
        print(message, flush=True)
    return 0 if state["status"] == "passed" and state.get("stop_exit") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
