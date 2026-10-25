#!/usr/bin/env python3
"""Collect the other repos' lessons files into benchmarking's own copy (results/imported_lessons/).

The four repos share knowledge without depending on each other. Benchmarking's lessons go out through the
model library (each other repo has its own importer that reads it). The other direction is this script: each
repo keeps a `lessons/` folder of what it learned while running (llm-gateway: every model load the manager
placed or that failed), and this copies those folders here, with where and when they came from, so
benchmarking can study them without the other repos needing to be present. Nothing is written into another
repo.

Usage (on the Pi):
  scripts/active/collect_lessons.py                 copy every repo found
  scripts/active/collect_lessons.py --list          show what would be copied
  LESSONS_SOURCES=name=path,name=path ...           other checkouts (default: the ones below)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "imported_lessons"
# Where each repo's lessons folder is on the Pi. A repo with no lessons/ yet is skipped.
DEFAULT_SOURCES = {
    "llm-gateway": Path.home() / "llm-gateway" / "lessons",
    "llm_orchestration": Path.home() / "llm_orchestration" / "lessons",
    "llm-harness": Path.home() / "llm-harness" / "lessons",
}


def sources() -> dict[str, Path]:
    env = os.getenv("LESSONS_SOURCES")
    if not env:
        return dict(DEFAULT_SOURCES)
    return {name: Path(path) for name, path in (item.split("=", 1) for item in env.split(",") if "=" in item)}


def commit_of(folder: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(folder), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="show what would be copied, copy nothing")
    a = ap.parse_args()
    copied = {}
    for name, folder in sources().items():
        if not folder.is_dir():
            print(f"{name}: no lessons folder at {folder}; skipped")
            continue
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        print(f"{name}: {len(files)} file(s) in {folder}")
        if a.list:
            for p in files:
                print(f"  {p.relative_to(folder)} ({p.stat().st_size} bytes)")
            continue
        dest = OUT / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(folder, dest)
        copied[name] = {"from": str(folder), "commit": commit_of(folder), "files": [str(p.relative_to(folder))
                                                                                    for p in files]}
    if not a.list and copied:
        manifest = {"collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": copied}
        (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}/ ({', '.join(copied)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
