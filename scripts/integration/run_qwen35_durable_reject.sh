#!/usr/bin/env bash
set -uo pipefail
label=${7:?label required}
base=/mnt/shared/experiments/kv-matrix-20261107
bash scripts/integration/run_qwen35_durable_nvme.sh "$@"
rc=$?
if [ "$rc" -eq 75 ] && grep -q 'DURABLE_REJECT reason=checksum' "$base/$label.log"; then
  date -u +%FT%TZ > "$base/$label.expected_reject"
  echo "DURABLE_EXPECTED_REJECT exit=$rc reason=checksum"
  exit 0
fi
echo "unexpected corruption-probe result: exit=$rc" >&2
exit 1
