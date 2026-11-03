#!/usr/bin/env python3
"""Probe Qwen3.8 Strata expert placement on leased GPU 0, RAM and NVMe."""
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
MODEL = Path("/data/model-hotset/qwen3.8-flash-next-q2_0")
RECEIPT = MODEL / "download_terminal.json"
PORT = 18131
NVME = Path("/sys/block/nvme0n1/stat")
PROMPT = ("Explain how a B-tree index serves searches, inserts, and deletes in a database. "
          "Include what happens during node splits and merges. " * 55)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(path: Path, state: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def gpu_mib() -> int:
    result = subprocess.run(["nvidia-smi", "-i", "0", "--query-gpu=memory.used",
                             "--format=csv,noheader,nounits"], capture_output=True,
                            text=True, check=True)
    return int(result.stdout.strip())


def memory() -> dict[str, int]:
    wanted = {"MemAvailable", "SwapFree", "SwapTotal", "Cached"}
    result = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in wanted:
            result[key + "_kib"] = int(value.split()[0])
    return result


def nvme_bytes() -> dict[str, int]:
    parts = [int(value) for value in NVME.read_text().split()]
    return {"read_bytes": parts[2] * 512, "written_bytes": parts[6] * 512}


def engine_io() -> dict[str, int | str] | None:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            if "strata --serve" not in command or "qwen3.8" not in command.lower():
                continue
            values = {}
            for line in (entry / "io").read_text().splitlines():
                key, _, value = line.partition(":")
                if key in {"read_bytes", "write_bytes", "rchar", "wchar"}:
                    values[key] = int(value)
            values["pid"] = int(entry.name)
            values["command"] = command[:300]
            return values
        except (OSError, ValueError):
            continue
    return None


def request(path: str, body: dict | None = None, timeout: int = 10) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--resident-budget-gib", type=float,
                    help="GiB of experts copied into RAM; omit for Strata default")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state = {"started_at": stamp(), "status": "running", "model": str(MODEL),
             "gpu": 0, "context": 8192, "parallel": 1, "drafting": "off",
             "mtp": "off", "resident_budget_gib": args.resident_budget_gib,
             "nvme_counter": str(NVME), "nvme_counter_scope": "host-wide"}
    save(args.output / "checkpoint.json", state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=COMPONENTS,
               CUDA_VISIBLE_DEVICES="0", CUDA_DEVICE_ORDER="PCI_BUS_ID")
    base = [str(CONTROL), "launch"]
    launch = base + ["--family", "qwen", "--model", "q2_0", "--model-path", str(MODEL),
                     "--gpu", "0", "--backend", "nvidia", "--vision", "off",
                     "--context", "8192", "--parallel", "1", "--drafting", "off",
                     "--mtp", "off", "--port", str(PORT), "--access", "local",
                     "--no-api-key", "--tune", "skip", "--no-tui", "--yes", "--output", "json"]
    if args.resident_budget_gib is not None:
        launch += ["--set", f"resident-budget-gib={args.resident_budget_gib:g}"]
    state["launch_args"] = launch[2:]
    launched = False
    try:
        receipt = json.loads(RECEIPT.read_text())
        if receipt.get("status") != "passed":
            raise RuntimeError("model download receipt is not passed")
        if gpu_mib() > 1024:
            raise RuntimeError("GPU 0 is already in use")
        state["gpu_idle_mib"] = gpu_mib()
        state["host_before"] = memory()
        state["nvme_before"] = nvme_bytes()
        t0 = time.monotonic()
        launched = True
        proc = subprocess.run(launch, env=env, capture_output=True, text=True, timeout=900)
        (args.output / "launch_stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (args.output / "launch_stderr.txt").write_text(proc.stderr, encoding="utf-8")
        state["launch_exit"] = proc.returncode
        state["launch_seconds"] = round(time.monotonic() - t0, 2)
        if proc.returncode:
            raise RuntimeError(f"Strata launch exited {proc.returncode}")
        for _ in range(30):
            try:
                state["health"] = request("/health", timeout=2)
                break
            except (OSError, ValueError):
                time.sleep(2)
        else:
            raise RuntimeError("Strata API did not become ready")
        state["gpu_loaded_mib"] = gpu_mib()
        state["host_loaded"] = memory()
        state["nvme_loaded"] = nvme_bytes()
        state["engine_io_loaded"] = engine_io()
        if state["host_loaded"]["MemAvailable_kib"] < 5 * 1024 * 1024:
            raise RuntimeError("less than 5 GiB MemAvailable after launch")
        state["requests"] = []
        for repeat in (1, 2):
            disk_before = nvme_bytes()
            io_before = engine_io()
            t1 = time.monotonic()
            response = request("/v1/chat/completions", {"model": "strata", "messages": [
                {"role": "user", "content": PROMPT}], "max_tokens": 128,
                "temperature": 0}, timeout=600)
            wall = round(time.monotonic() - t1, 3)
            save(args.output / f"response_{repeat}.json", response)
            state["requests"].append({"repeat": repeat, "wall_seconds": wall,
                                      "usage": response.get("usage"),
                                      "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
                                      "gpu_mib": gpu_mib(), "host": memory(),
                                      "nvme_before": disk_before, "nvme_after": nvme_bytes(),
                                      "engine_io_before": io_before, "engine_io_after": engine_io()})
            save(args.output / "checkpoint.json", state)
        state["status"] = "passed"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if launched:
            try:
                stopped = subprocess.run(base + ["--stop", "--output", "json"], env=env,
                                         capture_output=True, text=True, timeout=120)
                (args.output / "stop_stdout.txt").write_text(stopped.stdout, encoding="utf-8")
                (args.output / "stop_stderr.txt").write_text(stopped.stderr, encoding="utf-8")
                state["stop_exit"] = stopped.returncode
            except Exception as exc:
                state["stop_error"] = f"{type(exc).__name__}: {exc}"
        log_root = Path("/home/bryan/.local/state/strata")
        for folder, name in (("launch", "engine.log"), ("runtime", "server.log")):
            logs = sorted((log_root / folder).glob("*q2_0-8k*.log"),
                          key=lambda path: path.stat().st_mtime, reverse=True)
            if logs:
                shutil.copy2(logs[0], args.output / name)
        state["gpu_after_mib"] = gpu_mib()
        state["host_after"] = memory()
        state["nvme_after"] = nvme_bytes()
        state["finished_at"] = stamp()
        save(args.output / "terminal.json", state)
        message = f"Strata Qwen3.8 probe: {state['status']}"
        if state.get("error"):
            message += f" {state['error']}"
        print(message, flush=True)
    return 0 if state["status"] == "passed" and state.get("stop_exit") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
