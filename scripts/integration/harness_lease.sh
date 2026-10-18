#!/usr/bin/env bash
# Ask the rig manager (llm-gateway on the Pi, docs/MANAGER.md) for a GPU lease, the harness process
# every benchmark lane follows. Runs on the rig; reaches the manager with rigctl over ssh.
#   harness_lease.sh acquire <gpu> <owner> <run-id> [model]  -> prints the lease id
#   harness_lease.sh renew <lease-id> <owner>
#   harness_lease.sh release <lease-id> <owner>
# acquire exits 2 if the manager refuses (card held, claimed or busy) and the lane must not run.
# If the manager cannot be reached, acquire prints nothing and exits 0: the rig works offline, and
# run_runtime.sh audits the load as no-lease.
# Env: HARNESS_HOST (default pi), HARNESS_RIGCTL (default ~/llm-gateway/tools/rigctl.py on that host).
set -uo pipefail
HOST="${HARNESS_HOST:-pi}"
RIGCTL="${HARNESS_RIGCTL:-~/llm-gateway/tools/rigctl.py}"
TTL=600

rigctl() {  # every argument is a plain token (ids, numbers), so ssh's re-splitting is harmless
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" python3 "$RIGCTL" "$@"
}

case "${1:-}" in
  acquire)
    gpu=$2; owner=$3; run_id=$4; model=${5:-}
    out=$(rigctl acquire --controller benchmarks --owner "$owner" --run-id "$run_id" --gpus "$gpu" \
          --ttl "$TTL" --model "${model:-none}" 2>&1); rc=$?
    if [ "$rc" -eq 255 ] || grep -q "manager unreachable" <<< "$out"; then
      echo "harness_lease: manager not reachable; running without a lease" >&2
      exit 0
    fi
    if [ "$rc" -ne 0 ]; then
      echo "harness_lease: manager refused GPU $gpu: $(python3 -c 'import json,sys; print(json.load(sys.stdin)["error"]["message"])' <<< "$out" 2>/dev/null || echo "$out")" >&2
      exit 2
    fi
    python3 -c 'import json,sys; print(json.load(sys.stdin)["lease"]["lease_id"])' <<< "$out"
    ;;
  renew)
    [ -n "${2:-}" ] || exit 0
    rigctl renew "$2" --owner "$3" --ttl "$TTL" > /dev/null 2>&1 || true
    ;;
  release)
    [ -n "${2:-}" ] || exit 0
    rigctl release "$2" --owner "$3" > /dev/null 2>&1 || echo "harness_lease: release of $2 failed" >&2
    ;;
  *) echo "usage: harness_lease.sh acquire|renew|release ..." >&2; exit 64 ;;
esac
