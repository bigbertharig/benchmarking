#!/usr/bin/env python3
"""Build or verify a portable campaign runtime directory without a Git checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "benchmark-campaign-package/1"
ROOT_FILES = (
    "model_registry.json", "model_library_export.json", "model_roles.json",
    "models.catalog.json", "model_tuning_profiles.json", "load_recipes.json",
    "subagent_catalog.json", "docker/suite_contracts.json",
    "custom_tasks/cases.json", "custom_tasks/brain_decisions_cases.json",
    "custom_tasks/model_prompt_profiles.json",
    "scripts/integration/wait_for_campaign_completion.py",
)


def package_files(root: Path) -> list[Path]:
    files = [Path(name) for name in ROOT_FILES]
    files.extend(path.relative_to(root) for path in (root / "scripts" / "active").glob("*.py"))
    for path in files:
        if not (root / path).is_file():
            raise ValueError(f"missing campaign package input: {path}")
    return sorted(files)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(root: Path, output: Path) -> dict:
    files = package_files(root)
    entries = {path.as_posix(): digest((root / path).read_bytes()) for path in files}
    manifest = {"schema": SCHEMA, "files": entries}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(root / path, "benchmarking-campaign/" + path.as_posix())
        archive.writestr("benchmarking-campaign/campaign_bundle.json",
                         json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


def verify(root: Path) -> dict:
    manifest = json.loads((root / "campaign_bundle.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"), dict):
        raise ValueError("unsupported campaign package manifest")
    for name, expected in manifest["files"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("unsafe campaign package path")
        if digest((root / path).read_bytes()) != expected:
            raise ValueError(f"campaign package input changed: {name}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("output", type=Path)
    build_parser.add_argument("--root", type=Path, default=ROOT)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            manifest = build(args.root, args.output)
            print(json.dumps({"package": str(args.output), "files": len(manifest["files"])}))
        else:
            manifest = verify(args.root)
            print(json.dumps({"verified": str(args.root), "files": len(manifest["files"])}))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
