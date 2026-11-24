#!/usr/bin/env python3
"""Measure shared-weight worker-context memory, packing, and concurrent speed.

This is a benchmark-only probe for the llama-kv-chat-server runtime.  A managed
hardware session must reserve the parent and worker GPUs before invoking it.
The probe keeps model weights on GPU0, creates Q4 KV contexts on the requested
worker cards, derives a MiB-per-token curve, and admits concurrent chats only
while direct NVIDIA free-memory telemetry remains above the requested reserve.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, text=True, capture_output=True)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1000:]
        raise RuntimeError(f"{' '.join(argv)} failed ({result.returncode}): {detail}")
    return result


def request(port: int, path: str, method: str = "GET", body: dict | None = None,
            timeout: float = 180) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except ValueError:
            return exc.code, {"error": exc.reason}


def gpu_memory() -> dict[int, dict[str, int]]:
    result = run([
        "nvidia-smi", "--query-gpu=index,memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits"])
    values: dict[int, dict[str, int]] = {}
    for line in result.stdout.splitlines():
        gpu, total, used, free = (int(part.strip()) for part in line.split(","))
        values[gpu] = {"total_mib": total, "used_mib": used, "free_mib": free}
    return values


def fit_line(rows: list[dict]) -> dict:
    points = [(float(row["context_cap"]), float(row["worker_allocation_mib"])) for row in rows]
    x_mean = sum(x for x, _ in points) / len(points)
    y_mean = sum(y for _, y in points) / len(points)
    denom = sum((x - x_mean) ** 2 for x, _ in points)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denom if denom else 0.0
    intercept = y_mean - slope * x_mean
    predicted = [intercept + slope * x for x, _ in points]
    errors = [abs(y - p) for (_, y), p in zip(points, predicted)]
    return {
        "fixed_mib": round(intercept, 4),
        "mib_per_token": round(slope, 8),
        "tokens_per_mib": round(1.0 / slope, 3) if slope > 0 else None,
        "mib_at_262144": math.ceil(intercept + slope * 262144),
        "max_absolute_error_mib": round(max(errors), 3),
        "formula": f"ceil({intercept:.4f} + {slope:.8f} * context_tokens) MiB",
    }


def affordable_context(free_mib: int, reserve_mib: int, memory_model: dict,
                       maximum: int, *, quantum: int = 1024) -> int:
    """Largest aligned context predicted to fit while preserving the reserve."""
    slope = float(memory_model["mib_per_token"])
    fixed = float(memory_model["fixed_mib"])
    if slope <= 0 or free_mib <= reserve_mib + fixed:
        return 0
    tokens = math.floor((free_mib - reserve_mib - fixed) / slope)
    return min(maximum, tokens // quantum * quantum)


def attach(port: int, chat_id: str, gpu: int, context_cap: int) -> dict:
    code, value = request(port, "/chats", "POST", {
        "chat_id": chat_id, "gpu": gpu, "context_cap": context_cap})
    if code != 201:
        raise RuntimeError(f"attach {chat_id} on GPU{gpu} failed ({code}): {value}")
    return value


def detach(port: int, chat_id: str) -> None:
    code, value = request(port, f"/chats/{chat_id}", "DELETE")
    if code not in (200, 404):
        raise RuntimeError(f"detach {chat_id} failed ({code}): {value}")


def turn(port: int, chat_id: str, max_tokens: int) -> dict:
    code, value = request(port, f"/chats/{chat_id}/turns", "POST", {
        "message": f"Reply with exactly CAPACITY_{chat_id} and nothing else.",
        "max_tokens": max_tokens}, timeout=900)
    if code != 200:
        raise RuntimeError(f"turn {chat_id} failed ({code}): {value}")
    value["label_ok"] = f"CAPACITY_{chat_id}" in value.get("content", "")
    return value


def concurrent_turns(port: int, chats: list[dict], max_tokens: int) -> dict:
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(chats)) as pool:
        futures = {pool.submit(turn, port, row["chat_id"], max_tokens): row for row in chats}
        replies = []
        for future, row in futures.items():
            try:
                replies.append({"chat_id": row["chat_id"], "gpu": row["gpu"], **future.result()})
            except Exception as exc:
                replies.append({"chat_id": row["chat_id"], "gpu": row["gpu"],
                                "error": f"{type(exc).__name__}: {exc}"})
    wall = time.monotonic() - started
    generated = sum(int(row.get("generated_tokens") or 0) for row in replies)
    return {"chat_count": len(chats), "wall_seconds": round(wall, 3),
            "aggregate_generated_tok_s": round(generated / wall, 3) if wall else None,
            "all_labels_ok": all(row.get("label_ok") is True for row in replies),
            "replies": replies, "gpu_memory_after": gpu_memory()}


def parse_ints(value: str) -> list[int]:
    try:
        result = [int(part) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not result or len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("values must be unique")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build", type=Path, default=Path("/data/bench-staging/kvchat-b11669-build"))
    parser.add_argument("--image", default="4bfa1cb0a955")
    parser.add_argument("--server", default="llama-kv-chat-server-v2")
    parser.add_argument("--port", type=int, default=11534)
    parser.add_argument("--parent-gpu", type=int, default=0)
    parser.add_argument("--worker-gpus", type=parse_ints, default=parse_ints("1,3,4,5"))
    parser.add_argument("--curve-contexts", type=parse_ints,
                        default=parse_ints("16384,32768,65536,131072,196608,262144"))
    parser.add_argument("--context-cap", type=int, default=262144)
    parser.add_argument("--worker-reserve-mib", type=int, default=272)
    parser.add_argument("--parent-reserve-mib", type=int, default=512)
    parser.add_argument("--max-chats", type=int, default=16)
    parser.add_argument("--turn-tokens", type=int, default=48)
    parser.add_argument("--gap-fill", action="store_true",
                        help="after full contexts, validate smaller contexts in remaining worker memory")
    args = parser.parse_args()
    if not args.model.is_file():
        parser.error(f"model is missing: {args.model}")
    binary = args.build / "bin" / args.server
    if not binary.is_file():
        parser.error(f"shared-KV server is missing: {binary}")
    if args.parent_gpu in args.worker_gpus:
        parser.error("parent GPU cannot also be a worker GPU")
    if any(ctx < 16384 or ctx > args.context_cap for ctx in args.curve_contexts):
        parser.error("curve contexts must be within 16384..context-cap")

    container = f"shared-kv-capacity-{os.getpid()}"
    receipt = {
        "schema_version": 1, "kind": "shared_kv_capacity", "started_at": stamp(),
        "model_path": str(args.model), "kv_type": "q4_0", "parent_gpu": args.parent_gpu,
        "worker_gpus": args.worker_gpus, "context_cap": args.context_cap,
        "reserves_mib": {"parent": args.parent_reserve_mib, "worker": args.worker_reserve_mib},
        "curve": [], "concurrency": [], "cleanup_verified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    active: list[dict] = []
    try:
        baseline = gpu_memory()
        receipt["baseline_gpu_memory"] = baseline
        with __import__("socket").socket() as sock:
            if sock.connect_ex(("127.0.0.1", args.port)) == 0:
                raise RuntimeError(f"port {args.port} is already in use")
        run(["docker", "run", "-d", "--rm", "--gpus", "all", "--network", "host",
             "--name", container, "-e", "CUDA_DEVICE_ORDER=PCI_BUS_ID",
             "-e", "KV_ALLOW_SHARED_GPU=1", "-e", "KV_MAIN_CONTEXT_CAP=0",
             "-v", f"{args.build}:/build:ro", "-v", f"{args.model}:/model.gguf:ro",
             args.image, f"/build/bin/{args.server}", "/model.gguf", str(args.port),
             str(args.context_cap), "q4_0"])
        for _ in range(180):
            try:
                code, health = request(args.port, "/health", timeout=2)
                if code == 200 and health.get("model_loaded") is True:
                    break
            except OSError:
                pass
            state = run(["docker", "inspect", "-f", "{{.State.Running}}", container], check=False)
            if state.returncode or state.stdout.strip() != "true":
                raise RuntimeError("shared-KV server exited during startup")
            time.sleep(1)
        else:
            raise RuntimeError("shared-KV server did not become ready in 180 seconds")
        receipt["service_ready_at"] = stamp()
        receipt["weights_gpu_memory"] = gpu_memory()

        curve_gpu = args.worker_gpus[0]
        for context_cap in args.curve_contexts:
            chat_id = f"curve_{context_cap}"
            before = gpu_memory()
            attach(args.port, chat_id, curve_gpu, context_cap)
            time.sleep(1)
            after = gpu_memory()
            response = turn(args.port, chat_id, args.turn_tokens)
            after_turn = gpu_memory()
            detach(args.port, chat_id)
            time.sleep(1)
            released = gpu_memory()
            receipt["curve"].append({
                "context_cap": context_cap, "gpu": curve_gpu,
                "worker_allocation_mib": after[curve_gpu]["used_mib"] - before[curve_gpu]["used_mib"],
                "parent_allocation_mib": after[args.parent_gpu]["used_mib"] - before[args.parent_gpu]["used_mib"],
                "first_turn_worker_growth_mib": after_turn[curve_gpu]["used_mib"] - after[curve_gpu]["used_mib"],
                "first_turn_parent_growth_mib": after_turn[args.parent_gpu]["used_mib"] - after[args.parent_gpu]["used_mib"],
                "decode_tok_s": response.get("decode_tok_s"), "label_ok": response.get("label_ok"),
                "released_delta_mib": released[curve_gpu]["used_mib"] - before[curve_gpu]["used_mib"],
            })
        receipt["memory_model"] = fit_line(receipt["curve"])
        predicted = int(receipt["memory_model"]["mib_at_262144"])

        while len(active) < args.max_chats:
            memory = gpu_memory()
            parent_free = memory[args.parent_gpu]["free_mib"]
            if parent_free < args.parent_reserve_mib:
                receipt["saturation_reason"] = "parent reserve reached"
                break
            candidates = [gpu for gpu in args.worker_gpus
                          if memory[gpu]["free_mib"] - predicted >= args.worker_reserve_mib]
            if not candidates:
                receipt["saturation_reason"] = "worker reserves reached"
                break
            selected = max(candidates, key=lambda gpu: memory[gpu]["free_mib"])
            chat_id = f"chat_{len(active) + 1:02d}"
            try:
                attach(args.port, chat_id, selected, args.context_cap)
            except Exception as exc:
                receipt["saturation_reason"] = f"runtime attach rejected: {exc}"
                break
            active.append({"chat_id": chat_id, "gpu": selected, "context_cap": args.context_cap})
            receipt.setdefault("admissions", []).append({
                **active[-1], "gpu_memory_after": gpu_memory()})

        receipt["max_full_context_chats"] = len(active)
        if args.gap_fill:
            while len(active) < args.max_chats:
                memory = gpu_memory()
                if memory[args.parent_gpu]["free_mib"] < args.parent_reserve_mib:
                    receipt["gap_fill_reason"] = "parent reserve reached"
                    break
                choices = []
                for gpu in args.worker_gpus:
                    context_cap = affordable_context(
                        memory[gpu]["free_mib"], args.worker_reserve_mib,
                        receipt["memory_model"], args.context_cap)
                    if context_cap >= 16384:
                        choices.append((context_cap, gpu))
                if not choices:
                    receipt["gap_fill_reason"] = "no worker has room for the minimum context"
                    break
                context_cap, selected = max(choices)
                chat_id = f"gap_{len(active) + 1:02d}_{context_cap}"
                try:
                    attach(args.port, chat_id, selected, context_cap)
                except Exception as exc:
                    receipt["gap_fill_reason"] = f"runtime attach rejected: {exc}"
                    break
                active.append({"chat_id": chat_id, "gpu": selected, "context_cap": context_cap})
                receipt.setdefault("gap_fill_admissions", []).append({
                    **active[-1], "gpu_memory_after": gpu_memory()})

        levels = sorted(set(level for level in (1, len(args.worker_gpus), len(active))
                            if 0 < level <= len(active)))
        for level in levels:
            receipt["concurrency"].append(concurrent_turns(
                args.port, active[:level], args.turn_tokens))
        receipt["max_safe_chats"] = len(active)
        receipt["placement"] = [row["gpu"] for row in active]
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for row in reversed(active):
            try:
                detach(args.port, row["chat_id"])
            except Exception:
                pass
        run(["docker", "stop", container], check=False)
        time.sleep(1)
        try:
            final_memory = gpu_memory()
            receipt["final_gpu_memory"] = final_memory
            baseline = receipt.get("baseline_gpu_memory") or {}
            receipt["cleanup_verified"] = all(
                final_memory[gpu]["used_mib"] <= baseline[gpu]["used_mib"] + 16
                for gpu in [args.parent_gpu, *args.worker_gpus])
        except Exception as exc:
            receipt["cleanup_error"] = f"{type(exc).__name__}: {exc}"
        receipt["finished_at"] = stamp()
        tmp = args.output.with_suffix(args.output.suffix + ".tmp")
        tmp.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, args.output)
        print(json.dumps({"output": str(args.output), "max_safe_chats": receipt.get("max_safe_chats"),
                          "cleanup_verified": receipt["cleanup_verified"],
                          "error": receipt.get("error")}), flush=True)
    return 1 if receipt.get("error") or not receipt["cleanup_verified"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
