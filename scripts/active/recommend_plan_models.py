#!/usr/bin/env python3
"""Suggest llm_model fields for plan tasks from the job routing in model_roles.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import model_library


def parse_plan_tasks(plan_text: str) -> list[dict[str, str]]:
    sections = re.split(r"\n### ", plan_text)
    tasks: list[dict[str, str]] = []
    for sec in sections[1:]:
        lines = sec.strip().splitlines()
        if not lines:
            continue
        task_id = lines[0].strip()
        task = {"id": task_id, "task_class": "", "command": ""}
        for line in lines[1:]:
            s = line.strip()
            if s.startswith("- **task_class**:"):
                task["task_class"] = s.split(":", 1)[1].strip().lower()
            elif s.startswith("- **command**:"):
                m = re.search(r"`([^`]+)`", s)
                task["command"] = (m.group(1) if m else s.split(":", 1)[1].strip()).lower()
        tasks.append(task)
    return tasks


DEFAULT_JOB = "general_qa"


def choose_job(task: dict[str, str], roles: dict[str, Any]) -> tuple[str, str]:
    hay = f"{task.get('id', '')} {task.get('command', '')}"
    match = model_library.job_role(hay, roles)
    if match:
        return match
    default = next(j for j in roles["jobs"] if j["id"] == DEFAULT_JOB)
    return default["id"], default["role"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Recommend model settings for llm tasks in a plan.")
    ap.add_argument("--plan", required=True, help="Path to plan.md")
    ap.add_argument("--output", default="", help="Optional output JSON path")
    args = ap.parse_args()

    plan_path = Path(args.plan).expanduser().resolve()
    roles = model_library.load_roles()
    registry = model_library.load_registry()
    tasks = parse_plan_tasks(plan_path.read_text(encoding="utf-8"))

    recs: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("task_class") != "llm":
            continue
        job, role = choose_job(task, roles)
        r = model_library.resolve_role(role, roles, registry)
        recs.append(
            {
                "task_id": task.get("id"),
                "job": job,
                "role": role,
                "recommendation": {
                    "llm_model": r["model"],
                    "llm_min_tier": r["schedule"].get("tier"),
                    "llm_placement": r["schedule"].get("placement"),
                },
                "evidence": r.get("evidence", ""),
            }
        )

    payload = {
        "plan": str(plan_path),
        "roles": str(model_library.ROLES_PATH),
        "recommendations": recs
    }

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote recommendations: {out_path}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
