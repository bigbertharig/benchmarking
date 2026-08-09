#!/usr/bin/env python3
"""Compatibility wrapper for the active Pareto builder."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    target = Path(__file__).resolve().parent / "scripts" / "active" / "build_pareto_frontier.py"
    return subprocess.run([sys.executable, str(target), *sys.argv[1:]], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
