#!/usr/bin/env python3
"""Compile parameterized experiment cases into a managed schema-2 sequence.

This expands case parameters only. Physical GPU roles are deliberately left for
run_model_loading_sequence.py to resolve and freeze on the rig.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

VARIABLE = re.compile(r"\$\{([a-z][a-z0-9_]*)\}")
CASE_ID = re.compile(r"[a-z0-9][a-z0-9_]*\Z")
KINDS = frozenset({"model_fit", "depth_replay", "paired_replay", "service_replay",
                   "chat_sequence", "component_probe", "transfer_probe"})
LOAD_PATHS = frozenset({"managed", "experimental"})


def _expand(value, variables):
    if isinstance(value, str):
        def replacement(match):
            key = match.group(1)
            if key not in variables:
                raise ValueError(f"unbound template variable: {key}")
            return str(variables[key])
        result = VARIABLE.sub(replacement, value)
        if "${" in result:
            raise ValueError(f"invalid or unresolved template variable: {result}")
        return result
    if isinstance(value, list):
        return [_expand(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item, variables) for key, item in value.items()}
    return value


def _parameters(value, label):
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key)
        or not isinstance(item, (str, int, float, bool))
        for key, item in value.items()
    ):
        raise ValueError(f"{label} must be a map of scalar parameters")
    return value


def compile_experiment(source, source_bytes):
    if source.get("schema") != 3:
        raise ValueError("expected experiment schema 3")
    if not isinstance(source.get("name"), str) or not source["name"]:
        raise ValueError("experiment name required")
    roles = source.get("hardware_roles", {})
    defaults = source.get("defaults", {})
    template = source.get("template")
    cases = source.get("cases")
    if not isinstance(roles, dict) or not isinstance(defaults, dict) or not isinstance(template, dict):
        raise ValueError("hardware_roles, defaults and template must be objects")
    if not isinstance(cases, list) or not cases:
        raise ValueError("at least one case required")
    common = _parameters(source.get("parameters", {}), "parameters")
    stages = []
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) - {"id", "values", "stage"}:
            raise ValueError("case must have id, values and optional stage only")
        name = case.get("id")
        if not isinstance(name, str) or not CASE_ID.fullmatch(name) or name in seen:
            raise ValueError(f"invalid or duplicate case id: {name}")
        values = _parameters(case.get("values", {}), f"{name}.values")
        overrides = case.get("stage", {})
        if not isinstance(overrides, dict):
            raise ValueError(f"{name}.stage must be an object")
        variables = {**common, **values, "case_id": name}
        stage = _expand({**defaults, **template}, variables)
        if "env" in defaults and "env" in template:
            if not isinstance(defaults["env"], dict) or not isinstance(template["env"], dict):
                raise ValueError(f"{name}.env must be an object")
            stage["env"] = _expand({**defaults["env"], **template["env"]}, variables)
        expanded_overrides = _expand(overrides, variables)
        if "env" in expanded_overrides and "env" in stage:
            if not isinstance(stage["env"], dict) or not isinstance(expanded_overrides["env"], dict):
                raise ValueError(f"{name}.env must be an object")
            stage["env"] = {**stage["env"], **expanded_overrides.pop("env")}
        stage.update(expanded_overrides)
        stage["id"] = name
        kind = stage.get("kind")
        if kind not in KINDS:
            raise ValueError(f"{name}: unknown experiment kind: {kind}")
        load_path = stage.get("load_path")
        if load_path not in LOAD_PATHS:
            raise ValueError(f"{name}: load_path must be managed or experimental")
        if load_path == "experimental":
            if not isinstance(stage.get("experimental_reason"), str) or not stage["experimental_reason"].strip():
                raise ValueError(f"{name}: experimental load needs a reason")
            if not isinstance(stage.get("gpus"), list) or not stage["gpus"]:
                raise ValueError(f"{name}: experimental load needs card roles for Manager admission")
        elif stage.get("experimental_reason"):
            raise ValueError(f"{name}: managed load cannot have experimental_reason")
        baseline = stage.get("baseline")
        if baseline is not None and baseline not in seen:
            raise ValueError(f"{name}: baseline must name an earlier case")
        stage["case_values"] = values
        stages.append(stage)
        seen.add(name)
    return {"schema": 2, "name": source["name"], "hardware_roles": roles,
            "source_schema": 3, "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "defaults": {}, "cases": stages}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, help="write a deterministic schema-2 manifest")
    parser.add_argument("--check", action="store_true", help="print compiled manifest without writing")
    args = parser.parse_args()
    if not args.check and not args.output:
        parser.error("--output required unless --check is used")
    raw = args.source.read_bytes()
    result = compile_experiment(json.loads(raw), raw)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.check:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(encoded)
        os.replace(temporary, args.output)
        print(args.output)


if __name__ == "__main__":
    main()
