#!/usr/bin/env python3
"""Resolve benchmark model profiles and aliases deterministically."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def normalize_model_id(value: str) -> str:
    value = value.strip().lower()
    if value.endswith(".gguf"):
        value = value[:-5]
    return re.sub(r"[^a-z0-9]+", "", value)


def _matching_key(models: dict[str, Any], model_id: str) -> str | None:
    if model_id in models:
        return model_id
    lowered = model_id.strip().lower()
    exact_casefold = [key for key in models if key.lower() == lowered]
    if len(exact_casefold) == 1:
        return exact_casefold[0]
    normalized = normalize_model_id(model_id)
    exact = [key for key in models if normalize_model_id(key) == normalized]
    if len(exact) == 1:
        return exact[0]
    fuzzy = [
        key for key in models
        if normalized
        and normalize_model_id(key)
        and (normalized in normalize_model_id(key) or normalize_model_id(key) in normalized)
    ]
    return fuzzy[0] if len(fuzzy) == 1 else None


def resolve_profile(models: dict[str, Any], model_id: str) -> tuple[str, dict[str, Any]] | None:
    key = _matching_key(models, model_id)
    if key is None or not isinstance(models.get(key), dict):
        return None

    seen: set[str] = set()

    def resolve(current: str) -> dict[str, Any]:
        if current in seen:
            raise ValueError(f"model profile alias cycle at {current}")
        seen.add(current)
        entry = models.get(current)
        if not isinstance(entry, dict):
            raise ValueError(f"model profile alias target is missing: {current}")
        alias = str(entry.get("_alias_of", "")).strip()
        if not alias:
            return dict(entry)
        canonical_key = _matching_key(models, alias)
        if canonical_key is None:
            raise ValueError(f"model profile alias target is missing: {alias}")
        merged = resolve(canonical_key)
        merged.update({k: v for k, v in entry.items() if k != "_alias_of"})
        merged["_resolved_from"] = canonical_key
        return merged

    return key, resolve(key)


def load_resolved_profile(path: Path, model_id: str) -> tuple[str, dict[str, Any]] | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.get("models", {})
    if not isinstance(models, dict):
        raise ValueError(f"profiles file has no models object: {path}")
    return resolve_profile(models, model_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--field", default="", help="Print one resolved field instead of JSON")
    parser.add_argument("--require-system-prompt", action="store_true")
    args = parser.parse_args()

    resolved = load_resolved_profile(args.profiles, args.model)
    if resolved is None:
        parser.error(f"no unique model profile for {args.model}")
    key, profile = resolved
    if args.require_system_prompt and not str(profile.get("system_prompt", "")).strip():
        parser.error(f"resolved profile for {args.model} has no system_prompt")
    if args.field:
        value = profile.get(args.field)
        if isinstance(value, (dict, list)):
            print(json.dumps(value, sort_keys=True))
        elif value is not None:
            print(value)
    else:
        print(json.dumps({"matched_key": key, "profile": profile}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
