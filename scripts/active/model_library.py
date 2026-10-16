#!/usr/bin/env python3
"""The rig's model library: one registry of tested models, one quick reference of roles.

Sources (the only files edited by hand):
  model_registry.json  every tested model: archive GGUF, status, scheduling, named profiles
                       (default = benchmark settings, interactive = remote use, orchestration =
                       orchestrator llama launch), plus orchestration_defaults
  model_roles.json     which model + profile to use per rig lane and job, plus remote profiles

Generated from the registry (never edit; `export` rewrites them, `check` fails on drift):
  models.catalog.json, model_tuning_profiles.json, custom_tasks/model_prompt_profiles.json

Usage:
  model_library.py role brain               resolved settings for a role
  model_library.py model qwen3.6:27b [--profile interactive]
  model_library.py remote-profiles          resolved remote profiles (rig mode selector, gateway)
  model_library.py job "extract json from a page"
  model_library.py export                   rewrite the generated files
  model_library.py check                    validate sources and generated files (exit 1 on problems)
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "model_registry.json"
ROLES_PATH = ROOT / "model_roles.json"
CATALOG_PATH = ROOT / "models.catalog.json"
TUNING_PATH = ROOT / "model_tuning_profiles.json"
PROMPT_PROFILES_PATH = ROOT / "custom_tasks" / "model_prompt_profiles.json"
GENERATED_NOTE = "Generated from model_registry.json by scripts/active/model_library.py export. Do not edit."
ROLE_STATUSES = {"active"}
ORCHESTRATOR_ROLES = ("brain", "single_1060")
STATUSES = {"active", "candidate", "archived", "invalid"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return load_json(path)


def load_roles(path: Path = ROLES_PATH) -> dict[str, Any]:
    return load_json(path)


def find_model(registry: dict[str, Any], model_id: str) -> tuple[str, dict[str, Any]]:
    """Registry entry for a model id or one of its aliases."""
    models = registry["models"]
    if model_id in models:
        return model_id, models[model_id]
    for mid, entry in models.items():
        if model_id in entry.get("aliases", []):
            return mid, entry
    raise KeyError(f"model {model_id} is not in {REGISTRY_PATH.name}")


def gguf_path(registry: dict[str, Any], entry: dict[str, Any]) -> str:
    return f"{registry['archive_root']}/{entry['gguf']}"


def resolve(model_id: str, profile: str = "default", registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fully merged settings for one model profile.

    A named profile overrides the default profile: its runtime fields are merged over the
    default runtime, and any other field it sets replaces the default's value.
    """
    registry = registry or load_registry()
    mid, entry = find_model(registry, model_id)
    profiles = entry["profiles"]
    if profile not in profiles:
        raise KeyError(f"model {mid} has no profile {profile}; profiles: {sorted(profiles)}")
    merged = copy.deepcopy(profiles["default"])
    if profile != "default":
        for key, value in profiles[profile].items():
            if key == "runtime":
                merged["runtime"] = {**merged.get("runtime", {}), **value}
            else:
                merged[key] = copy.deepcopy(value)
    merged.setdefault("extra_args", [])
    return {
        "model": mid,
        "profile": profile,
        "status": entry["status"],
        "gguf_path": gguf_path(registry, entry),
        "schedule": copy.deepcopy(entry.get("schedule", {})),
        **merged,
    }


def resolve_role(role: str, roles: dict[str, Any] | None = None,
                 registry: dict[str, Any] | None = None) -> dict[str, Any]:
    roles = roles or load_roles()
    if role not in roles["roles"]:
        raise KeyError(f"unknown role {role}; roles: {sorted(roles['roles'])}")
    spec = roles["roles"][role]
    return {"role": role, **{k: v for k, v in spec.items() if k not in ("model", "profile")},
            **resolve(spec["model"], spec.get("profile", "default"), registry)}


def remote_profiles(roles: dict[str, Any] | None = None,
                    registry: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Remote profiles with their model settings flattened for the rig and the gateway."""
    roles = roles or load_roles()
    registry = registry or load_registry()
    out = {}
    for rp in roles["remote_profiles"]:
        r = resolve(rp["model"], rp.get("profile", "default"), registry)
        out[rp["id"]] = {
            **{k: copy.deepcopy(v) for k, v in rp.items() if k != "profile"},
            "model": r["model"], "gguf_path": r["gguf_path"],
            "ctx_size": r["runtime"]["ctx_size"], "batch_size": r["runtime"]["batch_size"],
            "parallel": r["runtime"].get("parallel", 1), "extra_args": r["extra_args"],
            **({"tensor_split": r["tensor_split"]} if r.get("tensor_split") else {}),
            **({"image": r["image"]} if r.get("image") else {}),
        }
    return out


def job_role(text: str, roles: dict[str, Any] | None = None) -> tuple[str, str] | None:
    """(job id, role) whose keywords best match a task description, or None."""
    roles = roles or load_roles()
    lowered = text.lower()
    best = None
    for job in roles["jobs"]:
        hits = sum(1 for kw in job["keywords"] if kw in lowered)
        if hits and (best is None or hits > best[0]):
            best = (hits, job["id"], job["role"])
    return (best[1], best[2]) if best else None


# ---------------------------------------------------------------------------- generated files

def export_catalog(registry: dict[str, Any]) -> dict[str, Any]:
    models = []
    for mid, entry in registry["models"].items():
        sched = entry.get("schedule")
        if not sched:
            continue
        row = {"id": mid, "tier": sched["tier"], "placement": sched["placement"],
               "gguf_path": gguf_path(registry, entry)}
        if "split_groups" in sched:
            row["split_groups"] = sched["split_groups"]
        row["tags"] = sched.get("tags", [])
        models.append(row)
    return {"_comment": GENERATED_NOTE, **registry["catalog_defaults"], "models": models}


def export_tuning(registry: dict[str, Any]) -> dict[str, Any]:
    """Default profiles keyed by GGUF file name, with every model id and alias pointing at them."""
    models: dict[str, Any] = {}
    for mid, entry in registry["models"].items():
        p = entry["profiles"]["default"]
        tuning = p.get("tuning", {})
        name = Path(entry["gguf"]).name
        row = {
            "status": tuning.get("status", "untuned"),
            "last_tuned_at": tuning.get("last_tuned_at"),
            "benchmark_suite": tuning.get("benchmark_suite", "agent_reliability"),
            "system_prompt": p["system_prompt"],
            "inference": p["inference"],
            "runtime": p["runtime"],
        }
        if p.get("extra_args"):
            row["extra_args"] = p["extra_args"]
        if p.get("notes"):
            row["notes"] = p["notes"]
        models[name] = row
        for alias in [mid, *entry.get("aliases", [])]:
            if alias != name:
                models[alias] = {"_alias_of": name}
    return {"version": registry["updated"], "notes": GENERATED_NOTE, "models": models}


def export_prompt_profiles(registry: dict[str, Any]) -> dict[str, Any]:
    models = [
        {"id": Path(entry["gguf"]).name, "system_prompt": entry["profiles"]["default"]["system_prompt"],
         "test_overrides": entry["test_prompt_overrides"]}
        for entry in registry["models"].values() if entry.get("test_prompt_overrides")
    ]
    return {"version": registry["updated"], "notes": GENERATED_NOTE, "default_system_prompt": "", "models": models}


GENERATED = {
    CATALOG_PATH: export_catalog,
    TUNING_PATH: export_tuning,
    PROMPT_PROFILES_PATH: export_prompt_profiles,
}


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True) + "\n"


def export(registry: dict[str, Any] | None = None) -> list[Path]:
    registry = registry or load_registry()
    written = []
    for path, build in GENERATED.items():
        path.write_text(render(build(registry)), encoding="utf-8", newline="\n")
        written.append(path)
    return written


# ---------------------------------------------------------------------------- validation

def validate(registry: dict[str, Any], roles: dict[str, Any], archive_root: Path | None = None) -> list[str]:
    """Problems in the two source files. archive_root, when given, also checks every GGUF exists."""
    errors: list[str] = []
    models = registry["models"]
    seen: dict[str, str] = {}
    for mid, entry in models.items():
        for name in [mid, *entry.get("aliases", [])]:
            if name in seen:
                errors.append(f"id/alias {name} used by {seen[name]} and {mid}")
            seen[name] = mid
        if entry.get("status") not in STATUSES:
            errors.append(f"{mid}: status must be one of {sorted(STATUSES)}")
        if "default" not in entry.get("profiles", {}):
            errors.append(f"{mid}: no default profile")
        else:
            d = entry["profiles"]["default"]
            for key in ("system_prompt", "inference", "runtime"):
                if key not in d:
                    errors.append(f"{mid}: default profile has no {key}")
        sup = entry.get("superseded_by")
        if sup and sup not in models:
            errors.append(f"{mid}: superseded_by {sup} is not in the registry")
        if entry.get("status") == "archived" and not entry.get("status_note"):
            errors.append(f"{mid}: archived without status_note")
        if archive_root is not None and not (archive_root / entry["gguf"]).is_file():
            errors.append(f"{mid}: GGUF missing under {archive_root}: {entry['gguf']}")
        orch = entry.get("profiles", {}).get("orchestration")
        if orch is not None and "ctx_size" not in orch.get("runtime", {}):
            errors.append(f"{mid}: orchestration profile has no runtime.ctx_size")

    # The orchestrator loads the brain and worker defaults from these (llm_orchestration brain_core).
    for lane in ORCHESTRATOR_ROLES:
        if lane not in roles["roles"]:
            errors.append(f"role {lane} is required by the orchestrator")
    for kind in ("single", "split"):
        if "ctx_size" not in registry.get("orchestration_defaults", {}).get(kind, {}):
            errors.append(f"orchestration_defaults.{kind} needs ctx_size")

    def check_ref(where: str, model_id: str, profile: str) -> None:
        try:
            mid, entry = find_model(registry, model_id)
        except KeyError as exc:
            errors.append(f"{where}: {exc}")
            return
        if entry["status"] not in ROLE_STATUSES:
            errors.append(f"{where}: {mid} is {entry['status']}, roles may only use active models")
        if profile not in entry["profiles"]:
            errors.append(f"{where}: {mid} has no profile {profile}")

    for role, spec in roles["roles"].items():
        check_ref(f"role {role}", spec["model"], spec.get("profile", "default"))
    for job in roles["jobs"]:
        if job["role"] not in roles["roles"]:
            errors.append(f"job {job['id']}: unknown role {job['role']}")
    ids = set()
    for rp in roles["remote_profiles"]:
        if rp["id"] in ids:
            errors.append(f"remote profile {rp['id']} defined twice")
        ids.add(rp["id"])
        check_ref(f"remote profile {rp['id']}", rp["model"], rp.get("profile", "default"))
        if not rp.get("gpus_needed"):
            errors.append(f"remote profile {rp['id']}: gpus_needed is required")
        else:
            try:
                runtime = resolve(rp["model"], rp.get("profile", "default"), registry)["runtime"]
                if "ctx_size" not in runtime or "batch_size" not in runtime:
                    errors.append(f"remote profile {rp['id']}: profile lacks ctx_size/batch_size")
            except KeyError:
                pass
    return errors


def generated_drift(registry: dict[str, Any]) -> list[str]:
    drift = []
    for path, build in GENERATED.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != render(build(registry)):
            drift.append(f"{path.relative_to(ROOT)} differs from the registry; run model_library.py export")
    return drift


# ---------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="Rig model library", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("role")
    s.add_argument("name")
    s = sub.add_parser("model")
    s.add_argument("id")
    s.add_argument("--profile", default="default")
    sub.add_parser("remote-profiles")
    s = sub.add_parser("job")
    s.add_argument("text")
    sub.add_parser("export")
    s = sub.add_parser("check")
    s.add_argument("--archive-root", type=Path, help="also require every GGUF to exist under this root")
    args = ap.parse_args()

    try:
        if args.cmd == "role":
            print(json.dumps(resolve_role(args.name), indent=2))
        elif args.cmd == "model":
            print(json.dumps(resolve(args.id, args.profile), indent=2))
        elif args.cmd == "remote-profiles":
            print(json.dumps(remote_profiles(), indent=2))
        elif args.cmd == "job":
            match = job_role(args.text)
            print(json.dumps({"job": match[0], **resolve_role(match[1])} if match else None, indent=2))
        elif args.cmd == "export":
            for path in export():
                print(f"wrote {path.relative_to(ROOT)}")
        elif args.cmd == "check":
            registry, roles = load_registry(), load_roles()
            problems = validate(registry, roles, args.archive_root) + generated_drift(registry)
            for p in problems:
                print(f"problem: {p}")
            print("ok" if not problems else f"{len(problems)} problem(s)")
            return 1 if problems else 0
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
