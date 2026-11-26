#!/usr/bin/env python3
"""Publish the versioned, portable model knowledge consumed by rig repos."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import model_library
import model_profiles
from benchmark_records import best_by_model_test_group, latest_successful_by_model_test

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "model_library_export.json"
SCHEMA = "gpu-rig-model-library/1"
KEY_TESTS = (("bbh", "bbh_flexible"), ("gsm8k", "gsm8k_flexible"),
             ("drop", "drop_flexible"), ("ifeval", "ifeval_prompt_level_strict_acc_none"),
             ("mmlu-pro", "mmlu_pro_flexible"), ("humaneval+", "humaneval_plus"),
             ("mbpp+", "mbpp_plus"))


def read(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def summary(registry: dict, roles: dict) -> dict:
    records = ROOT / "results/model_benchmark_records.jsonl"
    measurements = []
    if records.is_file():
        for line in records.read_text(encoding="utf-8").splitlines():
            try:
                measurements.append(json.loads(line))
            except ValueError:
                continue
    def evidence(row: dict) -> dict:
        methodology = row.get("methodology") or {}
        test = str(row["test_id"])
        config_id = str((row.get("runtime") or {}).get("config_id") or "")
        version = re.search(r"extract-v(\d+)$", config_id)
        return {
            "score": float(row["score"]),
            "run_class": row.get("run_class") or "legacy",
            "n": row.get("sample_count"),
            "at": str(row.get("run_at") or "")[:10],
            "unreadable": row.get("extractor_failure_count") or 0 if version and int(version.group(1)) >= 5 else None,
            "run_id": row.get("run_id"),
            "methodology": {
                "id": methodology.get("id") or "legacy-unversioned",
                "version": methodology.get("version") or "unversioned",
                "comparison_group": methodology.get("comparison_group") or f"legacy:{test}",
            },
            "config_hash": (row.get("runtime") or {}).get("config_hash") or None,
            "reproduction": {
                "suite": row.get("suite"),
                "command": row.get("command"),
                "runtime_config": (row.get("runtime") or {}).get("config") or {},
            },
        }

    current = {
        (str(row["model"]), str(row["test_id"])): evidence(row)
        for row in latest_successful_by_model_test(measurements)
    }
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in best_by_model_test_group(measurements):
        grouped.setdefault((str(row["model"]), str(row["test_id"])), []).append(evidence(row))
    rows = []
    for mid, entry in registry["models"].items():
        sched = entry.get("schedule") or {}
        scores = {label: current[(mid, test)] for label, test in KEY_TESTS
                  if (mid, test) in current}
        score_groups = {label: grouped[(mid, test)] for label, test in KEY_TESTS
                        if len(grouped.get((mid, test), [])) > 1}
        pipeline_headlines = [
            evidence for (model, test), evidence in current.items()
            if model == mid and test.startswith("custom_")
        ]
        # The strict-JSON grader changed independently of the other five tasks.
        # The current rollup follows each task's latest selected score; retain the
        # per-task methodology and command so mixed versions remain inspectable.
        pipeline = (round(sum(item["score"] for item in pipeline_headlines) /
                          len(pipeline_headlines), 3)
                    if len(pipeline_headlines) == 6 else None)
        pipeline_tests = len(pipeline_headlines)
        pipeline_evidence = {test: item for (model, test), item in current.items()
                             if model == mid and test.startswith("custom_")}
        pipeline_groups: dict[tuple[str, str], list[float]] = {}
        for (model, test), evidence_rows in grouped.items():
            if model != mid or not test.startswith("custom_"):
                continue
            for item in evidence_rows:
                method = item["methodology"]
                key = (method["id"], method["comparison_group"])
                pipeline_groups.setdefault(key, []).append(item["score"])
        pipeline_by_group = [
            {"methodology_id": method, "comparison_group": group,
             "score": round(sum(values) / len(values), 3), "tests": len(values)}
            for (method, group), values in sorted(pipeline_groups.items())
        ]
        slug = re.sub(r"[:.]", "_", mid)
        files = sorted((ROOT / "results/runtime_experiments").glob(
            f"{slug}_runtime_characterization_*.json"))
        runtime = None
        if files:
            item = json.loads(files[-1].read_text(encoding="utf-8"))
            rt, dec = item.get("runtime") or {}, item.get("decode") or {}
            runtime = {"decode_tps": dec.get("generation_tokens_per_second"),
                       "prompt_tps": dec.get("prompt_tokens_per_second"),
                       "ctx": rt.get("ctx_size"), "tensor_split": rt.get("tensor_split"),
                       "file": files[-1].name, "at": files[-1].stem.rsplit("_", 1)[-1]}
        rows.append({"model": mid, "status": entry.get("status"),
                     "placement": sched.get("placement"), "tier": sched.get("tier"),
                     "profiles": sorted((entry.get("profiles") or {}).keys()),
                     "roles": sorted(name for name, spec in roles["roles"].items()
                                     if isinstance(spec, dict) and spec.get("model") == mid),
                     "source_url": entry.get("source_url"), "superseded_by": entry.get("superseded_by"),
                     "scores": scores, "score_groups": score_groups,
                     "pipeline": pipeline, "pipeline_tests": pipeline_tests,
                     "pipeline_by_group": pipeline_by_group, "pipeline_evidence": pipeline_evidence, "runtime": runtime})
    rows.sort(key=lambda row: ({"active": 0, "candidate": 1}.get(row["status"], 2), row["model"]))
    return {"key_tests": [label for label, _ in KEY_TESTS], "models": rows,
            "roles": {key: value.get("model") for key, value in roles["roles"].items()
                      if isinstance(value, dict)}}


def canonical_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def validate_subagents(document: dict, registry: dict, evidence_root: Path | None = None) -> None:
    """Validate benchmark-owned capabilities before publishing them to consumers."""
    if document.get("schema_version") != 1 or not isinstance(document.get("candidates"), dict):
        raise ValueError("invalid subagent catalog")
    for candidate_id, candidate in document["candidates"].items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", candidate_id) or not isinstance(candidate, dict):
            raise ValueError(f"invalid subagent candidate {candidate_id!r}")
        if candidate.get("provider") != "rig_shared_chat":
            continue
        model = candidate.get("model")
        if model not in registry["models"]:
            raise ValueError(f"subagent {candidate_id} names unknown model")
        evidence = candidate.get("evidence")
        if evidence_root is not None and isinstance(evidence, str) and evidence.startswith("results/"):
            path = (evidence_root / evidence).resolve()
            if not path.is_relative_to(evidence_root.resolve()) or not path.is_file():
                raise ValueError(f"subagent {candidate_id} evidence is missing: {evidence}")
        if candidate.get("context_allocation") not in ("fixed_per_chat", "dynamic_at_attach"):
            raise ValueError(f"subagent {candidate_id} has invalid context allocation")
        context_cap = candidate.get("context_cap")
        if type(context_cap) is not int or context_cap < 1:
            raise ValueError(f"subagent {candidate_id} has invalid context cap")
        if candidate.get("context_allocation") == "dynamic_at_attach":
            context_min = candidate.get("context_min")
            context_default = candidate.get("context_default")
            if (type(context_min) is not int or type(context_default) is not int
                    or not 1 <= context_min <= context_default <= context_cap):
                raise ValueError(f"subagent {candidate_id} has invalid dynamic context range")
            estimate = candidate.get("memory_estimate")
            if (not isinstance(estimate, dict)
                    or any(type(estimate.get(field)) is not int or estimate[field] < 0
                           for field in ("fixed_compute_mib", "kv_mib_at_262144",
                                         "admission_reserve_mib"))
                    or not isinstance(estimate.get("method"), str) or not estimate["method"]):
                raise ValueError(f"subagent {candidate_id} has invalid memory estimate")
        if type(candidate.get("max_attached_chats")) is not int or candidate["max_attached_chats"] < 1:
            raise ValueError(f"subagent {candidate_id} has invalid attached chat limit")


def build() -> dict:
    registry = read("model_registry.json")
    roles = read("model_roles.json")
    recipes = read("load_recipes.json")
    catalog = read("models.catalog.json")
    subagents = read("subagent_catalog.json")
    tuning_profiles = read("model_tuning_profiles.json")
    problems = model_library.validate(registry, roles) + model_library.generated_drift(registry)
    if problems:
        raise ValueError("invalid benchmarking model library: " + "; ".join(problems[:8]))
    if recipes.get("schema_version") != 1 or not isinstance(recipes.get("recipes"), dict):
        raise ValueError("invalid load recipes")
    validate_subagents(subagents, registry, ROOT)
    if not isinstance(tuning_profiles.get("models"), dict):
        raise ValueError("invalid tuning profiles")
    for name, recipe in recipes["recipes"].items():
        if recipe.get("model") not in registry["models"]:
            raise ValueError(f"recipe {name} names unknown model")
    for name, spec in roles["roles"].items():
        if spec.get("model") not in registry["models"]:
            raise ValueError(f"role {name} names unknown model")
    resolved = {mid: {profile: model_library.resolve(mid, profile, registry)
                      for profile in entry["profiles"]}
                for mid, entry in registry["models"].items()}
    resolved_tuning = {key: model_profiles.resolve_profile(tuning_profiles["models"], key)[1]
                       for key in tuning_profiles["models"]}
    payload = {"schema": SCHEMA, "registry": registry, "roles": roles,
               "load_recipes": recipes, "models_catalog": catalog,
               "subagent_catalog": subagents, "tuning_profiles": tuning_profiles,
               "resolved_profiles": resolved, "resolved_tuning_profiles": resolved_tuning,
               "summary": summary(registry, roles)}
    return {"source_sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest(), **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("what-new", "sync", "check"))
    args = parser.parse_args()
    try:
        after = build()
        before = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.is_file() else {}
        rendered = json.dumps(after, indent=2, ensure_ascii=True) + "\n"
        stale = before != after or (OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") != rendered)
        print(json.dumps({"stale": stale, "source_sha256": after["source_sha256"],
                          "models": len(after["registry"]["models"])}))
        if args.mode == "sync" and stale:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=OUTPUT.parent,
                                             prefix=".model_library_export.", suffix=".tmp",
                                             delete=False) as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
                temp = Path(handle.name)
            try:
                os.replace(temp, OUTPUT)
            finally:
                temp.unlink(missing_ok=True)
        return 1 if args.mode == "check" and stale else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
