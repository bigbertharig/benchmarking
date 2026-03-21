#!/usr/bin/env python3
"""Run one benchmark suite across a predefined single-GPU cohort.

This is a thin scheduling wrapper:
- model selection comes from models.catalog.json
- model loading stays on the canonical prepare_llm_runtimes.py path
- runtime verification stays on the live worker ports
- unloading uses the same unload_llm meta-task path used by the runtime prep flow
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import shlex
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_MODELS_CATALOG = "plans/shoulders/benchmarking/models.catalog.json"
DEFAULT_RESULTS_LEDGER = "plans/shoulders/benchmarking/results/model_benchmark_records.jsonl"
DEFAULT_RESERVATION_PYTHON = "/home/bryan/llm-orchestration-venv/bin/python3"
WORKER_SUITES = {"bench-reasoning", "bench-code", "bench-pipeline", "bench-daedalmap"}
COHORTS = {"single_gpu_large", "small_models"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip()) or "item"


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: expected JSON object in {path}")
    return data


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_json(url: str, timeout: int = 10) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        return json.loads(text) if text.strip() else {}


def read_worker_mapping(config_path: Path) -> Dict[str, Dict[str, Any]]:
    config = load_json(config_path)
    mapping: Dict[str, Dict[str, Any]] = {}
    for gpu in config.get("gpus", []):
        if not isinstance(gpu, dict):
            continue
        name = str(gpu.get("name", "")).strip()
        if name:
            mapping[name] = gpu
    return mapping


def remote_run_checked(host: str, argv: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", host, *argv],
        text=True,
        capture_output=True,
        check=False,
    )


def kill_remote_batch_processes(host: str, batch_id: str) -> None:
    _ = remote_run_checked(host, ["pkill", "-f", batch_id])


def remote_popen(host: str, argv: List[str], *, stdout=None, stderr=None, text: bool = True, env: Optional[Dict[str, str]] = None) -> subprocess.Popen[str]:
    remote_cmd = " ".join(shlex.quote(part) for part in argv)
    if env:
        exports = " ".join(f"{shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items())
        remote_cmd = f"env {exports} {remote_cmd}"
    return subprocess.Popen(
        ["ssh", host, remote_cmd],
        text=text,
        stdout=stdout,
        stderr=stderr,
    )


def probe_runtime_model(host: str, port: int) -> Optional[str]:
    proc = subprocess.run(
        ["ssh", host, "curl", "-sS", f"http://127.0.0.1:{port}/v1/models"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads((proc.stdout or "").strip() or "{}")
    except Exception:
        return None
    models = data.get("data")
    if not isinstance(models, list) or not models:
        models = data.get("models", [])
    if not isinstance(models, list) or not models:
        return None
    first = models[0] if isinstance(models[0], dict) else {}
    model_id = str(first.get("id") or first.get("name") or first.get("model") or "").strip()
    return model_id or None


def scan_workers(host: str, workers: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    state: Dict[str, Dict[str, Any]] = {}
    for name, cfg in workers.items():
        port = int(cfg.get("port") or 0)
        if port <= 0:
            continue
        model = probe_runtime_model(host, port)
        state[name] = {
            "worker": name,
            "port": port,
            "loaded_model": model or "",
            "cold": not bool(model),
        }
    return state


def queue_meta_task(shared_root: Path, task: Dict[str, Any]) -> str:
    queue_dir = shared_root / "tasks" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    task_id = str(task["task_id"]).strip()
    path = queue_dir / f"{task_id}.json"
    path.write_text(json.dumps(task, indent=2), encoding="utf-8")
    return task_id


def assert_scheduler_queue_clean(shared_root: Path) -> None:
    queue_dir = shared_root / "tasks" / "queue"
    active = sorted(p for p in queue_dir.glob("*.json") if not p.name.endswith(".heartbeat.json"))
    if active:
        names = ", ".join(p.name for p in active[:5])
        extra = "" if len(active) <= 5 else f" (+{len(active) - 5} more)"
        raise SystemExit(f"ERROR: task queue is not clean before cohort run: {names}{extra}")


def clear_batch_queue_entries(shared_root: Path, batch_id: str) -> None:
    queue_dir = shared_root / "tasks" / "queue"
    for path in queue_dir.glob("*.json"):
        if path.name.endswith(".heartbeat.json"):
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        if str(data.get("batch_id", "")).strip() == batch_id:
            path.unlink(missing_ok=True)


def wait_task_terminal(shared_root: Path, task_id: str, timeout_s: int) -> Dict[str, Any]:
    complete_path = shared_root / "tasks" / "complete" / f"{task_id}.json"
    failed_path = shared_root / "tasks" / "failed" / f"{task_id}.json"
    deadline = time.time() + max(1, timeout_s)
    while time.time() < deadline:
        if complete_path.exists():
            return {"state": "complete", "path": str(complete_path)}
        if failed_path.exists():
            data = load_json(failed_path)
            result = data.get("result", {}) if isinstance(data.get("result"), dict) else {}
            return {
                "state": "failed",
                "path": str(failed_path),
                "error": str(result.get("error") or data.get("error") or "").strip(),
            }
        time.sleep(1.0)
    return {"state": "timeout", "error": f"task {task_id} timed out after {timeout_s}s"}


def task_result_is_usable(result: Dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    if bool(result.get("success")):
        return True
    if result.get("runtime_state") == "cold" and result.get("model_loaded") is False:
        return True
    return False


def read_terminal_task_result(wait_result: Dict[str, Any]) -> Dict[str, Any]:
    path = str(wait_result.get("path", "")).strip()
    if not path:
        return {}
    try:
        data = load_json(Path(path))
    except Exception:
        return {}
    result = data.get("result", {})
    return result if isinstance(result, dict) else {}


def build_meta_task(command: str, *, batch_id: str, target_model: str = "", target_worker: str = "") -> Dict[str, Any]:
    task = {
        "task_id": str(uuid.uuid4()),
        "type": "meta",
        "command": command,
        "batch_id": batch_id,
        "name": command,
        "priority": 10,
        "task_class": "meta",
        "depends_on": [],
        "executor": "worker",
        "status": "pending",
        "created_at": now_iso(),
        "created_by": "single-gpu-cohort-suite",
        "retry_count": 0,
    }
    if target_model:
        task["target_model"] = target_model
    if target_worker:
        task["target_worker"] = target_worker
    if command == "load_llm":
        task["load_mode"] = "single"
    return task


def unload_worker(shared_root: Path, worker_name: str, model: str, timeout_s: int, batch_id: str) -> Dict[str, Any]:
    task = build_meta_task(
        "unload_llm",
        batch_id=batch_id,
        target_model=model,
        target_worker=worker_name,
    )
    queue_meta_task(shared_root, task)
    wait_result = wait_task_terminal(shared_root, task["task_id"], timeout_s)
    wait_result["result"] = read_terminal_task_result(wait_result)
    return wait_result


def clear_all_workers(shared_root: Path, host: str, workers: Dict[str, Dict[str, Any]], timeout_s: int, batch_id: str) -> None:
    scan = scan_workers(host, workers)
    for worker_name, state in scan.items():
        loaded = str(state.get("loaded_model", "")).strip()
        if not loaded:
            continue
        result = unload_worker(shared_root, worker_name, loaded, timeout_s, batch_id)
        if result["state"] != "complete" or not task_result_is_usable(result.get("result", {})):
            raise SystemExit(
                f"ERROR: failed to unload {worker_name} ({loaded}): "
                f"{result.get('error', result['state'])} result={result.get('result', {})}"
            )


def reservation_helper(shared_root: Path) -> Path:
    return shared_root / "scripts" / "benchmark_gpu_reservation.py"


def reserve_worker(shared_root: Path, worker_port: int, owner: str, python_bin: str) -> None:
    cmd = [
        python_bin,
        str(reservation_helper(shared_root)),
        "--shared-path", str(shared_root),
        "--port", str(worker_port),
        "--owner", owner,
        "--reserved-for", "single_gpu_cohort_suite",
        "reserve",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "reservation failed")


def release_worker(shared_root: Path, worker_port: int, owner: str, python_bin: str) -> None:
    cmd = [
        python_bin,
        str(reservation_helper(shared_root)),
        "--shared-path", str(shared_root),
        "--port", str(worker_port),
        "--owner", owner,
        "release",
    ]
    _ = subprocess.run(cmd, text=True, capture_output=True, check=False)


def suite_results_root(shared_root: Path, suite: str) -> Path:
    return shared_root / "logs" / "benchmarks" / suite / "history"


def build_suite_command(
    *,
    remote_shared_root: str,
    suite: str,
    model: str,
    worker_port: int,
    run_name: str,
    suite_args: List[str],
    env_file: str,
) -> List[str]:
    if suite not in WORKER_SUITES:
        raise SystemExit(f"ERROR: unsupported suite '{suite}'")

    if suite == "bench-code":
        cmd = [
            "docker", "run", "--rm", "--network", "host",
            "-v", f"{remote_shared_root}:{remote_shared_root}",
            "-v", f"{Path(remote_shared_root) / 'logs' / 'benchmarks' / suite / 'history'}:/results",
            suite,
            "--model", model,
            "--runtime-base", f"http://localhost:{worker_port}",
            "--run-name", run_name,
        ]
    else:
        cmd = [
            "docker", "run", "--rm", "--network", "host",
            "-e", "BENCHMARK_DISABLE_AUTO_RESERVE=1",
            "-v", f"{remote_shared_root}:{remote_shared_root}",
            "-v", f"{Path(remote_shared_root) / 'logs' / 'benchmarks' / suite / 'history'}:/results",
            "-v", f"{Path(remote_shared_root) / 'plans' / 'shoulders' / 'benchmarking'}:/benchmark-scripts:ro",
        ]
        if suite == "bench-daedalmap" and env_file:
            cmd.extend(["--env-file", env_file])
        cmd.extend([
            suite,
            "--model", model,
            "--runtime-base", f"http://localhost:{worker_port}",
            "--run-name", run_name,
        ])
    return cmd + suite_args


def parse_model_size_billions(model_id: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)b", model_id.lower())
    if not match:
        return None
    return float(match.group(1))


def catalog_runtime_name(gguf_path: str) -> str:
    return Path(str(gguf_path)).name.strip()


def select_models(catalog_path: Path, cohort: str) -> List[str]:
    data = load_json(catalog_path)
    selected: List[str] = []
    for item in data.get("models", []):
        if not isinstance(item, dict):
            continue
        placement = str(item.get("placement", "")).strip()
        model_id = str(item.get("id", "")).strip()
        if placement != "single_gpu" or not model_id:
            continue
        size_b = parse_model_size_billions(model_id)
        if size_b is None:
            continue
        if cohort == "small_models" and size_b < 5.0:
            selected.append(model_id)
        elif cohort == "single_gpu_large" and 5.0 <= size_b <= 9.0:
            selected.append(model_id)
    return selected


def build_catalog_runtime_map(catalog_path: Path) -> Dict[str, str]:
    data = load_json(catalog_path)
    mapping: Dict[str, str] = {}
    for item in data.get("models", []):
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        gguf_path = str(item.get("gguf_path", "")).strip()
        if model_id and gguf_path:
            mapping[model_id] = catalog_runtime_name(gguf_path)
    return mapping


def load_existing_harness_models(records_path: Path, harness: str) -> set[str]:
    seen: set[str] = set()
    if not records_path.exists():
        return seen
    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("harness", "")).strip() != harness:
                continue
            model = str(row.get("model", "")).strip()
            if model:
                seen.add(model)
    return seen


def build_prepare_command(remote_shared_root: str, config_name: str, model: str, timeout_s: int, batch_id: str) -> List[str]:
    return [
        "python3",
        str(Path(remote_shared_root) / "scripts" / "prepare_llm_runtimes.py"),
        "--shared-root", str(remote_shared_root),
        "--config", config_name,
        "--clear-orphan-queue-locks",
        "--load-timeout-seconds", str(timeout_s),
        "--meta-batch-id", batch_id,
        "--models", model,
    ]


def start_load_process(host: str, remote_shared_root: str, config_name: str, model: str, timeout_s: int, batch_id: str) -> subprocess.Popen[str]:
    cmd = build_prepare_command(remote_shared_root, config_name, model, timeout_s, batch_id)
    return remote_popen(host, cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def model_matches(requested_model: str, actual_model: str, runtime_name_map: Dict[str, str]) -> bool:
    actual = actual_model.strip().lower()
    requested = requested_model.strip().lower()
    if not actual or not requested:
        return False
    if actual == requested:
        return True
    expected_runtime = runtime_name_map.get(requested_model, "").strip().lower()
    if expected_runtime and actual == expected_runtime:
        return True
    normalized_actual = re.sub(r"[^a-z0-9]+", "", actual)
    normalized_requested = re.sub(r"[^a-z0-9]+", "", requested)
    normalized_expected = re.sub(r"[^a-z0-9]+", "", expected_runtime)
    return (
        (normalized_requested and normalized_requested in normalized_actual)
        or (normalized_expected and normalized_expected in normalized_actual)
    )


def choose_loaded_worker(
    model: str,
    before: Dict[str, Dict[str, Any]],
    after: Dict[str, Dict[str, Any]],
    busy_workers: set[str],
    runtime_name_map: Dict[str, str],
) -> Optional[str]:
    candidates: List[str] = []
    for worker_name, after_state in after.items():
        after_model = str(after_state.get("loaded_model", "")).strip()
        before_model = str(before.get(worker_name, {}).get("loaded_model", "")).strip()
        if worker_name in busy_workers:
            continue
        if model_matches(model, after_model, runtime_name_map) and not model_matches(model, before_model, runtime_name_map):
            candidates.append(worker_name)
    if len(candidates) == 1:
        return candidates[0]
    for worker_name, after_state in after.items():
        after_model = str(after_state.get("loaded_model", "")).strip()
        before_cold = bool(before.get(worker_name, {}).get("cold", False))
        if worker_name in busy_workers:
            continue
        if model_matches(model, after_model, runtime_name_map) and before_cold:
            return worker_name
    return None


def choose_loaded_worker_from_prepare_output(
    model: str,
    output: str,
    before: Dict[str, Dict[str, Any]],
    busy_workers: set[str],
    runtime_name_map: Dict[str, str],
) -> Optional[str]:
    in_final_scan = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line == "== final-scan ==":
            in_final_scan = True
            continue
        if not in_final_scan:
            continue
        if line.startswith("== "):
            break
        match = re.match(r"([A-Za-z0-9_-]+)\s+port=\d+\s+model=(.+)$", line)
        if not match:
            continue
        worker_name = match.group(1).strip()
        actual_model = match.group(2).strip()
        before_model = str(before.get(worker_name, {}).get("loaded_model", "")).strip()
        before_cold = bool(before.get(worker_name, {}).get("cold", False))
        if worker_name in busy_workers:
            continue
        if model_matches(model, actual_model, runtime_name_map) and (before_cold or not model_matches(model, before_model, runtime_name_map)):
            return worker_name
    return None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run one suite across a single-GPU cohort with slot recycling.")
    ap.add_argument("suite")
    ap.add_argument("cohort", choices=sorted(COHORTS))
    ap.add_argument("--shared-root", default="/mnt/shared")
    ap.add_argument("--remote-shared-root", default="/mnt/shared")
    ap.add_argument("--runner-host", default="gpu")
    ap.add_argument("--config", default="config.benchmark.json")
    ap.add_argument("--models-catalog", default=DEFAULT_MODELS_CATALOG)
    ap.add_argument("--results-ledger", default=DEFAULT_RESULTS_LEDGER)
    ap.add_argument("--reservation-python", default=DEFAULT_RESERVATION_PYTHON)
    ap.add_argument("--suite-arg", action="append", default=[], help="Repeatable suite arg token, appended as-is")
    ap.add_argument("--env-file", default="", help="Optional env file for bench-daedalmap")
    ap.add_argument("--run-prefix", default="")
    ap.add_argument("--poll-seconds", type=float, default=2.0)
    ap.add_argument("--load-timeout-seconds", type=int, default=300)
    ap.add_argument("--unload-timeout-seconds", type=int, default=180)
    ap.add_argument("--max-models", type=int, default=0)
    ap.add_argument("--existing-policy", choices=["skip", "rerun"], default="skip")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    if args.suite not in WORKER_SUITES:
        raise SystemExit(f"ERROR: suite must be one of {sorted(WORKER_SUITES)}")

    shared_root = Path(args.shared_root).expanduser().resolve()
    reservation_python = str(args.reservation_python).strip()
    if not reservation_python:
        raise SystemExit("ERROR: --reservation-python must not be empty")
    if not Path(reservation_python).exists():
        raise SystemExit(f"ERROR: reservation python not found: {reservation_python}")
    runner_host = str(args.runner_host).strip()
    remote_shared_root = str(args.remote_shared_root).strip()
    catalog_path = Path(args.models_catalog).expanduser()
    if not catalog_path.is_absolute():
        catalog_path = (shared_root / catalog_path).resolve()
    results_ledger = Path(args.results_ledger).expanduser()
    if not results_ledger.is_absolute():
        results_ledger = (shared_root / results_ledger).resolve()
    config_path = shared_root / "agents" / args.config

    workers = read_worker_mapping(config_path)
    worker_names = sorted(workers.keys(), key=lambda name: int(workers[name].get("id", 0)))
    if not worker_names:
        raise SystemExit("ERROR: no worker GPUs found in config")

    models = select_models(catalog_path, args.cohort)
    runtime_name_map = build_catalog_runtime_map(catalog_path)
    if args.max_models > 0:
        models = models[: args.max_models]
    if not models:
        raise SystemExit(f"ERROR: cohort {args.cohort} resolved to zero models")

    skipped_existing: List[str] = []
    if args.existing_policy == "skip":
        existing_models = load_existing_harness_models(results_ledger, args.suite)
        if existing_models:
            skipped_existing = [model for model in models if model in existing_models]
            models = [model for model in models if model not in existing_models]
    if not models:
        raise SystemExit(
            f"ERROR: no models left to run for cohort {args.cohort} after applying existing-policy={args.existing_policy}"
        )

    run_name = safe_name(args.run_prefix or f"{args.suite}_{args.cohort}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    status_path = shared_root / "logs" / "benchmarks" / "cohort_suite_runs" / "history" / run_name / "status.json"
    logs_dir = status_path.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    status: Dict[str, Any] = {
        "run_name": run_name,
        "suite": args.suite,
        "cohort": args.cohort,
        "models_selected": models,
        "workers": [{"name": name, "port": workers[name]["port"]} for name in worker_names],
        "runner_host": runner_host,
        "remote_shared_root": remote_shared_root,
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "state": "starting",
        "existing_policy": args.existing_policy,
        "skipped_existing": skipped_existing,
        "pending_models": list(models),
        "completed_models": [],
        "failed_models": [],
        "loading": None,
        "running": {},
    }
    write_json(status_path, status)

    if args.dry_run:
        for model in skipped_existing:
            print(f"skip_existing={model}")
        for model in models:
            print(f"model={model}")
        print(f"workers={','.join(worker_names)}")
        print(f"status_path={status_path}")
        return 0

    batch_id = f"cohort_suite_{safe_name(run_name)}"
    owner_prefix = f"cohort-suite:{run_name}"

    assert_scheduler_queue_clean(shared_root)
    clear_all_workers(shared_root, runner_host, workers, args.unload_timeout_seconds, batch_id)

    pending_models = list(models)
    running: Dict[str, Dict[str, Any]] = {}
    failed_models: List[Dict[str, Any]] = []
    completed_models: List[Dict[str, Any]] = []
    load_state: Optional[Dict[str, Any]] = None

    run_error: Optional[str] = None
    try:
        while pending_models or running or load_state:
            current_scan = scan_workers(runner_host, workers)
            free_workers = [
                name for name in worker_names
                if not current_scan[name]["loaded_model"] and name not in running
            ]

            if load_state is None and pending_models and free_workers:
                assert_scheduler_queue_clean(shared_root)
                model = pending_models.pop(0)
                before_scan = current_scan
                proc = start_load_process(
                    host=runner_host,
                    remote_shared_root=remote_shared_root,
                    config_name=args.config,
                    model=model,
                    timeout_s=args.load_timeout_seconds,
                    batch_id=batch_id,
                )
                load_state = {
                    "model": model,
                    "proc": proc,
                    "started_at": now_iso(),
                    "before_scan": before_scan,
                }
                status["loading"] = {"model": model, "started_at": load_state["started_at"]}
                status["pending_models"] = list(pending_models)
                status["updated_at"] = now_iso()
                status["state"] = "running"
                write_json(status_path, status)

            if load_state is not None:
                proc = load_state["proc"]
                returncode = proc.poll()
                if returncode is not None:
                    output = proc.stdout.read() if proc.stdout else ""
                    model = str(load_state["model"])
                    load_log_path = logs_dir / f"{safe_name(model)}_load.log"
                    load_log_path.write_text(output, encoding="utf-8")
                    after_scan = scan_workers(runner_host, workers)
                    worker_name = choose_loaded_worker(
                        model,
                        before=load_state["before_scan"],
                        after=after_scan,
                        busy_workers=set(running.keys()),
                        runtime_name_map=runtime_name_map,
                    )
                    if not worker_name:
                        worker_name = choose_loaded_worker_from_prepare_output(
                            model=model,
                            output=output,
                            before=load_state["before_scan"],
                            busy_workers=set(running.keys()),
                            runtime_name_map=runtime_name_map,
                        )
                    if returncode != 0 or not worker_name:
                        failed_models.append({
                            "model": model,
                            "phase": "load",
                            "worker": worker_name or "",
                            "returncode": returncode,
                            "load_log_path": str(load_log_path),
                        })
                        status["failed_models"] = failed_models
                    else:
                        port = int(workers[worker_name]["port"])
                        reserve_owner = f"{owner_prefix}:{worker_name}"
                        reserve_worker(shared_root, port, reserve_owner, reservation_python)
                        log_path = logs_dir / f"{safe_name(model)}_{worker_name}.log"
                        cmd = build_suite_command(
                            remote_shared_root=remote_shared_root,
                            suite=args.suite,
                            model=model,
                            worker_port=port,
                            run_name=safe_name(f"{run_name}_{safe_name(model)}"),
                            suite_args=list(args.suite_arg),
                            env_file=args.env_file,
                        )
                        env = os.environ.copy()
                        env["BENCHMARK_DISABLE_AUTO_RESERVE"] = "1"
                        env["BENCHMARK_RESERVATION_SHARED_PATH"] = remote_shared_root
                        env["BENCHMARK_RESERVATION_OWNER"] = reserve_owner
                        log_file = open(log_path, "a", encoding="utf-8")
                        log_file.write(f"\n[{now_iso()}] CMD: {' '.join(cmd)}\n")
                        bench_proc = remote_popen(
                            runner_host,
                            cmd,
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            env=env,
                        )
                        running[worker_name] = {
                            "model": model,
                            "port": port,
                            "proc": bench_proc,
                            "log_file": log_file,
                            "log_path": str(log_path),
                            "owner": reserve_owner,
                            "started_at": now_iso(),
                        }
                        status["running"][worker_name] = {
                            "model": model,
                            "port": port,
                            "log_path": str(log_path),
                            "load_log_path": str(load_log_path),
                            "started_at": running[worker_name]["started_at"],
                        }
                    load_state = None
                    status["loading"] = None
                    status["updated_at"] = now_iso()
                    write_json(status_path, status)

            finished_workers: List[str] = []
            for worker_name, info in list(running.items()):
                proc = info["proc"]
                returncode = proc.poll()
                if returncode is None:
                    continue
                info["log_file"].close()
                release_worker(shared_root, int(info["port"]), str(info["owner"]), reservation_python)
                unload_result = unload_worker(
                    shared_root=shared_root,
                    worker_name=worker_name,
                    model=str(info["model"]),
                    timeout_s=args.unload_timeout_seconds,
                    batch_id=batch_id,
                )
                record = {
                    "model": info["model"],
                    "worker": worker_name,
                    "port": info["port"],
                    "exit_code": int(returncode),
                    "log_path": info["log_path"],
                    "unload_state": unload_result["state"],
                    "unload_result": unload_result.get("result", {}),
                    "ended_at": now_iso(),
                }
                if returncode == 0 and unload_result["state"] == "complete" and task_result_is_usable(unload_result.get("result", {})):
                    completed_models.append(record)
                else:
                    failed_models.append(record)
                finished_workers.append(worker_name)

            for worker_name in finished_workers:
                running.pop(worker_name, None)
                status["running"].pop(worker_name, None)
            status["completed_models"] = completed_models
            status["failed_models"] = failed_models
            status["pending_models"] = list(pending_models)
            status["updated_at"] = now_iso()
            write_json(status_path, status)

            time.sleep(max(0.5, float(args.poll_seconds)))

    except Exception as e:
        run_error = str(e).strip() or repr(e)
    finally:
        kill_remote_batch_processes(runner_host, batch_id)
        clear_batch_queue_entries(shared_root, batch_id)
        for worker_name, info in list(running.items()):
            if info["proc"].poll() is None:
                info["proc"].terminate()
            info["log_file"].close()
            release_worker(shared_root, int(info["port"]), str(info["owner"]), reservation_python)

    status["ended_at"] = now_iso()
    if run_error:
        status["state"] = "failed"
        status["error"] = run_error
    else:
        status["state"] = "completed" if not failed_models else "failed"
    status["updated_at"] = now_iso()
    status["completed_models"] = completed_models
    status["failed_models"] = failed_models
    status["pending_models"] = list(pending_models)
    status["loading"] = status.get("loading") if load_state is not None else None
    status["running"] = status.get("running", {})
    write_json(status_path, status)
    return 0 if not failed_models and not run_error else 1


if __name__ == "__main__":
    raise SystemExit(main())
