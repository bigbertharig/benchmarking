#!/usr/bin/env python3
"""Run local custom benchmark tasks against a llama-compatible chat endpoint."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from benchmark_records import RUN_CLASSES


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def default_output_dir() -> str:
    media_path = Path("/media/bryan/shared/logs/benchmarks")
    if media_path.exists():
        return str(media_path)
    return "/mnt/shared/logs/benchmarks"


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for item in data.get("tests", []):
        test_id = str(item.get("id", "")).strip()
        if test_id:
            out[test_id] = item
    return out


def load_cases(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for item in data.get("tests", []):
        test_id = str(item.get("id", "")).strip()
        if test_id:
            out[test_id] = item
    return out


def load_prompt_profiles(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Prompt profiles not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Prompt profiles must be a JSON object: {path}")
    return data


def load_tuning_profiles(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Tuning profiles not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Tuning profiles must be a JSON object: {path}")
    return data


def _normalize_model_token(value: str) -> str:
    raw = value.strip().lower()
    if raw.endswith(".gguf"):
        raw = raw[:-5]
    return re.sub(r"[^a-z0-9]+", "", raw)


def _lookup_model_entry_by_id(models_obj: Any, model: str) -> dict[str, Any] | None:
    model_l = model.strip().lower()
    model_n = _normalize_model_token(model)

    if isinstance(models_obj, list):
        exact_norm_matches: list[dict[str, Any]] = []
        fuzzy_matches: list[dict[str, Any]] = []
        for item in models_obj:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id", "")).strip()
            if not model_id:
                continue
            if model_id.lower() == model_l:
                return item
            id_n = _normalize_model_token(model_id)
            if id_n == model_n:
                exact_norm_matches.append(item)
            elif model_n and id_n and (model_n in id_n or id_n in model_n):
                fuzzy_matches.append(item)
        if len(exact_norm_matches) == 1:
            return exact_norm_matches[0]
        if len(exact_norm_matches) > 1:
            return None
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0]
        return None

    if isinstance(models_obj, dict):
        exact_norm_matches: list[dict[str, Any]] = []
        fuzzy_matches: list[dict[str, Any]] = []
        for key, value in models_obj.items():
            if not isinstance(value, dict):
                continue
            key_s = str(key).strip()
            if key_s.lower() == model_l:
                return value
            key_n = _normalize_model_token(key_s)
            if key_n == model_n:
                exact_norm_matches.append(value)
            elif model_n and key_n and (model_n in key_n or key_n in model_n):
                fuzzy_matches.append(value)
        if len(exact_norm_matches) == 1:
            return exact_norm_matches[0]
        if len(exact_norm_matches) > 1:
            return None
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0]

    return None


def resolve_system_prompt(
    profiles: dict[str, Any],
    tuning_profiles: dict[str, Any],
    model: str,
    test_id: str,
) -> tuple[str, str]:
    default_prompt = str(profiles.get("default_system_prompt", "")).strip()
    item = _lookup_model_entry_by_id(profiles.get("models", []), model)
    if item:
        model_id = str(item.get("id", model)).strip()
        overrides = item.get("test_overrides", {})
        if isinstance(overrides, dict):
            override_prompt = str(overrides.get(test_id, "")).strip()
            if override_prompt:
                return override_prompt, f"model:{model_id}:test:{test_id}"
        model_prompt = str(item.get("system_prompt", "")).strip()
        if model_prompt:
            return model_prompt, f"model:{model_id}"

    tuning_item = _lookup_model_entry_by_id(tuning_profiles.get("models", {}), model)
    if tuning_item:
        universal_prompt = str(tuning_item.get("system_prompt", "")).strip()
        if universal_prompt:
            return universal_prompt, f"universal:{model}"

    return default_prompt, "default"


def has_model_prompt_source(
    profiles: dict[str, Any],
    tuning_profiles: dict[str, Any],
    model: str,
) -> bool:
    item = _lookup_model_entry_by_id(profiles.get("models", []), model)
    if item:
        model_prompt = str(item.get("system_prompt", "")).strip()
        if model_prompt:
            return True
    tuning_item = _lookup_model_entry_by_id(tuning_profiles.get("models", {}), model)
    if tuning_item:
        universal_prompt = str(tuning_item.get("system_prompt", "")).strip()
        if universal_prompt:
            return True
    return False


def normalize_inference_config(value: str) -> dict[str, Any]:
    try:
        supplied = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--inference-config-json must be valid JSON: {exc}") from exc
    if not isinstance(supplied, dict):
        raise SystemExit("--inference-config-json must decode to an object")
    allowed = {
        "temperature", "top_k", "top_p", "repeat_penalty", "thinking",
        "json_grammar", "system_prompt", "stop_sequences", "max_tokens",
    }
    unknown = set(supplied) - allowed
    if unknown:
        raise SystemExit(f"Unknown inference settings: {', '.join(sorted(unknown))}")
    config: dict[str, Any] = {
        "temperature": 0,
        "top_k": None,
        "top_p": None,
        "repeat_penalty": None,
        "thinking": None,
        "json_grammar": False,
        "system_prompt": None,
        "stop_sequences": [],
        "max_tokens": 512,
    }
    config.update(supplied)
    for key in ("temperature", "top_p", "repeat_penalty"):
        item = config[key]
        if item is not None and (isinstance(item, bool) or not isinstance(item, (int, float))):
            raise SystemExit(f"Inference setting {key} must be numeric or null")
    if not 0 <= config["temperature"] <= 2:
        raise SystemExit("Inference setting temperature must be between 0 and 2")
    if config["top_p"] is not None and not 0 < config["top_p"] <= 1:
        raise SystemExit("Inference setting top_p must be greater than 0 and at most 1")
    if config["repeat_penalty"] is not None and config["repeat_penalty"] <= 0:
        raise SystemExit("Inference setting repeat_penalty must be positive")
    for key in ("top_k", "max_tokens"):
        item = config[key]
        if item is not None and (isinstance(item, bool) or not isinstance(item, int) or item < 0):
            raise SystemExit(f"Inference setting {key} must be a non-negative integer or null")
    if config["max_tokens"] == 0:
        raise SystemExit("Inference setting max_tokens must be positive")
    for key in ("thinking", "json_grammar"):
        item = config[key]
        if item is not None and not isinstance(item, bool):
            raise SystemExit(f"Inference setting {key} must be boolean or null")
    if config["system_prompt"] is not None and not isinstance(config["system_prompt"], str):
        raise SystemExit("Inference setting system_prompt must be a string or null")
    stops = config["stop_sequences"]
    if not isinstance(stops, list) or any(not isinstance(item, str) or not item for item in stops):
        raise SystemExit("Inference setting stop_sequences must be an array of non-empty strings")
    return config


def build_chat_payload(
    model: str,
    prompt: str,
    system_prompt: str,
    inference_config: dict[str, Any],
) -> dict[str, Any]:
    configured_prompt = inference_config.get("system_prompt")
    if configured_prompt is not None:
        system_prompt = str(configured_prompt)
    messages: list[dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {
        "messages": messages,
        "max_tokens": inference_config["max_tokens"],
        "temperature": inference_config["temperature"],
        "stream": False,
    }
    for key in ("top_k", "top_p", "repeat_penalty"):
        if inference_config.get(key) is not None:
            payload[key] = inference_config[key]
    if inference_config.get("thinking") is not None:
        payload["chat_template_kwargs"] = {"enable_thinking": inference_config["thinking"]}
    if inference_config.get("json_grammar"):
        payload["response_format"] = {"type": "json_object"}
    if inference_config.get("stop_sequences"):
        payload["stop"] = inference_config["stop_sequences"]
    if model:
        payload["model"] = model
    return payload


def call_chat_completion(
    base_url: str,
    model: str,
    prompt: str,
    timeout: int,
    system_prompt: str,
    inference_config: dict[str, Any],
) -> tuple[str, str]:
    payload = build_chat_payload(model, prompt, system_prompt, inference_config)
    response = requests.post(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("chat completion response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("chat completion choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("chat completion choice missing message")
    content = str(message.get("content", "")).strip()
    if content:
        return content, "content"
    reasoning = str(message.get("reasoning_content", "")).strip()
    if reasoning:
        return reasoning, "reasoning_content"
    return "", "empty"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def model_safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())


def parse_strict_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```") or stripped.endswith("```"):
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def grade_json_schema(case: dict[str, Any], response: str) -> tuple[bool, str]:
    parsed = parse_strict_json(response)
    if parsed is None:
        return False, "response is not strict raw JSON object"
    schema = case.get("schema", {})
    for key, expected_type in schema.items():
        if key not in parsed:
            return False, f"missing key {key}"
        value = parsed[key]
        if expected_type == "string" and not isinstance(value, str):
            return False, f"key {key} is not string"
        if expected_type == "integer" and not isinstance(value, int):
            return False, f"key {key} is not integer"
        if expected_type == "boolean" and not isinstance(value, bool):
            return False, f"key {key} is not boolean"
    expected = case.get("expected", {})
    action_contains = str(expected.get("action_contains", "")).strip().lower()
    if action_contains and action_contains not in str(parsed.get("action", "")).lower():
        return False, "action content mismatch"
    if "priority" in expected and parsed.get("priority") != expected.get("priority"):
        return False, "priority mismatch"
    if "safe" in expected and parsed.get("safe") is not expected.get("safe"):
        return False, "safe flag mismatch"
    return True, "strict schema case passed"


def grade_keyword_case(case: dict[str, Any], response: str) -> tuple[bool, str]:
    normalized = normalize_text(response)
    required = [str(x).strip().lower() for x in case.get("required_keywords", []) if str(x).strip()]
    required_any = [
        [str(option).strip().lower() for option in group if str(option).strip()]
        for group in case.get("required_any_keywords", [])
        if isinstance(group, list)
    ]
    forbidden = [str(x).strip().lower() for x in case.get("forbidden_keywords", []) if str(x).strip()]
    missing = [word for word in required if word not in normalized]
    if missing:
        return False, f"missing required keywords: {', '.join(missing)}"
    missing_any: list[str] = []
    for group in required_any:
        if group and not any(option in normalized for option in group):
            missing_any.append(" / ".join(group))
    if missing_any:
        return False, f"missing required keyword groups: {', '.join(missing_any)}"
    triggered = [word for word in forbidden if word in normalized]
    if triggered:
        return False, f"forbidden keywords present: {', '.join(triggered)}"
    return True, "keyword case passed"


def grade_case(test_id: str, case: dict[str, Any], response: str) -> tuple[bool, str]:
    if test_id == "custom_json_schema_strict":
        return grade_json_schema(case, response)
    return grade_keyword_case(case, response)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a local custom benchmark task")
    ap.add_argument("--id", required=True, help="Custom test id from benchmark catalog")
    ap.add_argument("--model", required=True, help="Model id to record for this run")
    ap.add_argument("--base-url", required=True, help="Runtime base URL like http://localhost:11435")
    ap.add_argument("--catalog", default="benchmark_catalog.json")
    ap.add_argument("--cases", default="custom_tasks/cases.json")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--output-dir", default=default_output_dir())
    ap.add_argument("--suite", default="individual_custom")
    ap.add_argument(
        "--run-class",
        choices=RUN_CLASSES[:-1],
        default="provisional",
        help="Evidence quality label recorded in the canonical ledger (default: provisional).",
    )
    ap.add_argument("--use-model-prompts", action="store_true")
    ap.add_argument("--prompt-profiles", default="custom_tasks/model_prompt_profiles.json")
    ap.add_argument("--tuning-profiles", default="model_tuning_profiles.json")
    ap.add_argument(
        "--require-model-prompt",
        action="store_true",
        help="Fail if model-specific prompt source is missing (no generic default fallback).",
    )
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--config-id", default="")
    ap.add_argument("--config-json", default="{}")
    ap.add_argument("--inference-config-json", default="{}")
    args = ap.parse_args()
    inference_config = normalize_inference_config(args.inference_config_json)
    try:
        benchmark_config = json.loads(args.config_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--config-json must be valid JSON: {exc}") from exc
    if not isinstance(benchmark_config, dict):
        raise SystemExit("--config-json must decode to an object")

    this_dir = Path(__file__).resolve().parent
    benchmark_root = Path(__file__).resolve().parents[2]
    catalog_path = (benchmark_root / args.catalog).resolve() if not Path(args.catalog).is_absolute() else Path(args.catalog)
    cases_path = (benchmark_root / args.cases).resolve() if not Path(args.cases).is_absolute() else Path(args.cases)
    prompt_profiles_path = (
        (benchmark_root / args.prompt_profiles).resolve()
        if not Path(args.prompt_profiles).is_absolute()
        else Path(args.prompt_profiles)
    )
    tuning_profiles_path = (
        (benchmark_root / args.tuning_profiles).resolve()
        if not Path(args.tuning_profiles).is_absolute()
        else Path(args.tuning_profiles)
    )

    catalog = load_catalog(catalog_path)
    case_map = load_cases(cases_path)
    prompt_profiles: dict[str, Any] = {}
    tuning_profiles: dict[str, Any] = {}
    if args.use_model_prompts:
        prompt_profiles = load_prompt_profiles(prompt_profiles_path)
        tuning_profiles = load_tuning_profiles(tuning_profiles_path)
        if args.require_model_prompt and not has_model_prompt_source(
            prompt_profiles,
            tuning_profiles,
            args.model,
        ):
            raise SystemExit(
                f"No model-specific prompt source found for model '{args.model}'. "
                "Add system_prompt in custom_tasks/model_prompt_profiles.json or model_tuning_profiles.json."
            )

    selected = catalog.get(args.id)
    if selected is None:
        raise SystemExit(f"Unknown test id '{args.id}'")
    if str(selected.get("harness", "")).strip() != "local_custom":
        raise SystemExit(f"Test '{args.id}' is not a local_custom test")
    test_cases = case_map.get(args.id, {}).get("cases", [])
    if not test_cases:
        raise SystemExit(f"No local custom cases defined for '{args.id}'")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / f"{args.id}_{model_safe(args.model)}_{now_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    passes = 0
    extractor_failures = 0
    for case in test_cases:
        prompt = str(case.get("prompt", "")).strip()
        if not prompt:
            continue
        system_prompt = ""
        prompt_source = "none"
        if args.use_model_prompts:
            system_prompt, prompt_source = resolve_system_prompt(
                prompt_profiles,
                tuning_profiles,
                args.model,
                args.id,
            )
        if inference_config.get("system_prompt") is not None:
            system_prompt = str(inference_config["system_prompt"])
            prompt_source = "inference_config"
        try:
            response, response_source = call_chat_completion(
                args.base_url,
                args.model,
                prompt,
                args.timeout,
                system_prompt,
                inference_config,
            )
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            if not args.no_record:
                failure_kind = "timeout" if isinstance(exc, requests.Timeout) else "request_failure"
                recorder = this_dir / "record_benchmark_result.py"
                failure_cmd = [
                    sys.executable,
                    str(recorder),
                    "--model",
                    args.model,
                    "--test-id",
                    args.id,
                    "--status",
                    "failure",
                    "--run-class",
                    args.run_class,
                    "--harness",
                    "local_custom",
                    "--suite",
                    args.suite,
                    "--failure-kind",
                    failure_kind,
                    "--failure-message",
                    f"{type(exc).__name__}: {exc}",
                    "--failed-request-count",
                    "1",
                    "--config-id",
                    args.config_id,
                    "--config-json",
                    json.dumps(benchmark_config, sort_keys=True),
                ]
                if failure_kind == "timeout":
                    failure_cmd.extend(["--timeout-count", "1"])
                subprocess.run(failure_cmd, check=False)
            raise
        if response_source == "empty":
            extractor_failures += 1
        passed, detail = grade_case(args.id, case, response)
        if passed:
            passes += 1
        results.append(
            {
                "name": str(case.get("name", "")),
                "passed": passed,
                "detail": detail,
                "prompt_source": prompt_source,
                "system_prompt_used": system_prompt,
                "response_source": response_source,
                "response": response,
            }
        )

    total = len(results)
    if total == 0:
        raise SystemExit(f"No runnable cases found for '{args.id}'")
    score = passes / total if total else 0.0

    prompts_snapshot: dict[str, Any] = {}
    if args.use_model_prompts and prompt_profiles:
        resolved_prompt, resolved_source = resolve_system_prompt(
            prompt_profiles,
            tuning_profiles,
            args.model,
            args.id,
        )
        prompts_snapshot = {
            "default_system_prompt": str(prompt_profiles.get("default_system_prompt", "")),
            "tuning_profiles_path": str(tuning_profiles_path),
            "resolved_system_prompt": resolved_prompt,
            "resolved_source": resolved_source,
        }
    if inference_config.get("system_prompt") is not None:
        prompts_snapshot["resolved_system_prompt"] = str(inference_config["system_prompt"])
        prompts_snapshot["resolved_source"] = "inference_config"

    payload = {
        "run_at": datetime.now().isoformat(),
        "test_id": args.id,
        "model": args.model,
        "base_url": args.base_url,
        "score": score,
        "metric": str(case_map.get(args.id, {}).get("metric", "pass_rate")),
        "use_model_prompts": bool(args.use_model_prompts),
        "prompt_profiles": str(prompt_profiles_path) if args.use_model_prompts else "",
        "prompts_snapshot": prompts_snapshot,
        "config_id": args.config_id,
        "benchmark_config": benchmark_config,
        "inference_config": inference_config,
        "cases": results,
    }
    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not args.no_record:
        recorder = this_dir / "record_benchmark_result.py"
        cmd = [
            sys.executable,
            str(recorder),
            "--model",
            args.model,
            "--test-id",
            args.id,
            "--score",
            str(score),
            "--raw-harness-score",
            str(score),
            "--metric",
            payload["metric"],
            "--run-class",
            args.run_class,
            "--sample-count",
            str(total),
            "--format-compatibility",
            "degraded" if extractor_failures else "compatible",
            "--extractor-failure-count",
            str(extractor_failures),
            "--harness",
            "local_custom",
            "--suite",
            args.suite,
            "--config-id",
            args.config_id,
            "--config-json",
            json.dumps(benchmark_config, sort_keys=True),
            "--notes",
            f"{passes}/{total} cases passed",
        ]
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)

    print(json.dumps({"result_path": str(result_path), "score": score, "passes": passes, "total": total}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
