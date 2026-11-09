#!/usr/bin/env python3
"""Show loading-stage progress and verify recorded evidence without using the rig."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "model_registry.json"
STATES = {"in_progress", "ready_for_benchmark", "blocked"}
REQUIRED = ("state", "runtime", "recipe", "evidence", "limits", "next_step")


def problems(model_id: str, stage: object) -> list[str]:
    if not isinstance(stage, dict):
        return [f"{model_id}: loading_stage must be an object"]
    errors = []
    for field in REQUIRED:
        value = stage.get(field)
        if field == "evidence":
            if not isinstance(value, list) or not all(isinstance(p, str) and p for p in value):
                errors.append(f"{model_id}: evidence must be a list of paths")
            elif stage.get("state") == "ready_for_benchmark" and not value:
                errors.append(f"{model_id}: ready_for_benchmark requires at least one receipt")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"{model_id}: {field} must be nonempty text")
    if stage.get("state") not in STATES:
        errors.append(f"{model_id}: state must be one of {', '.join(sorted(STATES))}")
    for raw in stage.get("evidence", []) if isinstance(stage.get("evidence"), list) else []:
        if not isinstance(raw, str):
            continue
        path = (ROOT / raw).resolve()
        if not path.is_relative_to(ROOT):
            errors.append(f"{model_id}: evidence path leaves the repository: {raw}")
        elif not path.is_file():
            errors.append(f"{model_id}: missing evidence: {raw}")
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
                  f"runtime={stage.get('runtime', '?') if isinstance(stage, dict) else '?'}")
        if stage is not None:
            errors.extend(problems(model_id, stage))
        if args.check_ready and state != "ready_for_benchmark":
            errors.append(f"{model_id}: loading stage is {state}, not ready_for_benchmark")
    print("Summary: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    for error in errors:
        print(f"problem: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
