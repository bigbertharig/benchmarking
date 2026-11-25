#!/usr/bin/env bash
# Compatibility entry point for existing benchmark lanes. The implementation now consumes
# the public Orchestration lifecycle API. Remove when all lane launchers call managed_lease.py.
# Explicit BENCHMARK_CONTROLLER and optional BENCHMARK_ORCHESTRATION_COMMAND JSON argv are required.
# No Gateway checkout, SSH alias or automatic no-lease fallback.
set -euo pipefail
exec python3 "$(dirname "$0")/managed_lease.py" "$@"
