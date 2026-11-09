#!/usr/bin/env python3
"""Show loading readiness and configured context limits without using the rig."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "model_registry.json"
STATES = {"in_progress", "ready_for_benchmark", "blocked"}
REQUIRED = ("state", "runtime", "recipe", "limits")
CONTEXT_FIELDS = ("default_context", "context_limit", "context_basis")


def problems(model_id: str, entry: dict) -> list[str]:
    stage = entry.get("loading_stage")
    if not isinstance(stage, dict):
        return [f"{model_id}: loading_stage must be an object"]
    errors = []
    for field in REQUIRED:
        value = stage.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{model_id}: {field} must be nonempty text")
    if stage.get("state") not in STATES:
        errors.append(f"{model_id}: state must be one of {', '.join(sorted(STATES))}")
    for field in CONTEXT_FIELDS:
        value = stage.get(field)
        if value is None and stage.get("state") != "ready_for_benchmark":
            continue
        if field in ("default_context", "context_limit"):
            if type(value) is not int or value <= 0:
                errors.append(f"{model_id}: {field} must be a positive integer when recorded")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"{model_id}: {field} must be nonempty text when recorded")
    default = stage.get("default_context")
    limit = stage.get("context_limit")
    if type(default) is int and type(limit) is int and default > limit:
        errors.append(f"{model_id}: default_context exceeds context_limit")
    profile = entry.get("profiles", {}).get("default", {})
    registered_default = profile.get("runtime", {}).get("ctx_size")
    registered_max = profile.get("context_bounds", {}).get("max")
    if type(default) is int and type(registered_default) is int and default != registered_default:
        errors.append(f"{model_id}: default_context differs from the default profile")
    if type(limit) is int and type(registered_max) is int and limit > registered_max:
        errors.append(f"{model_id}: context_limit exceeds the registered context bound")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_id", nargs="?", help="show or check one model")
    parser.add_argument("--check-ready", action="store_true", help="fail unless the selected model is ready")
    args = parser.parse_args()
    if args.check_ready and not args.model_id:
        parser.error("--check-ready requires model_id")

    models = json.loads(REGISTRY.read_text(encoding="utf-8"))["models"]
    if args.model_id and args.model_id not in models:
        parser.error(f"unknown model: {args.model_id}")
    selected = {args.model_id: models[args.model_id]} if args.model_id else models
    counts: dict[str, int] = {}
    errors = []
    for model_id, entry in selected.items():
        stage = entry.get("loading_stage")
        state = stage.get("state", "invalid") if isinstance(stage, dict) else "legacy/untracked"
        counts[state] = counts.get(state, 0) + 1
        if args.model_id or stage is not None:
            print(f"{model_id}: {state} | deployment={entry.get('status')} | "
                  f"runtime={stage.get('runtime', '?') if isinstance(stage, dict) else '?'} | "
                  f"context={stage.get('default_context', '?') if isinstance(stage, dict) else '?'}"
                  f"/{stage.get('context_limit', '?') if isinstance(stage, dict) else '?'}")
        if stage is not None:
            errors.extend(problems(model_id, entry))
        if args.check_ready and state != "ready_for_benchmark":
            errors.append(f"{model_id}: loading stage is {state}, not ready_for_benchmark")
    print("Summary: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    for error in errors:
        print(f"problem: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
