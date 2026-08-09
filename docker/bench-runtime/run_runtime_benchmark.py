#!/usr/bin/env python3
"""Measure operational llama-compatible runtime behavior and record schema-v3 rows."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


METHODOLOGY = ("bench-runtime/operational", "1.0.0", "runtime-operational-v1")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def usage_count(payload: dict[str, Any], *names: str) -> int:
    usage = payload.get("usage", {})
    if not isinstance(usage, dict):
        return 0
    for name in names:
        value = usage.get(name)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def post_json(url: str, payload: dict[str, Any], timeout: int) -> tuple[dict[str, Any], float]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read())
    elapsed = time.monotonic() - started
    if not isinstance(decoded, dict):
        raise RuntimeError("runtime returned non-object JSON")
    return decoded, elapsed


def chat_payload(model: str, prompt: str, max_tokens: int, *, stream: bool = False) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def stream_ttft(base_url: str, model: str, timeout: int) -> tuple[float, float]:
    payload = chat_payload(model, "Reply with exactly: READY", 8, stream=True)
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    started = time.monotonic()
    first_token_at: float | None = None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                event = json.loads(body)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices", []) if isinstance(event, dict) else []
            if not choices or not isinstance(choices[0], dict):
                continue
            delta = choices[0].get("delta", {})
            if not isinstance(delta, dict):
                continue
            token = str(delta.get("content") or delta.get("reasoning_content") or "")
            if token and first_token_at is None:
                first_token_at = time.monotonic()
    ended = time.monotonic()
    if first_token_at is None:
        raise RuntimeError("stream completed without a content token")
    return first_token_at - started, ended - started


def telemetry_rows(gpu_ids: tuple[int, ...]) -> list[tuple[float, float, float]]:
    proc = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.used,power.draw",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    selected = set(gpu_ids)
    now = time.monotonic()
    memory = power = 0.0
    found: set[int] = set()
    for line in proc.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            gpu_id = int(parts[0])
            memory_mb = float(parts[1])
            power_w = float(parts[2])
        except ValueError:
            continue
        if gpu_id in selected:
            found.add(gpu_id)
            memory += memory_mb
            power += power_w
    if found != selected:
        detail = proc.stderr.strip()
        missing = f"nvidia-smi did not report requested GPU ids: {sorted(selected - found)}"
        raise RuntimeError(f"{missing}; {detail}" if detail else missing)
    return [(now, memory, power)]


@dataclass
class TelemetrySampler:
    gpu_ids: tuple[int, ...]
    interval: float = 0.2
    samples: list[tuple[float, float, float]] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _error: str = ""
    _thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.gpu_ids:
            return
        self.samples.extend(telemetry_rows(self.gpu_ids))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.samples.extend(telemetry_rows(self.gpu_ids))
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                return

    def finish(self) -> dict[str, float | None]:
        if not self.gpu_ids:
            return {"peak_vram_mb": None, "energy_wh": None}
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.samples.extend(telemetry_rows(self.gpu_ids))
        if self._error:
            raise RuntimeError(self._error)
        energy_wh = 0.0
        for left, right in zip(self.samples, self.samples[1:]):
            delta_seconds = max(0.0, right[0] - left[0])
            energy_wh += ((left[2] + right[2]) / 2.0) * delta_seconds / 3600.0
        return {
            "peak_vram_mb": max((sample[1] for sample in self.samples), default=0.0),
            "energy_wh": energy_wh,
        }


def measured(gpu_ids: tuple[int, ...], operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    sampler = TelemetrySampler(gpu_ids)
    sampler.start()
    started = time.monotonic()
    try:
        result = operation()
    finally:
        elapsed = time.monotonic() - started
        telemetry = sampler.finish()
    result["wall_time_seconds"] = elapsed
    result.update(telemetry)
    result["gpu_seconds"] = elapsed * len(gpu_ids) if gpu_ids else None
    return result


def run_stability(base_url: str, model: str, timeout: int, count: int) -> dict[str, Any]:
    failures: list[str] = []
    elapsed_total = 0.0
    for index in range(count):
        try:
            payload, elapsed = post_json(
                f"{base_url.rstrip('/')}/v1/chat/completions",
                chat_payload(model, f"Health request {index + 1}. Reply OK.", 8),
                timeout,
            )
            choices = payload.get("choices", [])
            if not choices:
                raise RuntimeError("response missing choices")
            elapsed_total += elapsed
        except Exception as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
    return {
        "score": (count - len(failures)) / count,
        "sample_count": count,
        "failed_request_count": len(failures),
        "timeout_count": sum("timed out" in item.lower() for item in failures),
        "request_wall_seconds": elapsed_total,
        "errors": failures,
    }


def run_ttft(base_url: str, model: str, timeout: int, count: int) -> dict[str, Any]:
    values: list[float] = []
    failures: list[str] = []
    for _ in range(count):
        try:
            ttft, _ = stream_ttft(base_url, model, timeout)
            values.append(ttft)
        except Exception as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
    return {
        "score": len(values) / count,
        "sample_count": count,
        "ttft_seconds": sum(values) / len(values) if values else None,
        "failed_request_count": len(failures),
        "timeout_count": sum("timed out" in item.lower() for item in failures),
        "values": values,
        "errors": failures,
    }


def run_throughput(base_url: str, model: str, timeout: int, max_tokens: int) -> dict[str, Any]:
    prompt = "Write a numbered list of concise deterministic facts about integer arithmetic."
    payload, elapsed = post_json(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        chat_payload(model, prompt, max_tokens),
        timeout,
    )
    prompt_tokens = usage_count(payload, "prompt_tokens", "input_tokens")
    completion_tokens = usage_count(payload, "completion_tokens", "output_tokens")
    timings = payload.get("timings", {})
    if not isinstance(timings, dict):
        timings = {}
    prompt_tps = numeric(timings.get("prompt_per_second"))
    generation_tps = numeric(timings.get("predicted_per_second"))
    if generation_tps is None and completion_tokens > 0 and elapsed > 0:
        generation_tps = completion_tokens / elapsed
    return {
        "score": float(completion_tokens > 0),
        "sample_count": 1,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "prompt_tps": prompt_tps,
        "generation_tps": generation_tps,
        "request_wall_seconds": elapsed,
        "failed_request_count": 0,
        "timeout_count": 0,
    }


def context_prompt(words: int) -> str:
    chunk = "alpha beta gamma delta epsilon zeta eta theta iota kappa "
    body = chunk * max(1, words // 10)
    return f"Return exactly OK after reading this context.\n{body}\nEND"


def run_context(base_url: str, model: str, timeout: int, targets: list[int], max_tokens: int) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for words in targets:
        try:
            payload, elapsed = post_json(
                f"{base_url.rstrip('/')}/v1/chat/completions",
                chat_payload(model, context_prompt(words), max_tokens),
                timeout,
            )
            results.append(
                {
                    "target_words": words,
                    "success": bool(payload.get("choices")),
                    "prompt_tokens": usage_count(payload, "prompt_tokens", "input_tokens"),
                    "wall_seconds": elapsed,
                    "error": "",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "target_words": words,
                    "success": False,
                    "prompt_tokens": 0,
                    "wall_seconds": 0.0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    failures = [row for row in results if not row["success"]]
    return {
        "score": (len(results) - len(failures)) / len(results),
        "sample_count": len(results),
        "failed_request_count": len(failures),
        "timeout_count": sum("timed out" in row["error"].lower() for row in failures),
        "max_success_prompt_tokens": max(
            (row["prompt_tokens"] for row in results if row["success"]),
            default=0,
        ),
        "results": results,
    }


def recorder_command(args: argparse.Namespace, test_id: str) -> list[str]:
    recorder = Path(args.scripts_dir).resolve() / "scripts" / "active" / "record_benchmark_result.py"
    return [
        sys.executable,
        str(recorder),
        "--model",
        args.model,
        "--test-id",
        test_id,
        "--run-class",
        args.run_class,
        "--harness",
        "bench-runtime",
        "--suite",
        args.run_name,
        "--methodology-id",
        METHODOLOGY[0],
        "--methodology-version",
        METHODOLOGY[1],
        "--comparison-group",
        METHODOLOGY[2],
        "--hardware-id",
        args.hardware_id,
        "--records",
        args.records,
        "--reference-output",
        args.reference_output,
        "--scoreboard-output",
        args.scoreboard_output,
    ]


def record_success(
    args: argparse.Namespace,
    test_id: str,
    result: dict[str, Any],
    config: dict[str, Any],
    refresh: bool,
) -> None:
    if args.no_record:
        return
    command = recorder_command(args, test_id)
    command.extend(
        [
            "--score",
            str(result["score"]),
            "--raw-harness-score",
            str(result["score"]),
            "--normalized-answer-score",
            str(result["score"]),
            "--metric",
            "request_success_rate",
            "--sample-count",
            str(result["sample_count"]),
            "--format-compatibility",
            "compatible",
            "--config-id",
            str(config["version"]),
            "--config-json",
            json.dumps(config, sort_keys=True),
            "--wall-time-seconds",
            str(result["wall_time_seconds"]),
            "--timeout-count",
            str(result.get("timeout_count", 0)),
            "--failed-request-count",
            str(result.get("failed_request_count", 0)),
            "--notes",
            json.dumps(result, sort_keys=True),
        ]
    )
    optional = {
        "--ttft-seconds": result.get("ttft_seconds"),
        "--prompt-tps": result.get("prompt_tps"),
        "--generation-tps": result.get("generation_tps"),
        "--peak-vram-mb": result.get("peak_vram_mb"),
        "--gpu-seconds": result.get("gpu_seconds"),
        "--energy-wh": result.get("energy_wh"),
    }
    for flag, value in optional.items():
        if value is not None:
            command.extend([flag, str(value)])
    if not refresh:
        command.append("--no-refresh")
    proc = subprocess.run(command, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"benchmark recorder exited with code {proc.returncode}")


def record_failure(args: argparse.Namespace, test_id: str, exc: Exception) -> None:
    if args.no_record:
        return
    command = recorder_command(args, test_id)
    command.extend(
        [
            "--status",
            "failure",
            "--failure-kind",
            "harness_error",
            "--failure-message",
            f"{type(exc).__name__}: {exc}",
            "--failed-request-count",
            "1",
        ]
    )
    proc = subprocess.run(command, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"failure recorder exited with code {proc.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure operational runtime behavior.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime-base", required=True)
    parser.add_argument("--config", default="/opt/bench/runtime_cases.json")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--run-class", choices=("smoke", "provisional", "validated", "full"), default="provisional")
    parser.add_argument("--gpu-ids", default="", help="Comma-separated physical GPU IDs for VRAM and energy telemetry")
    parser.add_argument("--hardware-id", required=True, help="Stable hardware/placement identity recorded with every result")
    parser.add_argument("--results-dir", default="/results")
    parser.add_argument("--scripts-dir", default="/benchmark-scripts")
    parser.add_argument("--records", default="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl")
    parser.add_argument("--reference-output", default="/mnt/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md")
    parser.add_argument("--scoreboard-output", default="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        parser.error("--run-name may contain only letters, digits, dot, underscore, and hyphen")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        gpu_ids = tuple(int(value.strip()) for value in args.gpu_ids.split(",") if value.strip())
    except ValueError as exc:
        parser.error(f"--gpu-ids must contain integers: {exc}")
    if any(value < 0 for value in gpu_ids) or len(set(gpu_ids)) != len(gpu_ids):
        parser.error("--gpu-ids must contain unique non-negative integers")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", args.hardware_id):
        parser.error("--hardware-id may contain only letters, digits, dot, underscore, colon, and hyphen")

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not str(config.get("version", "")):
        raise SystemExit("runtime config must be an object with a version")
    if gpu_ids:
        telemetry_rows(gpu_ids)
    record_config = dict(config)
    record_config["gpu_ids"] = list(gpu_ids)
    record_config["hardware_id"] = args.hardware_id
    models, _ = post_json(
        f"{args.runtime_base.rstrip('/')}/v1/chat/completions",
        chat_payload(args.model, "Reply OK.", 4),
        args.timeout,
    )
    if not models.get("choices"):
        raise SystemExit("runtime preflight response missing choices")

    operations: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        (
            "runtime_stability",
            lambda: run_stability(args.runtime_base, args.model, args.timeout, int(config["stability_requests"])),
        ),
        (
            "runtime_ttft",
            lambda: run_ttft(args.runtime_base, args.model, args.timeout, int(config["ttft_requests"])),
        ),
        (
            "runtime_throughput",
            lambda: run_throughput(args.runtime_base, args.model, args.timeout, int(config["throughput_max_tokens"])),
        ),
        (
            "runtime_context_reliability",
            lambda: run_context(
                args.runtime_base,
                args.model,
                args.timeout,
                [int(value) for value in config["context_word_targets"]],
                int(config["context_max_tokens"]),
            ),
        ),
    ]
    run_dir = Path(args.results_dir).resolve() / f"bench-runtime_{safe_name(args.model)}_{args.run_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    failures = 0
    for index, (test_id, operation) in enumerate(operations):
        try:
            result = measured(gpu_ids, operation)
            record_success(args, test_id, result, record_config, refresh=index == len(operations) - 1)
            results[test_id] = result
            print(f"{test_id}: success_rate={result['score']:.4f}")
        except Exception as exc:
            failures += 1
            record_failure(args, test_id, exc)
            results[test_id] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"{test_id}: ERROR {type(exc).__name__}: {exc}", file=sys.stderr)

    summary = {
        "suite": "bench-runtime",
        "methodology": {"id": METHODOLOGY[0], "version": METHODOLOGY[1], "comparison_group": METHODOLOGY[2]},
        "model": args.model,
        "run_name": args.run_name,
        "run_class": args.run_class,
        "gpu_ids": list(gpu_ids),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": record_config,
        "failures": failures,
        "results": results,
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
