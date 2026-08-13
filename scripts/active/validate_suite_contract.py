#!/usr/bin/env python3
"""Validate benchmark suite source trees against the campaign contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


CONTRACT_LABEL = 'LABEL daedalmap.benchmark.contract="campaign-v1"'


def load_contract(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("contract_version") != "campaign-v1":
        raise ValueError(f"unsupported contract version in {path}")
    if not isinstance(data.get("suites"), dict) or not data["suites"]:
        raise ValueError(f"contract has no suites: {path}")
    return data


def entrypoint_path(suite_dir: Path, dockerfile_text: str) -> Path:
    match = re.search(r'^ENTRYPOINT\s+\[\s*"[^"]+"\s*,\s*"([^"]+)"', dockerfile_text, re.MULTILINE)
    if match:
        return suite_dir / Path(match.group(1)).name
    match = re.search(r'^ENTRYPOINT\s+\[\s*"([^"]+)"', dockerfile_text, re.MULTILINE)
    if not match:
        raise ValueError(f"Dockerfile has no JSON ENTRYPOINT: {suite_dir / 'Dockerfile'}")
    return suite_dir / Path(match.group(1)).name


def required_flags(spec: dict[str, Any]) -> set[str]:
    flags = {"--model", "--run-name", "--run-class", "--results-dir"}
    if spec.get("runtime_mode") == "external":
        flags.add("--runtime-base")
    elif spec.get("runtime_mode") == "standalone":
        flags.add("--gguf")
    else:
        raise ValueError(f"invalid runtime_mode: {spec.get('runtime_mode')}")
    if spec.get("limit_supported"):
        flags.add("--limit")
    selector = spec.get("task_selector")
    if selector:
        flags.add(str(selector))
    if spec.get("profile_policy") in {"required", "task_prompt_plus_profile"}:
        flags.add("--tuning-profiles")
    if spec.get("hardware_id_required"):
        flags.add("--hardware-id")
    return flags


def validate(root: Path, contract_path: Path) -> list[str]:
    contract = load_contract(contract_path)
    errors: list[str] = []
    configured = set(contract["suites"])
    discovered = {p.name for p in root.glob("bench-*") if (p / "Dockerfile").is_file()}
    for missing in sorted(discovered - configured):
        errors.append(f"{missing}: Docker suite is not registered")
    for missing in sorted(configured - discovered):
        errors.append(f"{missing}: registered suite directory is missing")

    for suite, spec in sorted(contract["suites"].items()):
        suite_dir = root / suite
        dockerfile = suite_dir / "Dockerfile"
        if not dockerfile.is_file():
            continue
        docker_text = dockerfile.read_text(encoding="utf-8")
        if CONTRACT_LABEL not in docker_text:
            errors.append(f"{suite}: Dockerfile lacks {CONTRACT_LABEL}")
        try:
            entrypoint = entrypoint_path(suite_dir, docker_text)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not entrypoint.is_file():
            errors.append(f"{suite}: entrypoint source is missing: {entrypoint.name}")
            continue
        source = entrypoint.read_text(encoding="utf-8")
        for flag in sorted(required_flags(spec)):
            if flag not in source:
                errors.append(f"{suite}: entrypoint does not accept {flag}")
        for required_doc in ("README.md", f"BENCH_{suite.removeprefix('bench-').upper()}_HISTORY.md"):
            if not (suite_dir / required_doc).is_file():
                errors.append(f"{suite}: missing {required_doc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[2] / "docker"
    parser.add_argument("--docker-root", type=Path, default=default_root)
    parser.add_argument("--contract", type=Path, default=default_root / "suite_contracts.json")
    args = parser.parse_args()
    errors = validate(args.docker_root.resolve(), args.contract.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("suite contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
