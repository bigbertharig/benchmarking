#!/usr/bin/env python3
"""Build a controlled unified-runner campaign from an explicit profile list."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
INFERENCE_KEYS = {
    "temperature",
    "top_k",
    "top_p",
    "repeat_penalty",
    "thinking",
    "json_grammar",
    "system_prompt",
    "stop_sequences",
    "max_tokens",
}
RUNTIME_KEYS = {"ctx_size", "batch_size", "kv_cache", "chat_template", "extra_args"}


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_")
    if not cleaned:
        raise ValueError("profile id must contain a letter or digit")
    return cleaned


def merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def validate_inference(config: dict[str, Any]) -> None:
    unknown = set(config) - INFERENCE_KEYS
    if unknown:
        raise ValueError(f"unknown inference settings: {', '.join(sorted(unknown))}")
    for key in ("temperature", "top_p", "repeat_penalty"):
        value = config.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError(f"inference.{key} must be numeric or null")
    if config.get("temperature") is not None and not 0 <= config["temperature"] <= 2:
        raise ValueError("inference.temperature must be between 0 and 2")
    if config.get("top_p") is not None and not 0 < config["top_p"] <= 1:
        raise ValueError("inference.top_p must be greater than 0 and at most 1")
    if config.get("repeat_penalty") is not None and config["repeat_penalty"] <= 0:
        raise ValueError("inference.repeat_penalty must be positive")
    for key in ("top_k", "max_tokens"):
        value = config.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError(f"inference.{key} must be a non-negative integer or null")
    if config.get("max_tokens") == 0:
        raise ValueError("inference.max_tokens must be positive")
    for key in ("thinking", "json_grammar"):
        value = config.get(key)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"inference.{key} must be boolean or null")
    system_prompt = config.get("system_prompt")
    if system_prompt is not None and not isinstance(system_prompt, str):
        raise ValueError("inference.system_prompt must be a string or null")
    stops = config.get("stop_sequences", [])
    if not isinstance(stops, list) or any(not isinstance(item, str) or not item for item in stops):
        raise ValueError("inference.stop_sequences must be an array of non-empty strings")


def validate_runtime(config: dict[str, Any]) -> None:
    unknown = set(config) - RUNTIME_KEYS
    if unknown:
        raise ValueError(f"unknown runtime settings: {', '.join(sorted(unknown))}")
    for key in ("ctx_size", "batch_size"):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"runtime.{key} must be a positive integer")
    kv_cache = config.get("kv_cache", {})
    if not isinstance(kv_cache, dict) or set(kv_cache) - {"type_k", "type_v"}:
        raise ValueError("runtime.kv_cache supports only type_k and type_v")
    if any(not isinstance(value, str) or not value for value in kv_cache.values()):
        raise ValueError("runtime.kv_cache values must be non-empty strings")
    chat_template = config.get("chat_template")
    if chat_template is not None and (not isinstance(chat_template, str) or not chat_template):
        raise ValueError("runtime.chat_template must be a non-empty string or null")
    extra_args = config.get("extra_args", [])
    if not isinstance(extra_args, list) or any(not isinstance(item, str) or not item for item in extra_args):
        raise ValueError("runtime.extra_args must be an array of non-empty strings")


def runtime_args(config: dict[str, Any]) -> list[str]:
    args = list(config.get("extra_args", []))
    kv_cache = config.get("kv_cache", {})
    if kv_cache.get("type_k"):
        args.extend(["--cache-type-k", kv_cache["type_k"]])
    if kv_cache.get("type_v"):
        args.extend(["--cache-type-v", kv_cache["type_v"]])
    if config.get("chat_template"):
        args.extend(["--chat-template", config["chat_template"]])
    return args


def build_campaign(spec: dict[str, Any]) -> dict[str, Any]:
    required = ("name", "model", "gguf", "suite", "placement", "baseline", "profiles")
    missing = [key for key in required if not spec.get(key)]
    if missing:
        raise ValueError(f"matrix is missing required fields: {', '.join(missing)}")
    baseline = spec["baseline"]
    if not isinstance(baseline, dict):
        raise ValueError("baseline must be an object")
    profiles = spec["profiles"]
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("profiles must be a non-empty array")
    defaults = spec.get("defaults", {})
    suite_args = spec.get("suite_args", [])
    if not isinstance(defaults, dict) or not isinstance(suite_args, list):
        raise ValueError("defaults must be an object and suite_args must be an array")
    if any(not isinstance(item, (str, int, float)) or isinstance(item, bool) for item in suite_args):
        raise ValueError("suite_args values must be strings or numbers")
    if spec["suite"] != "bench-pipeline":
        raise ValueError("runtime matrices currently support only bench-pipeline")
    if spec["placement"] not in {"brain", "single", "split_1_3", "split_4_5"}:
        raise ValueError(f"unsupported placement: {spec['placement']}")
    if spec.get("run_class", "provisional") not in {"smoke", "provisional", "validated", "full"}:
        raise ValueError(f"unsupported run_class: {spec.get('run_class')}")

    blocks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    previous_id = ""
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict) or "id" not in profile:
            raise ValueError(f"profile #{index + 1} must be an object with an id")
        profile_id = safe_id(str(profile["id"]))
        if profile_id in seen_ids:
            raise ValueError(f"duplicate profile id: {profile_id}")
        seen_ids.add(profile_id)
        overrides = profile.get("overrides", {})
        if not isinstance(overrides, dict) or set(overrides) - {"inference", "runtime"}:
            raise ValueError(f"profile {profile_id} overrides supports only inference and runtime")
        resolved = merge_dict(baseline, overrides)
        inference = resolved.get("inference", {})
        runtime = resolved.get("runtime", {})
        if not isinstance(inference, dict) or not isinstance(runtime, dict):
            raise ValueError(f"profile {profile_id} inference and runtime must be objects")
        validate_inference(inference)
        validate_runtime(runtime)
        config_body = {
            "matrix": str(spec["name"]),
            "profile": profile_id,
            "inference": inference,
            "runtime": runtime,
        }
        config_json = json.dumps(config_body, sort_keys=True, separators=(",", ":"))
        config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
        block_id = safe_id(f"{spec['name']}_{profile_id}")
        args = [str(item) for item in suite_args]
        args.extend(
            [
                "--run-class",
                str(spec.get("run_class", "provisional")),
                "--config-id",
                f"{profile_id}-{config_hash[:12]}",
                "--config-json",
                config_json,
                "--inference-config-json",
                json.dumps(inference, sort_keys=True, separators=(",", ":")),
            ]
        )
        block = {
            "id": block_id,
            "model": str(spec["model"]),
            "gguf": str(spec["gguf"]),
            "placement": str(spec["placement"]),
            "suite": str(spec["suite"]),
            "suite_args": args,
            "runtime_args": runtime_args(runtime),
            "ctx_size": runtime["ctx_size"],
            "batch_size": runtime["batch_size"],
            "depends_on": [previous_id] if previous_id else [],
            "matrix_profile": profile_id,
            "config_hash": config_hash,
        }
        blocks.append(block)
        previous_id = block_id

    return {
        "name": str(spec["name"]),
        "description": str(spec.get("description", "")),
        "defaults": defaults,
        "matrix_policy": "explicit_profiles_sequential_same_slot",
        "blocks": blocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an explicit runtime matrix campaign.")
    parser.add_argument("matrix")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    matrix_path = Path(args.matrix).expanduser().resolve()
    spec = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise SystemExit("matrix definition must be a JSON object")
    try:
        campaign = build_campaign(spec)
    except ValueError as exc:
        raise SystemExit(f"invalid runtime matrix: {exc}") from exc
    output = Path(args.output).expanduser().resolve() if args.output else ROOT / "campaigns" / f"{safe_id(str(spec['name']))}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"Wrote runtime matrix campaign: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
