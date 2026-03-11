#!/usr/bin/env python3
"""Measure practical llama-server context capacity per worker GPU.

Run on the GPU rig:
  python3 /mnt/shared/plans/shoulders/benchmarking/context_window_benchmark.py

By default this reads /mnt/shared/agents/config.json, tests configured worker
GPUs that already have a live llama runtime on their assigned port, and writes
CSV/JSON reports under /mnt/shared/logs/benchmarks/.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_config(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_cmd(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return p.returncode, p.stdout, p.stderr


def nvidia_row(gpu_id: int) -> dict[str, Any] | None:
    rc, out, err = run_cmd(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.used,memory.total,temperature.gpu,power.draw,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=5,
    )
    if rc != 0:
        raise RuntimeError(f"nvidia-smi failed: {err.strip() or 'command unavailable'}")
    for line in out.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            idx = int(parts[0])
        except ValueError:
            continue
        if idx != gpu_id:
            continue
        try:
            return {
                "gpu_id": idx,
                "mem_used_mb": int(float(parts[1])),
                "mem_total_mb": int(float(parts[2])),
                "temp_c": int(float(parts[3])),
                "power_w": float(parts[4]),
                "util_pct": int(float(parts[5])),
            }
        except ValueError:
            return None
    return None


def require_nvidia_smi() -> None:
    rc, _, err = run_cmd(["nvidia-smi", "--help"], timeout=5)
    if rc != 0:
        raise SystemExit(f"nvidia-smi is required on the GPU rig: {err.strip() or 'command unavailable'}")


def llama_get_json(url: str, timeout_s: int) -> tuple[bool, dict[str, Any], str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            return False, {}, f"Non-dict JSON response from {url}"
        return True, parsed, ""
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        return False, {}, f"HTTP {e.code}: {err[:300]}"
    except Exception as e:
        return False, {}, str(e)


def llama_models(host: str, port: int, timeout_s: int) -> tuple[bool, list[str], str]:
    ok, payload, err = llama_get_json(f"http://{host}:{port}/v1/models", timeout_s)
    if not ok:
        return False, [], err
    models: list[str] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            models.append(model_id)
    return True, models, ""


def model_loaded(loaded_models: list[str], target_model: str) -> bool:
    target = target_model.strip()
    if not target:
        return False
    target_base = target.split(":")[0]
    for name in loaded_models:
        current = name.strip()
        if current == target:
            return True
        if current.split(":")[0] == target_base:
            return True
    return False


def display_model_name(raw_model: str) -> str:
    value = str(raw_model or "").strip()
    if not value:
        return ""
    return Path(value).name if "/" in value else value


def build_prompt(word_count: int) -> str:
    chunk = "alpha beta gamma delta epsilon zeta eta theta iota kappa "
    reps = max(1, int(word_count / 10))
    body = chunk * reps
    return (
        "Context stress test. Return the single token OK.\n\n"
        "BEGIN CONTEXT:\n"
        f"{body}\n"
        "END CONTEXT.\n"
    )


def llama_chat(
    host: str,
    port: int,
    prompt: str,
    timeout_s: int,
    max_tokens: int,
) -> tuple[bool, dict[str, Any], str]:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    url = f"http://{host}:{port}/v1/chat/completions"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            return False, {}, "Non-dict JSON chat response"
        return True, parsed, ""
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        return False, {}, f"HTTP {e.code}: {err[:300]}"
    except Exception as e:
        return False, {}, str(e)


def prompt_token_count(payload: dict[str, Any]) -> int:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "input_tokens"):
            value = usage.get(key)
            if value not in (None, ""):
                try:
                    return int(value)
                except Exception:
                    pass
    return 0


def completion_token_count(payload: dict[str, Any]) -> int:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        for key in ("completion_tokens", "output_tokens"):
            value = usage.get(key)
            if value not in (None, ""):
                try:
                    return int(value)
                except Exception:
                    pass
    return 0


def selected_worker_profile(config: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    defaults = config.get("llama_single_defaults")
    profile = dict(defaults) if isinstance(defaults, dict) else {}

    model_profiles = config.get("llama_single_profiles")
    if isinstance(model_profiles, dict):
        model_profile = model_profiles.get(str(worker.get("model") or "").strip())
        if isinstance(model_profile, dict):
            profile.update(model_profile)

    worker_profile = worker.get("llama_runtime")
    if isinstance(worker_profile, dict):
        profile.update(worker_profile)
    return profile


def ensure_workers_ready(
    workers: list[dict[str, Any]],
    host: str,
    timeout_s: int,
) -> list[dict[str, Any]]:
    ready_workers: list[dict[str, Any]] = []
    print("\nChecking active llama runtimes on target workers...")
    for worker in workers:
        gpu_id = int(worker["id"])
        name = str(worker.get("name", f"gpu-{gpu_id}"))
        model = str(worker.get("model", "")).strip()
        port = int(worker.get("port", 11434 + gpu_id))
        ok, models, err = llama_models(host, port, timeout_s=min(timeout_s, 10))
        if not ok:
            print(f"  {name}: skipped, /v1/models unavailable on {port} ({err[:120]})")
            continue
        if not models:
            print(f"  {name}: skipped, /v1/models returned no model ids")
            continue
        live_model = models[0]
        ready = dict(worker)
        ready["live_model"] = live_model
        ready["configured_model"] = model
        ready_workers.append(ready)
        if model and not model_loaded(models, model):
            print(
                f"  {name}: ready on {port} with loaded model "
                f"{display_model_name(live_model)} (config expects {model})"
            )
        else:
            print(f"  {name}: ready on {port} ({display_model_name(live_model)})")
    return ready_workers


@dataclass
class PeakTracker:
    gpu_id: int
    stop: threading.Event
    peak_mem_mb: int = 0
    peak_util_pct: int = 0
    peak_temp_c: int = 0
    last_power_w: float = 0.0

    def loop(self) -> None:
        while not self.stop.is_set():
            try:
                row = nvidia_row(self.gpu_id)
            except Exception:
                row = None
            if row:
                self.peak_mem_mb = max(self.peak_mem_mb, int(row["mem_used_mb"]))
                self.peak_util_pct = max(self.peak_util_pct, int(row["util_pct"]))
                self.peak_temp_c = max(self.peak_temp_c, int(row["temp_c"]))
                self.last_power_w = float(row["power_w"])
            time.sleep(0.2)


def select_workers(config: dict[str, Any], names_csv: str | None) -> list[dict[str, Any]]:
    workers = [w for w in config.get("gpus", []) if isinstance(w, dict)]
    if not names_csv:
        return workers
    names = {x.strip() for x in names_csv.split(",") if x.strip()}
    return [w for w in workers if str(w.get("name")) in names]


def test_worker(
    config: dict[str, Any],
    worker: dict[str, Any],
    host: str,
    start_words: int,
    step_words: int,
    max_words: int,
    timeout_s: int,
    max_tokens: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gpu_id = int(worker["id"])
    name = str(worker.get("name", f"gpu-{gpu_id}"))
    model = str(worker.get("live_model") or worker.get("model") or "").strip()
    configured_model = str(worker.get("configured_model") or worker.get("model") or "").strip()
    port = int(worker.get("port", 11434 + gpu_id))
    profile = selected_worker_profile(config, worker)

    rows: list[dict[str, Any]] = []
    last_success_words = 0
    last_success_prompt_tokens = 0
    first_failure: str | None = None

    llama_chat(host, port, "READY?", timeout_s, max_tokens=4)

    for words in range(start_words, max_words + 1, step_words):
        before = nvidia_row(gpu_id) or {}
        stop_evt = threading.Event()
        tracker = PeakTracker(gpu_id=gpu_id, stop=stop_evt)
        thread = threading.Thread(target=tracker.loop, daemon=True)
        thread.start()
        t0 = time.time()
        ok, out, err = llama_chat(host, port, build_prompt(words), timeout_s, max_tokens=max_tokens)
        elapsed = time.time() - t0
        stop_evt.set()
        thread.join(timeout=1.0)
        after = nvidia_row(gpu_id) or {}

        prompt_tokens = prompt_token_count(out)
        completion_tokens = completion_token_count(out)
        finish_reason = ""
        choices = out.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                finish_reason = str(first_choice.get("finish_reason") or "").strip()

        row = {
            "worker": name,
            "gpu_id": gpu_id,
            "port": port,
            "model": model,
            "configured_model": configured_model,
            "ctx_size_configured": profile.get("ctx_size"),
            "batch_size_configured": profile.get("batch_size"),
            "parallel_configured": profile.get("parallel"),
            "input_words": words,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "finish_reason": finish_reason,
            "request_ok": ok,
            "error": err[:260] if err else "",
            "elapsed_s": round(elapsed, 3),
            "mem_before_mb": before.get("mem_used_mb"),
            "mem_after_mb": after.get("mem_used_mb"),
            "mem_peak_mb": tracker.peak_mem_mb or after.get("mem_used_mb"),
            "mem_total_mb": after.get("mem_total_mb") or before.get("mem_total_mb"),
            "gpu_util_peak_pct": tracker.peak_util_pct,
            "gpu_temp_peak_c": tracker.peak_temp_c or after.get("temp_c"),
            "power_last_w": round(tracker.last_power_w, 2),
        }
        rows.append(row)

        if ok:
            last_success_words = words
            if prompt_tokens > 0:
                last_success_prompt_tokens = prompt_tokens
        elif first_failure is None:
            first_failure = f"words={words}: {err[:180]}"
            break

        mem_total = row.get("mem_total_mb") or 0
        mem_peak = row.get("mem_peak_mb") or 0
        if mem_total and mem_peak and (mem_peak / mem_total) >= 0.985:
            first_failure = f"memory ceiling reached at words={words}"
            break

        # Do not treat finish_reason=length as a hard context ceiling.
        # Some models hit generation caps despite having prompt headroom.

    summary = {
        "worker": name,
        "gpu_id": gpu_id,
        "port": port,
        "model": model,
        "configured_model": configured_model,
        "ctx_size_configured": profile.get("ctx_size"),
        "last_success_words": last_success_words,
        "last_success_prompt_tokens": last_success_prompt_tokens,
        "first_failure": first_failure or "",
        "attempts": len(rows),
    }
    return rows, summary


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Benchmark llama runtime context growth and VRAM behavior per GPU worker")
    ap.add_argument("--config", default="/mnt/shared/agents/config.json")
    ap.add_argument("--host", default="127.0.0.1", help="llama runtime host on rig")
    ap.add_argument("--workers", default="", help="Comma-separated worker names (default: all)")
    ap.add_argument("--start-words", type=int, default=800)
    ap.add_argument("--step-words", type=int, default=800)
    ap.add_argument("--max-words", type=int, default=20000)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    ap.add_argument("--max-tokens", type=int, default=4)
    ap.add_argument("--log-dir", default="/mnt/shared/logs/benchmarks")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    require_nvidia_smi()
    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)
    if str(cfg.get("runtime_backend", "llama") or "llama").strip() != "llama":
        raise SystemExit("context_window_benchmark.py only supports runtime_backend=llama")

    workers = select_workers(cfg, args.workers or None)
    if not workers:
        raise SystemExit("No matching workers found in config.")

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    csv_path = log_dir / f"context_window_benchmark_{stamp}.csv"
    json_path = log_dir / f"context_window_benchmark_{stamp}.json"

    ready_workers = ensure_workers_ready(
        workers=workers,
        host=args.host,
        timeout_s=args.timeout_seconds,
    )
    if not ready_workers:
        raise SystemExit(
            "No ready llama worker runtimes found. Start benchmark mode and load the target worker model first."
        )

    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    print(f"Context benchmark on {len(ready_workers)} worker(s)")
    print(f"Config: {cfg_path}")
    print(f"Output: {csv_path}")

    for worker in ready_workers:
        name = worker.get("name")
        gpu_id = worker.get("id")
        port = worker.get("port", 11434 + int(gpu_id))
        model = worker.get("live_model") or worker.get("model")
        print(f"\n--- {name} (gpu={gpu_id}, port={port}, model={model}) ---")
        rows, summary = test_worker(
            config=cfg,
            worker=worker,
            host=args.host,
            start_words=args.start_words,
            step_words=args.step_words,
            max_words=args.max_words,
            timeout_s=args.timeout_seconds,
            max_tokens=args.max_tokens,
        )
        all_rows.extend(rows)
        summaries.append(summary)
        print(
            f"last_success_words={summary['last_success_words']} "
            f"prompt_tokens={summary['last_success_prompt_tokens']} "
            f"failure='{summary['first_failure']}'"
        )

    if all_rows:
        fields = list(all_rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in all_rows:
                writer.writerow(row)

    report = {
        "generated_at": datetime.now().isoformat(),
        "config": str(cfg_path),
        "host": args.host,
        "workers_tested": [summary["worker"] for summary in summaries],
        "params": {
            "start_words": args.start_words,
            "step_words": args.step_words,
            "max_words": args.max_words,
            "timeout_seconds": args.timeout_seconds,
            "max_tokens": args.max_tokens,
        },
        "summary": summaries,
        "rows": all_rows,
        "csv_path": str(csv_path),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nSummary:")
    for summary in summaries:
        print(
            f"{summary['worker']}: last_success_words={summary['last_success_words']}, "
            f"prompt_tokens={summary['last_success_prompt_tokens']}, "
            f"failure={summary['first_failure'] or '-'}"
        )
    print(f"\nWrote CSV:  {csv_path}")
    print(f"Wrote JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
