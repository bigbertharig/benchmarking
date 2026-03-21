#!/usr/bin/env python3
"""Run one benchmark suite across many models on a single worker."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


WORKER_SUITES = {"bench-reasoning", "bench-code", "bench-pipeline", "bench-daedalmap"}


def now_iso() -> str:
    return datetime.now().isoformat()


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


def run_checked(cmd: List[str], *, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


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
    if not isinstance(models, list) or not models:
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


def build_meta_task(command: str, *, batch_id: str, target_model: str, target_worker: str) -> Dict[str, Any]:
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
        "created_by": "multi-model-suite-campaign",
        "retry_count": 0,
        "target_model": target_model,
        "target_worker": target_worker,
    }
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

    if model_loaded and loaded_model:
        unload_task = build_meta_task(
            "unload_llm",
            batch_id=batch_id,
            target_model=loaded_model,
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
            f"ERROR: worker {worker_name} not ready after load. "
            f"heartbeat_model={loaded_model or 'cold'} runtime_model={runtime_model or 'down'}"
        )

    return {
        "ready": True,
        "heartbeat_model": loaded_model,
        "runtime_model": runtime_model,
        "repaired": True,
    }


def reservation_helper(shared_root: Path) -> Path:
    return shared_root / "scripts" / "benchmark_gpu_reservation.py"


def reserve_worker(shared_root: Path, worker_port: int, owner: str) -> None:
    cmd = [
        "python3",
        str(reservation_helper(shared_root)),
        "--shared-path", str(shared_root),
        "--port", str(worker_port),
        "--owner", owner,
        "--reserved-for", "multi_model_suite_campaign",
        "reserve",
    ]
    proc = run_checked(cmd)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "reservation failed")


def release_worker(shared_root: Path, worker_port: int, owner: str) -> None:
    cmd = [
        "python3",
        str(reservation_helper(shared_root)),
        "--shared-path", str(shared_root),
        "--port", str(worker_port),
        "--owner", owner,
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
    model: str,
    worker_port: int,
    run_name: str,
    base_args: List[str],
    env_file: str,
) -> List[str]:
    if suite not in WORKER_SUITES:
        raise SystemExit(f"ERROR: suite {suite} is not supported by multi-model suite campaigns")

    if suite == "bench-code":
        cmd = [
            "docker", "run", "--rm", "--network", "host",
            "-v", f"{shared_root}:{shared_root}",
            "-v", f"{suite_results_root(shared_root, suite)}:/results",
            suite,
            "--model", model,
            "--runtime-base", f"http://localhost:{worker_port}",
            "--run-name", run_name,
        ]
    else:
        cmd = [
            "docker", "run", "--rm", "--network", "host",
            "-e", "BENCHMARK_DISABLE_AUTO_RESERVE=1",
            "-v", f"{shared_root}:{shared_root}",
            "-v", f"{suite_results_root(shared_root, suite)}:/results",
            "-v", f"{benchmark_root}:/benchmark-scripts:ro",
        ]
        if suite == "bench-daedalmap" and env_file:
            cmd.extend(["--env-file", env_file])
        cmd.extend([
            suite,
            "--model", model,
            "--runtime-base", f"http://localhost:{worker_port}",
            "--run-name", run_name,
        ])
    return cmd + base_args


def validate_string_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, (str, int, float)) for item in value):
        raise SystemExit(f"ERROR: {field_name} must be a JSON array of scalars")
    return [str(item) for item in value]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run one benchmark suite across many models.")
    ap.add_argument("campaign")
    ap.add_argument("--shared-root", default="/mnt/shared")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--config", default="config.benchmark.json")
    ap.add_argument("--load-timeout-seconds", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true", help="Validate manifest and print resolved commands without loading models")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    benchmark_root = Path(__file__).resolve().parents[2]
    shared_root = Path(args.shared_root).expanduser().resolve()
    campaign_path = Path(args.campaign).expanduser().resolve()
    campaign = load_json(campaign_path)

    campaign_name = safe_name(str(campaign.get("name", "") or campaign_path.stem))
    run_id = safe_name(args.run_id or str(campaign.get("run_id", "") or campaign_name))
    run_dir = shared_root / "logs" / "benchmarks" / "multi_model_suite_campaigns" / "history" / campaign_name / run_id
    status_path = run_dir / "status.json"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    suite = str(campaign.get("suite", "") or "").strip()
    if suite not in WORKER_SUITES:
        raise SystemExit(f"ERROR: campaign suite must be one of {sorted(WORKER_SUITES)}")

    target_worker = str(campaign.get("target_worker", "") or "").strip()
    if not target_worker:
        raise SystemExit("ERROR: campaign requires target_worker")

    config_path = shared_root / "agents" / args.config
    workers = read_worker_mapping(config_path)
    if target_worker not in workers:
        raise SystemExit(f"ERROR: unknown target_worker '{target_worker}' in {config_path}")
    worker_cfg = workers[target_worker]
    worker_port = int(campaign.get("worker_port") or worker_cfg.get("port") or 0)
    if worker_port <= 0:
        raise SystemExit(f"ERROR: target worker {target_worker} has no port")

    suite_args = validate_string_list(campaign.get("suite_args", []), "suite_args")
    env_file = str(campaign.get("env_file", "") or "").strip()
    if suite == "bench-daedalmap" and not env_file:
        default_env = benchmark_root / "docker" / "bench-daedalmap" / ".env"
        if default_env.exists():
            env_file = str(default_env)

    raw_models = campaign.get("models", [])
    if not isinstance(raw_models, list) or not raw_models:
        raise SystemExit("ERROR: campaign requires non-empty models list")

    models: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_models, start=1):
        if not isinstance(raw, dict):
            raise SystemExit(f"ERROR: models entry #{idx} must be an object")
        model = str(raw.get("model", "") or "").strip()
        if not model:
            raise SystemExit(f"ERROR: models entry #{idx} missing model")
        model_id = safe_name(str(raw.get("id", "") or model))
        entry = {
            "id": model_id,
            "model": model,
            "args": validate_string_list(raw.get("args", []), f"models[{idx}].args"),
            "enabled": bool(raw.get("enabled", True)),
            "run_name": safe_name(str(raw.get("run_name", "") or f"{run_id}_{model_id}")),
        }
        models.append(entry)

    status = load_json(status_path) if status_path.exists() else {
        "campaign": campaign_name,
        "run_id": run_id,
        "campaign_path": str(campaign_path),
        "suite": suite,
        "worker": {"name": target_worker, "port": worker_port},
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "state": "starting",
        "models": [],
    }

    existing_models: Dict[str, Dict[str, Any]] = {}
    if isinstance(status.get("models"), list):
        for existing in status["models"]:
            if isinstance(existing, dict):
                existing_models[str(existing.get("id", "")).strip()] = existing

    merged_models: List[Dict[str, Any]] = []
    for item in models:
        prior = existing_models.get(item["id"])
        if isinstance(prior, dict):
            merged = dict(item)
            merged.update(prior)
            merged_models.append(merged)
        else:
            merged_models.append(item)
    status["models"] = merged_models
    status["updated_at"] = now_iso()
    write_json(status_path, status)

    stop_on_failure = bool(campaign.get("stop_on_failure", True))
    owner = f"multi-model-suite:{campaign_name}:{run_id}"
    batch_id = f"multi_model_suite_{run_id}"
    reserved = False
    overall_success = True

    if args.dry_run:
        print(f"campaign={campaign_name}")
        print(f"suite={suite}")
        print(f"worker={target_worker}:{worker_port}")
        print(f"status_path={status_path}")
        for item in merged_models:
            if not item.get("enabled", True):
                print(f"skip {item['id']} disabled")
                continue
            cmd = build_suite_command(
                shared_root=shared_root,
                benchmark_root=benchmark_root,
                suite=suite,
                model=str(item["model"]),
                worker_port=worker_port,
                run_name=str(item["run_name"]),
                base_args=suite_args + item.get("args", []),
                env_file=env_file,
            )
            print(f"model={item['model']}")
            print("cmd=" + " ".join(cmd))
        return 0

    try:
        for item in merged_models:
            if not item.get("enabled", True):
                item["state"] = "skipped"
                continue
            if item.get("state") == "completed":
                continue

            model = str(item["model"]).strip()
            log_path = logs_dir / f"{item['id']}.log"
            item["log_path"] = str(log_path)
            item["started_at"] = now_iso()
            item["state"] = "loading"
            status["state"] = "running"
            status["current_model"] = item["id"]
            status["updated_at"] = now_iso()
            write_json(status_path, status)

            if reserved:
                release_worker(shared_root, worker_port, owner)
                reserved = False

            runtime_info = ensure_worker_runtime(
                shared_root=shared_root,
                worker_name=target_worker,
                worker_cfg=worker_cfg,
                port=worker_port,
                model=model,
                timeout_s=args.load_timeout_seconds,
                batch_id=batch_id,
            )
            item["runtime_check"] = runtime_info

            reserve_worker(shared_root, worker_port, owner)
            reserved = True

            cmd = build_suite_command(
                shared_root=shared_root,
                benchmark_root=benchmark_root,
                suite=suite,
                model=model,
                worker_port=worker_port,
                run_name=str(item["run_name"]),
                base_args=suite_args + item.get("args", []),
                env_file=env_file,
            )
            env = os.environ.copy()
            env["BENCHMARK_DISABLE_AUTO_RESERVE"] = "1"
            env["BENCHMARK_RESERVATION_SHARED_PATH"] = str(shared_root)
            env["BENCHMARK_RESERVATION_OWNER"] = owner

            item["state"] = "running"
            status["updated_at"] = now_iso()
            write_json(status_path, status)

            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n[{now_iso()}] MODEL: {model}\n")
                log_file.write(f"[{now_iso()}] CMD: {' '.join(cmd)}\n")
                proc = subprocess.run(
                    cmd,
                    text=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    check=False,
                    env=env,
                )

            item["ended_at"] = now_iso()
            item["exit_code"] = int(proc.returncode)
            if proc.returncode == 0:
                item["state"] = "completed"
            else:
                item["state"] = "failed"
                overall_success = False
                status["updated_at"] = now_iso()
                write_json(status_path, status)
                if stop_on_failure:
                    raise SystemExit(
                        f"ERROR: suite {suite} failed for model {model} with exit code {proc.returncode}. "
                        f"log={log_path}"
                    )

            if reserved:
                release_worker(shared_root, worker_port, owner)
                reserved = False
            status["updated_at"] = now_iso()
            write_json(status_path, status)

    finally:
        if reserved:
            release_worker(shared_root, worker_port, owner)

    status["ended_at"] = now_iso()
    status["state"] = "completed" if overall_success else "failed"
    status["updated_at"] = now_iso()
    status.pop("current_model", None)
    write_json(status_path, status)
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
