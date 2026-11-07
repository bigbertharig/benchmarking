#!/usr/bin/env bash
set -euo pipefail
root=/mnt/shared/experiments/kv-expert-chat-20261107/matched_placement_20261107
while [ ! -f "$root/local_campaign.exit" ]; do
    sleep 60
done
python3 "$root/analyze_matched_placement.py"
python3 "$root/archive_matched_placement.py"
date -u +%FT%TZ > "$root/postprocess.finish"
