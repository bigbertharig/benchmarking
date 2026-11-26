#!/usr/bin/env python3
"""Compile a model-and-suite request into the existing campaign-v1 contract.

This tool does no placement or model loading. The campaign runner and rig admission
decide when and where each model can run.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GATEWAY_FIT_FIELDS = ("use", "profile", "ctx_size", "ctx_min", "context_mode",
                      "margin_mb", "batch_size", "engine", "placement_policy")


def _id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def compile_request(request: dict, registry: dict, contracts: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    if set(request) - {"name", "models", "tests", "run_class"}:
        raise ValueError("unknown request fields: " + ", ".join(sorted(set(request) - {"name", "models", "tests", "run_class"})))
    name = request.get("name")
    if not isinstance(name, str) or not _id(name):
        raise ValueError("name must be nonempty text")
    name = _id(name)
    models = request.get("models")
    tests = request.get("tests")
    if not isinstance(models, list) or not models or any(not isinstance(m, str) or not m for m in models):
        raise ValueError("models must be a nonempty list of model IDs")
    if len(models) != len(set(models)):
        raise ValueError("models contains a duplicate ID")
    if not isinstance(tests, list) or not tests:
        raise ValueError("tests must be a nonempty list of suite names or suite objects")
    run_class = request.get("run_class", "smoke")
    if run_class not in {"smoke", "provisional", "validated", "full"}:
        raise ValueError("invalid run_class")
    known_models = registry.get("models", {})
    unknown = [model for model in models if model not in known_models]
    if unknown:
        raise ValueError("unknown registry model(s): " + ", ".join(unknown))
    for model in models:
        stage = known_models[model].get("loading_stage")
        if not isinstance(stage, dict):
            raise ValueError(f"{model}: loading_stage is required before a campaign request")
        state = stage.get("state")
        if state not in {"in_progress", "ready_for_benchmark", "blocked"}:
            raise ValueError(f"{model}: invalid loading_stage state")
        if state == "blocked":
            raise ValueError(f"{model}: loading_stage is blocked")
        if run_class != "smoke" and state != "ready_for_benchmark":
            raise ValueError(f"{model}: onboarding is not ready_for_benchmark")
    suite_specs = contracts.get("suites", {})
    normalized = []
    for index, item in enumerate(tests):
        test = {"suite": item} if isinstance(item, str) else item
        if not isinstance(test, dict) or set(test) - {"suite", "tasks", "limit"}:
            raise ValueError(f"test {index} must contain only suite, tasks, and limit")
        suite = test.get("suite")
        if suite not in suite_specs:
            raise ValueError(f"test {index}: unknown suite {suite!r}")
        spec = suite_specs[suite]
        tasks = test.get("tasks")
        if tasks is not None and (not isinstance(tasks, list) or not tasks or
                                  any(not isinstance(task, str) or not task for task in tasks)):
            raise ValueError(f"test {index}: tasks must be a nonempty list of names")
        if tasks is not None and not spec.get("task_selector"):
            raise ValueError(f"test {index}: {suite} has no task selector")
        limit = test.get("limit")
        if limit is not None and (type(limit) is not int or limit <= 0 or not spec.get("limit_supported")):
            raise ValueError(f"test {index}: {suite} does not support this limit")
        normalized.append({"suite": suite, "tasks": tasks, "limit": limit})
    blocks = []
    for model_index, model in enumerate(models):
        group = f"model_{model_index + 1}"
        for test_index, test in enumerate(normalized):
            block = {"id": f"m{model_index + 1}_t{test_index + 1}_{_id(test['suite'])}",
                     "model": model, "suite": test["suite"]}
            if len(normalized) > 1:
                block["runtime_group"] = group
            if test["tasks"] is not None:
                block["suite_args"] = [suite_specs[test["suite"]]["task_selector"], ",".join(test["tasks"])]
            if test["limit"] is not None:
                block["limit"] = test["limit"]
            blocks.append(block)
    return {"name": name, "defaults": {"run_class": run_class}, "blocks": blocks}


def compile_gateway_plan(campaign: dict) -> dict:
    """Project campaign-v1 onto Gateway's read-only scheduling contract.

    Benchmarking keeps suite arguments and scoring details. Gateway receives only
    dependencies, runtime reuse, fit intent, and optional duration evidence.
    """
    blocks = []
    for raw in campaign.get("blocks") or []:
        block = {key: raw[key] for key in
                 ("id", "model", "suite", "depends_on", "runtime_group", "estimated_duration_s")
                 if key in raw}
        for key in GATEWAY_FIT_FIELDS:
            if key not in raw:
                continue
            gateway_key = "ctx" if key == "ctx_size" else key
            block[gateway_key] = raw[key]
        blocks.append(block)
    return {"schema": "benchmark-campaign-plan/1", "name": campaign["name"], "blocks": blocks,
            "planning_mode": "after_current_work"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gateway-plan-output", type=Path,
                        help="also write the read-only Gateway campaign planning projection")
    parser.add_argument("--registry", type=Path, default=ROOT / "model_registry.json")
    parser.add_argument("--contracts", type=Path, default=ROOT / "docker" / "suite_contracts.json")
    args = parser.parse_args()
    if args.output.resolve() == args.request.resolve():
        parser.error("output must differ from the request")
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        contracts = json.loads(args.contracts.read_text(encoding="utf-8"))
        campaign = compile_request(request, registry, contracts)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(campaign, indent=2) + "\n", encoding="utf-8")
    if args.gateway_plan_output:
        if args.gateway_plan_output.resolve() in (args.request.resolve(), args.output.resolve()):
            parser.error("gateway plan output must differ from request and campaign output")
        args.gateway_plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.gateway_plan_output.write_text(
            json.dumps(compile_gateway_plan(campaign), indent=2) + "\n", encoding="utf-8")
    print(f"{len(campaign['blocks'])} blocks written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
