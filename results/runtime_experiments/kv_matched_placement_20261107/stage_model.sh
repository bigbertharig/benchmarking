#!/usr/bin/env bash
set -euo pipefail
root=/mnt/shared/experiments/kv-expert-chat-20261107/matched_placement_20261107
source=/mnt/shared/models/nemotron-3.5-bolt-74b-a9b/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL.gguf
dest_dir=/home/bryan/bench-model-stage
dest="$dest_dir/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL.gguf"
partial="$dest.part"
mkdir -p "$dest_dir"
date -u +%FT%TZ > "$root/stage.start"
rm -f "$root/stage.exit"
finish() {
    rc=$?
    trap - EXIT
    date -u +%FT%TZ > "$root/stage.finish"
    echo "$rc" > "$root/stage.exit"
    exit "$rc"
}
trap finish EXIT

expected=$(stat -c %s "$source")
available=$(df -B1 --output=avail / | tail -1 | tr -d ' ')
if [ ! -f "$dest" ] && [ "$available" -lt $((expected + 15000000000)) ]; then
    echo "insufficient root volume headroom: available=$available expected=$expected" >&2
    exit 2
fi
if [ -f "$dest" ] && [ "$(stat -c %s "$dest")" -eq "$expected" ]; then
    echo "STAGE_REUSE bytes=$expected path=$dest"
else
    rsync -a --partial --append-verify --info=progress2 "$source" "$partial"
    actual=$(stat -c %s "$partial")
    [ "$actual" -eq "$expected" ] || { echo "stage size mismatch: $actual != $expected" >&2; exit 3; }
    mv "$partial" "$dest"
    echo "STAGE_READY bytes=$actual path=$dest"
fi
