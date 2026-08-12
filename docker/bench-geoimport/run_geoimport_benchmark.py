#!/usr/bin/env python3
"""Run County Map geometry/admin-spine import benchmark cases."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


METHODOLOGY = ("bench-geoimport/capability", "2.0.0", "geoimport-capability-v2")
TASKS = ("classification", "prep_plan", "prep_handoff")
DEFAULT_INFERENCE = {
    "temperature": 0.1,
    "top_p": 1.0,
    "top_k": None,
    "repeat_penalty": None,
    "max_tokens": 2048,
    "stop_sequences": [],
    "thinking": None,
    "json_grammar": False,
}
INFERENCE_KEYS = set(DEFAULT_INFERENCE)


def merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_model_profile(models: dict[str, Any], model: str, seen: set[str] | None = None) -> tuple[dict[str, Any], str]:
    if model not in models:
        return {}, "suite-default"
    seen = set(seen or ())
    if model in seen:
        raise ValueError(f"model tuning profile alias cycle at {model}")
    seen.add(model)
    entry = models[model]
    if not isinstance(entry, dict):
        raise ValueError(f"model tuning profile must be an object: {model}")
    alias = entry.get("_alias_of")
    local = {key: value for key, value in entry.items() if key != "_alias_of"}
    if not alias:
        return local, model
    base, source = resolve_model_profile(models, str(alias), seen)
    return merge_dicts(base, local), f"{model}->{source}"


def load_run_profile(path: Path, model: str, override_json: str, disabled: bool) -> tuple[dict[str, Any], str, str]:
    profile: dict[str, Any] = {}
    source = "suite-default"
    if not disabled:
        if not path.exists():
            raise FileNotFoundError(f"model tuning profiles not found: {path}")
        root = json.loads(path.read_text(encoding="utf-8"))
        models = root.get("models", {})
        if not isinstance(models, dict):
            raise ValueError("model tuning profiles must contain an object named models")
        profile, source = resolve_model_profile(models, model)

    inference = merge_dicts(DEFAULT_INFERENCE, profile.get("inference", {}))
    overrides = json.loads(override_json)
    if not isinstance(overrides, dict):
        raise ValueError("--inference-config-json must decode to an object")
    unknown = sorted((set(inference) | set(overrides)) - INFERENCE_KEYS)
    if unknown:
        raise ValueError(f"unsupported inference settings: {','.join(unknown)}")
    inference = merge_dicts(inference, overrides)
    if not isinstance(inference["max_tokens"], int) or inference["max_tokens"] <= 0:
        raise ValueError("max_tokens must be a positive integer")
    if not isinstance(inference["stop_sequences"], list):
        raise ValueError("stop_sequences must be a list")
    system_prefix = str(profile.get("system_prompt", "")).strip()
    return inference, system_prefix, source


def chat(
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    inference: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": inference["temperature"],
        "stream": False,
        "max_tokens": inference["max_tokens"],
    }
    for key in ("top_p", "top_k", "repeat_penalty"):
        if inference.get(key) is not None:
            payload[key] = inference[key]
    if inference["stop_sequences"]:
        payload["stop"] = inference["stop_sequences"]
    if inference.get("thinking") is not None:
        payload["chat_template_kwargs"] = {"enable_thinking": bool(inference["thinking"])}
    if inference.get("json_grammar"):
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read())
    message = decoded["choices"][0]["message"]
    text = str(message.get("content") or message.get("reasoning_content") or "").strip()
    return {"content": strip_fences(text), "usage": decoded.get("usage", {}), "elapsed": time.monotonic() - started}


def strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


def parse_json(text: str) -> tuple[dict[str, Any], bool]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                payload, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            return (payload, True) if isinstance(payload, dict) else ({}, False)
        return {}, False
    return (payload, True) if isinstance(payload, dict) else ({}, False)


def lower_blob(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True).lower()
    return re.sub(r"[_-]+", " ", raw)


def value_hits(payload: dict[str, Any], values: list[str]) -> int:
    blob = lower_blob(payload)
    return sum(1 for value in values if re.sub(r"[_-]+", " ", str(value).lower()) in blob)


def concept_group_hits(payload: dict[str, Any], groups: list[list[str]]) -> list[dict[str, Any]]:
    blob = lower_blob(payload)
    results = []
    for group in groups:
        alternatives = [re.sub(r"[_-]+", " ", str(value).lower()) for value in group]
        matched = [value for value in alternatives if value in blob]
        results.append({"alternatives": group, "matched": matched, "passed": bool(matched)})
    return results


def prohibited_hits(payload: dict[str, Any], values: list[str]) -> list[str]:
    blob = lower_blob(payload)
    return [value for value in values if re.sub(r"[_-]+", " ", str(value).lower()) in blob]


def prohibited_claim_hits(payload: dict[str, Any], values: list[str]) -> list[str]:
    claim_fields = ("claim", "target_claim", "classification", "task_type")
    claims = " ".join(str(payload.get(field, "")) for field in claim_fields).lower()
    return [value for value in values if str(value).lower() in claims]


def score_case(case: dict[str, Any], raw_text: str) -> dict[str, Any]:
    payload, valid_json = parse_json(raw_text)
    expected = case.get("expected", {})
    checks = 1
    passes = 1 if valid_json else 0
    details: dict[str, Any] = {"valid_json": valid_json}
    if not valid_json:
        details["score"] = 0.0
        details["payload"] = raw_text[:500]
        return details

    required_keys = expected.get("required_keys", [])
    if required_keys:
        checks += len(required_keys)
        missing = [key for key in required_keys if key not in payload]
        passes += len(required_keys) - len(missing)
        details["missing_required_keys"] = missing

    for field, allowed_key in (
        ("task_type", "task_type_values"),
        ("target_claim", "target_claim_values"),
        ("claim", "claim_values"),
        ("classification", "classification"),
    ):
        allowed = expected.get(allowed_key, [])
        if allowed:
            checks += 1
            field_value = str(payload.get(field, "")).strip().lower()
            matched = field_value in {str(value).strip().lower() for value in allowed}
            passes += int(matched)
            details[f"{field}_matched"] = matched

    must_include = expected.get("must_include", [])
    if must_include:
        hits = value_hits(payload, must_include)
        checks += len(must_include)
        passes += hits
        details["must_include_hits"] = hits
        details["must_include_total"] = len(must_include)

    concept_groups = expected.get("concept_groups", [])
    if concept_groups:
        group_results = concept_group_hits(payload, concept_groups)
        checks += len(group_results)
        passes += sum(1 for result in group_results if result["passed"])
        details["concept_groups"] = group_results
        details["concept_groups_passed"] = sum(1 for result in group_results if result["passed"])
        details["concept_groups_total"] = len(group_results)

    must_not_include = expected.get("must_not_include", [])
    if must_not_include:
        bad = prohibited_hits(payload, must_not_include)
        checks += len(must_not_include)
        passes += len(must_not_include) - len(bad)
        details["prohibited_hits"] = bad

    must_not_claim = expected.get("must_not_claim", [])
    if must_not_claim:
        bad_claims = prohibited_claim_hits(payload, must_not_claim)
        checks += len(must_not_claim)
        passes += len(must_not_claim) - len(bad_claims)
        details["prohibited_claim_hits"] = bad_claims

    details["score"] = round(passes / checks if checks else 0.0, 4)
    details["payload"] = payload
    return details


def classify_thresholds(cases_root: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    thresholds = cases_root.get("thresholds", {})
    pass_score = float(thresholds.get("PASS", 0.9))
    partial_score = float(thresholds.get("PARTIAL", 0.6))
    scored_rows = [row for row in rows if row.get("status") == "success" and row.get("score") is not None]
    if not scored_rows:
        return False, ["no scored rows"]
    average = sum(float(row["score"]) for row in scored_rows) / len(scored_rows)
    failures = []
    if average < pass_score:
        failures.append(f"average score {average:.4f} below PASS threshold {pass_score:.4f}")
    low_rows = [row for row in scored_rows if float(row["score"]) < partial_score]
    for row in low_rows:
        failures.append(f"{row['test_id']} score {float(row['score']):.4f} below PARTIAL threshold {partial_score:.4f}")
    return not failures, failures


def update_status(path: Path, task: str, state: str, exit_code: int | None = None) -> None:
    status = json.loads(path.read_text(encoding="utf-8"))
    entry = status["tasks"][task]
    if state == "running":
        entry["started_at"] = datetime.now().isoformat()
    if state in {"completed", "failed"}:
        entry["ended_at"] = datetime.now().isoformat()
    entry["state"] = state
    entry["exit_code"] = exit_code
    status["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")


def record_result(args: argparse.Namespace, test_id: str, score: float, metric: str, notes: str) -> None:
    if args.no_record:
        return
    recorder = Path(args.scripts_dir) / "scripts" / "active" / "record_benchmark_result.py"
    if not recorder.exists():
        raise RuntimeError(f"recorder not found: {recorder}")
    subprocess.run(
        [
            sys.executable,
            str(recorder),
            "--model",
            args.model,
            "--test-id",
            test_id,
            "--score",
            f"{score:.4f}",
            "--raw-harness-score",
            f"{score:.4f}",
            "--metric",
            metric,
            "--run-class",
            args.run_class,
            "--sample-count",
            "1",
            "--harness",
            "bench-geoimport",
            "--suite",
            args.run_name,
            "--methodology-id",
            METHODOLOGY[0],
            "--methodology-version",
            METHODOLOGY[1],
            "--comparison-group",
            METHODOLOGY[2],
            "--config-id",
            args.config_id,
            "--config-json",
            args.config_json,
            "--run-at",
            datetime.now().isoformat(),
            "--notes",
            notes,
            "--records",
            args.records,
            "--reference-output",
            args.reference_output,
            "--scoreboard-output",
            args.scoreboard_output,
        ],
        check=True,
    )


def prompt_for(task: str, case: dict[str, Any]) -> str:
    expected = case.get("expected", {})
    task_types = ", ".join(expected.get("task_type_values", []))
    if task == "classification":
        classifications = ", ".join(expected.get("classification", []))
        claims = ", ".join(expected.get("target_claim_values", []))
        return (
            "Classify this geometry assignment. Return JSON with keys: "
            "classification, task_type, target_claim, rationale, next_actions. "
            f"Use exactly one classification from [{classifications}], one task_type from [{task_types}], "
            f"and one target_claim from [{claims}].\n\n"
            f"Context:\n{case['prompt_context']}"
        )
    if task == "prep_plan":
        claims = ", ".join(expected.get("target_claim_values", []))
        return (
            "Create a compact local-brain preparation plan. Return JSON with keys: "
            "task_type, target_claim, stages, outputs, local_checks, handoff, blocked_items. "
            f"Use exactly one task_type from [{task_types}] and one target_claim from [{claims}].\n\n"
            f"Context:\n{case['prompt_context']}"
        )
    claims = ", ".join(expected.get("claim_values", []))
    return (
        "Assess local preparation handoff readiness. Return JSON with keys: "
        "claim, prep_state, rationale, missing_or_failed, next_actions. "
        f"Use exactly one claim from [{claims}].\n\n"
        f"Context:\n{case['prompt_context']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run geometry/admin-spine import benchmark cases.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime-base", required=True)
    parser.add_argument("--tasks", default=",".join(TASKS))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--run-class", choices=("smoke", "provisional", "validated", "full"), default="provisional")
    parser.add_argument("--results-dir", default="/results")
    parser.add_argument("--scripts-dir", default="/benchmark-scripts")
    parser.add_argument("--cases-file", default="/opt/bench/geoimport_cases.json")
    parser.add_argument("--system-prompt-file", default="/opt/bench/geoimport_system_prompt.md")
    parser.add_argument("--tuning-profiles", default=None)
    parser.add_argument("--no-model-profile", action="store_true")
    parser.add_argument("--inference-config-json", default="{}")
    parser.add_argument("--config-id", default="")
    parser.add_argument("--config-json", default="{}")
    parser.add_argument("--records", default="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl")
    parser.add_argument("--reference-output", default="/mnt/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md")
    parser.add_argument("--scoreboard-output", default="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        parser.error("--run-name may contain only letters, digits, dot, underscore, and hyphen")
    requested = [task for task in args.tasks.split(",") if task]
    unknown = [task for task in requested if task not in TASKS]
    if unknown:
        parser.error(f"unknown tasks: {','.join(unknown)}")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")

    cases_root = json.loads(Path(args.cases_file).read_text(encoding="utf-8"))
    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    tuning_profiles = Path(args.tuning_profiles) if args.tuning_profiles else Path(args.scripts_dir) / "model_tuning_profiles.json"
    inference, system_prefix, profile_source = load_run_profile(
        tuning_profiles, args.model, args.inference_config_json, args.no_model_profile
    )
    if system_prefix:
        system_prompt = f"{system_prefix}\n\n{system_prompt}"
    operator_config = json.loads(args.config_json)
    if not isinstance(operator_config, dict):
        parser.error("--config-json must decode to an object")
    resolved_config = {
        "operator": operator_config,
        "model_profile": profile_source,
        "tuning_profiles": str(tuning_profiles) if not args.no_model_profile else "disabled",
        "inference": inference,
    }
    args.config_id = args.config_id or f"geoimport-v2:{profile_source}"
    args.config_json = json.dumps(resolved_config, sort_keys=True)
    model_safe = re.sub(r"[^A-Za-z0-9_.-]", "_", args.model)
    run_dir = Path(args.results_dir) / f"bench-geoimport_{model_safe}_{args.run_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    status_file = run_dir / "status.json"
    stage_file = run_dir / "stage_updates.jsonl"
    final_file = run_dir / "final_summary.json"

    if not status_file.exists():
        status = {
            "run_start": datetime.now().isoformat(),
            "model": args.model,
            "runtime": args.runtime_base,
            "tasks_requested": requested,
            "limit": args.limit or "all",
            "config_id": args.config_id,
            "config": resolved_config,
            "tasks": {task: {"state": "pending", "exit_code": None, "started_at": None, "ended_at": None} for task in requested},
            "updated_at": datetime.now().isoformat(),
        }
        status_file.write_text(json.dumps(status, indent=2), encoding="utf-8")

    results: list[dict[str, Any]] = []
    failures = 0
    for task in requested:
        status = json.loads(status_file.read_text(encoding="utf-8"))
        if status["tasks"].get(task, {}).get("state") == "completed":
            print(f"Skipping completed task: {task}")
            continue
        print(f"--- Running task: {task} ---")
        update_status(status_file, task, "running")
        task_dir = run_dir / task
        task_dir.mkdir(exist_ok=True)
        cases = cases_root["tasks"][task]["cases"]
        if args.limit is not None:
            cases = cases[: args.limit]
        task_failed = False
        for index, case in enumerate(cases, start=1):
            print(f"Case {index}/{len(cases)}: {case['case_id']} {case['name']}")
            try:
                response = chat(
                    args.runtime_base,
                    args.model,
                    system_prompt,
                    prompt_for(task, case),
                    args.timeout,
                    inference,
                )
                score = score_case(case, response["content"])
                score_path = task_dir / f"{case['case_id']}_score.json"
                output_path = task_dir / f"{case['case_id']}_output.json"
                score_path.write_text(json.dumps(score, indent=2), encoding="utf-8")
                output_path.write_text(response["content"], encoding="utf-8")
                row = {
                    "test_id": case["test_id"],
                    "status": "success",
                    "score": score["score"],
                    "metric": task,
                    "case_id": case["case_id"],
                    "at": datetime.now().isoformat(),
                }
                stage_file.open("a", encoding="utf-8").write(json.dumps(row) + "\n")
                record_result(args, case["test_id"], float(score["score"]), task, "")
                print(f"  score={score['score']:.2%}")
            except Exception as exc:  # noqa: BLE001
                task_failed = True
                failures += 1
                row = {
                    "test_id": case["test_id"],
                    "status": "failure",
                    "score": None,
                    "metric": task,
                    "case_id": case["case_id"],
                    "notes": str(exc),
                    "at": datetime.now().isoformat(),
                }
                stage_file.open("a", encoding="utf-8").write(json.dumps(row) + "\n")
                print(f"  ERROR: {exc}")
        update_status(status_file, task, "failed" if task_failed else "completed", 1 if task_failed else 0)

    if stage_file.exists():
        results = [json.loads(line) for line in stage_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    successes = [row for row in results if row.get("status") == "success"]
    failed_rows = [row for row in results if row.get("status") == "failure"]
    average = sum(float(row["score"]) for row in successes) / len(successes) if successes else 0.0
    summary = {
        "model": args.model,
        "config_id": args.config_id,
        "config": resolved_config,
        "tasks_completed": sum(1 for task in json.loads(status_file.read_text(encoding="utf-8"))["tasks"].values() if task["state"] == "completed"),
        "tasks_total": len(requested),
        "total_cases": len(results),
        "successful_cases": len(successes),
        "failed_cases": len(failed_rows),
        "average_score": round(average, 4),
        "results": results,
        "completed_at": datetime.now().isoformat(),
    }
    thresholds_passed, threshold_failures = classify_thresholds(cases_root, results)
    summary["thresholds_passed"] = thresholds_passed
    summary["threshold_failures"] = threshold_failures
    final_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if failures or not thresholds_passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
