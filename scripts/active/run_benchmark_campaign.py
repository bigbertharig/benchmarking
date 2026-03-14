#!/usr/bin/env python3
"""Run benchmark suites sequentially with campaign-level checkpointing."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


WORKER_SUITES = {"bench-reasoning", "bench-code", "bench-pipeline"}
SUPPORTED_SUITES = WORKER_SUITES | {"bench-knowledge"}


def now_iso() -> str:
    return datetime.now().isoformat()


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip()) or "campaign"


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


def parse_runtime_port(runtime_base: str) -> int:
    match = re.search(r":(\d+)(?:/|$)", runtime_base.strip())
    if not match:
        raise SystemExit(f"ERROR: could not parse port from runtime base '{runtime_base}'")
    return int(match.group(1))


def reservation_helper(shared_root: Path) -> Path:
    return shared_root / "scripts" / "benchmark_gpu_reservation.py"


def stop_worker_runtime(port: int) -> bool:
    """Stop the llama-server container listening on the given port to free GPU memory.

    Used when transitioning from worker-backed suites to bench-knowledge,
    which needs the GPU for its own internal llama-server.
    """
    proc = subprocess.run(
        ["docker", "ps", "--format", "{{.ID}} {{.Names}} {{.Image}}"],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        return False
    for line in proc.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        container_id = parts[0]
        # Check if this container is serving on our port
        inspect = subprocess.run(
            ["docker", "port", container_id],
            text=True, capture_output=True, check=False,
        )
        # Also check by container name pattern (llama-brain, llama-gpu-0, etc.)
        container_name = parts[1] if len(parts) >= 2 else ""
        if f"{port}" in (inspect.stdout or "") or container_name.startswith("llama-"):
            # Verify it's actually on our port by probing
            try:
                get_json(f"http://127.0.0.1:{port}/v1/models", timeout=3)
            except Exception:
                continue
            subprocess.run(
                ["docker", "stop", container_id],
                text=True, capture_output=True, check=False,
            )
            return True
    return False


def run_checked(cmd: List[str], *, env: Optional[Dict[str, str]] = None, cwd: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def read_worker_mapping(config_path: Path) -> Dict[str, Dict[str, Any]]:
    config = load_json(config_path)
    mapping: Dict[str, Dict[str, Any]] = {}
    for gpu in config.get("gpus", []):
        if not isinstance(gpu, dict):
            continue
        name = str(gpu.get("name", "")).strip()
        if not name:
            continue
        mapping[name] = gpu
    return mapping


def heartbeat_path(shared_root: Path, worker_cfg: Dict[str, Any]) -> Path:
    gpu_id = worker_cfg.get("id")
    if gpu_id is None:
        raise SystemExit(f"ERROR: worker config missing id: {worker_cfg}")
    return shared_root / "gpus" / f"gpu_{gpu_id}" / "heartbeat.json"


def read_heartbeat(shared_root: Path, worker_cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = heartbeat_path(shared_root, worker_cfg)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def probe_runtime_model(port: int) -> Optional[str]:
    try:
        data = get_json(f"http://127.0.0.1:{port}/v1/models", timeout=5)
    except Exception:
        return None
    models = data.get("data", [])
    if not models or not isinstance(models, list):
        return None
    first = models[0] if isinstance(models[0], dict) else {}
    model_id = str(first.get("id", "")).strip()
    return model_id or None


def queue_meta_task(shared_root: Path, task: Dict[str, Any]) -> str:
    queue_dir = shared_root / "tasks" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    task_id = str(task["task_id"]).strip()
    path = queue_dir / f"{task_id}.json"
    path.write_text(json.dumps(task, indent=2), encoding="utf-8")
    return task_id


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
        "created_by": "benchmark-campaign",
        "retry_count": 0,
    }
    if target_model:
        task["target_model"] = target_model
    if target_worker:
        task["target_worker"] = target_worker
    if command == "load_llm":
        task["load_mode"] = "single"
    return task


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


def ensure_worker_runtime(
    *,
    shared_root: Path,
    worker_name: str,
    worker_cfg: Dict[str, Any],
    port: int,
    model: str,
    timeout_s: int,
    allow_reload: bool,
    batch_id: str,
) -> Dict[str, Any]:
    hb = read_heartbeat(shared_root, worker_cfg)
    runtime_model = probe_runtime_model(port)
    runtime_healthy = bool(hb.get("runtime_healthy", True))
    loaded_model = str(hb.get("loaded_model", "") or "").strip()
    model_loaded = bool(hb.get("model_loaded", False))

    if runtime_healthy and model_loaded and loaded_model == model and runtime_model:
        return {
            "ready": True,
            "heartbeat_model": loaded_model,
            "runtime_model": runtime_model,
            "repaired": False,
        }

    if not allow_reload:
        raise SystemExit(
            f"ERROR: worker {worker_name} not ready for model {model}. "
            f"heartbeat_model={loaded_model or 'cold'} runtime_model={runtime_model or 'down'}"
        )

    if model_loaded:
        unload_task = build_meta_task(
            "unload_llm",
            batch_id=batch_id,
            target_model=loaded_model or model,
            target_worker=worker_name,
        )
        wait = wait_task_terminal(shared_root, queue_meta_task(shared_root, unload_task), timeout_s)
        if wait["state"] != "complete":
            raise SystemExit(f"ERROR: unload_llm failed for {worker_name}: {wait.get('error', wait['state'])}")

    load_task = build_meta_task(
        "load_llm",
        batch_id=batch_id,
        target_model=model,
        target_worker=worker_name,
    )
    wait = wait_task_terminal(shared_root, queue_meta_task(shared_root, load_task), timeout_s)
    if wait["state"] != "complete":
        raise SystemExit(f"ERROR: load_llm failed for {worker_name}: {wait.get('error', wait['state'])}")

    runtime_model = probe_runtime_model(port)
    hb = read_heartbeat(shared_root, worker_cfg)
    loaded_model = str(hb.get("loaded_model", "") or "").strip()
    if loaded_model != model or not runtime_model:
        raise SystemExit(
            f"ERROR: worker {worker_name} still not ready after reload. "
            f"heartbeat_model={loaded_model or 'cold'} runtime_model={runtime_model or 'down'}"
        )
    return {
        "ready": True,
        "heartbeat_model": loaded_model,
        "runtime_model": runtime_model,
        "repaired": True,
    }


def reserve_worker(shared_root: Path, worker_port: int, owner: str) -> None:
    helper = reservation_helper(shared_root)
    cmd = [
        "python3",
        str(helper),
        "--shared-path",
        str(shared_root),
        "--port",
        str(worker_port),
        "--owner",
        owner,
        "--reserved-for",
        "benchmark_campaign",
        "reserve",
    ]
    proc = run_checked(cmd)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "reservation failed")


def release_worker(shared_root: Path, worker_port: int, owner: str) -> None:
    helper = reservation_helper(shared_root)
    cmd = [
        "python3",
        str(helper),
        "--shared-path",
        str(shared_root),
        "--port",
        str(worker_port),
        "--owner",
        owner,
        "release",
    ]
    _ = run_checked(cmd)


def suite_results_root(shared_root: Path, suite: str) -> Path:
    return shared_root / "logs" / "benchmarks" / suite / "history"


def build_suite_command(
    *,
    shared_root: Path,
    benchmark_root: Path,
    suite: str,
    step: Dict[str, Any],
    model: str,
    worker_name: str,
    worker_port: int,
    run_name: str,
) -> List[str]:
    args = step.get("args", [])
    if isinstance(args, str):
        raise SystemExit(f"ERROR: suite args for {suite} must be a JSON array, not string")
    if not isinstance(args, list):
        raise SystemExit(f"ERROR: suite args for {suite} must be a JSON array")
    cmd: List[str]
    if suite == "bench-reasoning":
        cmd = [
            "docker", "run", "--rm", "--network", "host",
            "-v", f"{shared_root}:{shared_root}",
            "-v", f"{suite_results_root(shared_root, suite)}:/results",
            "-v", f"{benchmark_root}:/benchmark-scripts:ro",
            suite,
            "--model", model,
            "--runtime-base", f"http://localhost:{worker_port}",
            "--run-name", run_name,
        ]
    elif suite == "bench-code":
        cmd = [
            "docker", "run", "--rm", "--network", "host",
            "-v", f"{shared_root}:{shared_root}",
            "-v", f"{suite_results_root(shared_root, suite)}:/results",
            suite,
            "--model", model,
            "--runtime-base", f"http://localhost:{worker_port}",
            "--run-name", run_name,
        ]
    elif suite == "bench-pipeline":
        cmd = [
            "docker", "run", "--rm", "--network", "host",
            "-v", f"{shared_root}:{shared_root}",
            "-v", f"{suite_results_root(shared_root, suite)}:/results",
            "-v", f"{benchmark_root}:/benchmark-scripts:ro",
            suite,
            "--model", model,
            "--runtime-base", f"http://localhost:{worker_port}",
            "--run-name", run_name,
        ]
    elif suite == "bench-knowledge":
        gguf_path = str(step.get("gguf_path", "") or "").strip()
        reserve_gpu = str(step.get("reserve_gpu", worker_name) or "").strip()
        model_name = str(step.get("model_name", model) or "").strip()
        if not gguf_path:
            raise SystemExit("ERROR: bench-knowledge step requires gguf_path")
        gpu_device = str(step.get("gpu_device", "") or "").strip()
        if not gpu_device:
            raise SystemExit("ERROR: bench-knowledge step requires gpu_device")
        cmd = [
            "docker", "run", "--rm", "--gpus", f"device={gpu_device}",
            "-v", f"{shared_root}:{shared_root}",
            "-v", f"{shared_root / 'models'}:/models:ro",
            "-v", f"{suite_results_root(shared_root, suite)}:/results",
            "-v", f"{benchmark_root}:/benchmark-scripts:ro",
            suite,
            gguf_path,
            "--model-name", model_name,
            "--reserve-gpu", reserve_gpu,
            "--run-name", run_name,
        ]
    else:
        raise SystemExit(f"ERROR: unsupported suite '{suite}'")
    return cmd + [str(x) for x in args]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run benchmark suites sequentially with checkpointing.")
    ap.add_argument("campaign")
    ap.add_argument("--shared-root", default="/mnt/shared")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--config", default="config.benchmark.json")
    ap.add_argument("--load-timeout-seconds", type=int, default=300)
    ap.add_argument("--repair-runtime-on-drift", action="store_true", default=True)
    ap.add_argument("--no-repair-runtime-on-drift", dest="repair_runtime_on_drift", action="store_false")
    ap.add_argument("--release-on-failure", action="store_true", default=True)
    ap.add_argument("--keep-reserved-on-failure", dest="release_on_failure", action="store_false")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    benchmark_root = Path(__file__).resolve().parents[2]
    shared_root = Path(args.shared_root).expanduser().resolve()
    campaign_path = Path(args.campaign).expanduser().resolve()
    campaign = load_json(campaign_path)

    campaign_name = safe_name(str(campaign.get("name", "") or campaign_path.stem))
    run_id = safe_name(args.run_id or str(campaign.get("run_id", "") or campaign_name))
    run_dir = shared_root / "logs" / "benchmarks" / "campaigns" / "history" / campaign_name / run_id
    status_path = run_dir / "status.json"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    status = load_json(status_path) if status_path.exists() else {
        "campaign": campaign_name,
        "run_id": run_id,
        "campaign_path": str(campaign_path),
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "state": "starting",
        "steps": [],
    }

    config_path = shared_root / "agents" / args.config
    workers = read_worker_mapping(config_path)
    worker_name = str(campaign.get("target_worker") or campaign.get("gpu") or "").strip()
    if not worker_name:
        raise SystemExit("ERROR: campaign requires target_worker")
    if worker_name not in workers:
        raise SystemExit(f"ERROR: unknown target_worker '{worker_name}' in {config_path}")
    worker_cfg = workers[worker_name]
    worker_port = int(campaign.get("worker_port") or worker_cfg.get("port") or 0)
    if worker_port <= 0:
        raise SystemExit(f"ERROR: target worker {worker_name} has no port")
    model = str(campaign.get("model", "") or "").strip()
    if not model:
        raise SystemExit("ERROR: campaign requires model")
    stop_on_failure = bool(campaign.get("stop_on_failure", True))
    owner = f"benchmark-campaign:{campaign_name}:{run_id}"
    meta_batch_id = f"benchmark_campaign_{run_id}"

    raw_steps = campaign.get("suites", [])
    if not isinstance(raw_steps, list) or not raw_steps:
        raise SystemExit("ERROR: campaign requires non-empty suites list")

    steps: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise SystemExit(f"ERROR: suite step #{idx} must be an object")
        suite = str(raw.get("suite", "")).strip()
        if suite not in SUPPORTED_SUITES:
            raise SystemExit(f"ERROR: unsupported suite '{suite}' in step #{idx}")
        step_id = str(raw.get("id", "") or f"{idx:02d}_{suite}").strip()
        step_run_name = safe_name(f"{run_id}_{step_id}")
        steps.append({
            "id": step_id,
            "suite": suite,
            "args": raw.get("args", []),
            "enabled": bool(raw.get("enabled", True)),
            "run_name": step_run_name,
            "gguf_path": raw.get("gguf_path"),
            "gpu_device": raw.get("gpu_device"),
            "reserve_gpu": raw.get("reserve_gpu"),
            "model_name": raw.get("model_name"),
        })

    existing_steps = {}
    if isinstance(status.get("steps"), list):
        for existing in status["steps"]:
            if isinstance(existing, dict):
                existing_steps[str(existing.get("id", "")).strip()] = existing
    for step in steps:
        prior = existing_steps.get(step["id"])
        if isinstance(prior, dict):
            merged = dict(step)
            merged.update(prior)
            step.clear()
            step.update(merged)

    status["worker"] = {"name": worker_name, "port": worker_port, "model": model}
    status["steps"] = steps
    status["updated_at"] = now_iso()
    write_json(status_path, status)

    reserved = False
    overall_success = True
    try:
        ensure_worker_runtime(
            shared_root=shared_root,
            worker_name=worker_name,
            worker_cfg=worker_cfg,
            port=worker_port,
            model=model,
            timeout_s=args.load_timeout_seconds,
            allow_reload=True,
            batch_id=meta_batch_id,
        )
        reserve_worker(shared_root, worker_port, owner)
        reserved = True

        for index, step in enumerate(steps):
            if not step.get("enabled", True):
                step["state"] = "skipped"
                continue
            if step.get("state") == "completed":
                continue

            suite = step["suite"]
            if suite in WORKER_SUITES:
                release_worker(shared_root, worker_port, owner)
                reserved = False
                runtime_info = ensure_worker_runtime(
                    shared_root=shared_root,
                    worker_name=worker_name,
                    worker_cfg=worker_cfg,
                    port=worker_port,
                    model=model,
                    timeout_s=args.load_timeout_seconds,
                    allow_reload=args.repair_runtime_on_drift,
                    batch_id=meta_batch_id,
                )
                step["runtime_check"] = runtime_info
                reserve_worker(shared_root, worker_port, owner)
                reserved = True
            elif suite == "bench-knowledge":
                # Knowledge runs its own llama-server inside the container.
                # Stop the worker runtime first to free GPU memory.
                if reserved:
                    release_worker(shared_root, worker_port, owner)
                    reserved = False
                stopped = stop_worker_runtime(worker_port)
                step["worker_runtime_stopped"] = stopped

            log_path = logs_dir / f"{step['id']}.log"
            step["log_path"] = str(log_path)
            step["started_at"] = now_iso()
            step["state"] = "running"
            status["state"] = "running"
            status["current_step"] = step["id"]
            status["updated_at"] = now_iso()
            write_json(status_path, status)

            cmd = build_suite_command(
                shared_root=shared_root,
                benchmark_root=benchmark_root,
                suite=suite,
                step=step,
                model=model,
                worker_name=worker_name,
                worker_port=worker_port,
                run_name=step["run_name"],
            )
            env = os.environ.copy()
            if suite in WORKER_SUITES:
                env["BENCHMARK_DISABLE_AUTO_RESERVE"] = "1"
            env["BENCHMARK_RESERVATION_SHARED_PATH"] = str(shared_root)
            env["BENCHMARK_RESERVATION_OWNER"] = owner
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n[{now_iso()}] CMD: {' '.join(cmd)}\n")
                proc = subprocess.run(
                    cmd,
                    text=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    check=False,
                    env=env,
                )

            step["ended_at"] = now_iso()
            step["exit_code"] = int(proc.returncode)
            if proc.returncode == 0:
                step["state"] = "completed"
            else:
                step["state"] = "failed"
                overall_success = False
                if stop_on_failure:
                    status["state"] = "failed"
                    status["updated_at"] = now_iso()
                    write_json(status_path, status)
                    raise SystemExit(
                        f"ERROR: suite {suite} failed with exit code {proc.returncode}. log={log_path}"
                    )
            status["updated_at"] = now_iso()
            write_json(status_path, status)

        status["state"] = "completed" if overall_success else "completed_with_failures"
        status["completed_at"] = now_iso()
        status["updated_at"] = now_iso()
        write_json(status_path, status)
        return 0 if overall_success else 1
    finally:
        should_release = reserved and (overall_success or args.release_on_failure)
        if should_release:
            release_worker(shared_root, worker_port, owner)


if __name__ == "__main__":
    raise SystemExit(main())
