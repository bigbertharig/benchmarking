#!/usr/bin/env bash
set -euo pipefail
root=/mnt/shared/experiments/kv-expert-chat-20261107/matched_placement_20261107
while [ ! -f "$root/stage.exit" ]; do
    sleep 30
done
if [ "$(cat "$root/stage.exit")" != 0 ]; then
    echo "model staging failed; see stage.log" >&2
    exit 2
fi
bash "$root/run_local_placement.sh" > "$root/local_campaign.log" 2>&1
