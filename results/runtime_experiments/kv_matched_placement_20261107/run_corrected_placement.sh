#!/usr/bin/env bash
set -euo pipefail
base=/mnt/shared/experiments/kv-expert-chat-20261107
root="$base/matched_placement_20261107"
model=/mnt/shared/models/nemotron-3.5-bolt-74b-a9b/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL.gguf
python3 "$root/validate_layout.py"
date -u +%FT%TZ > "$root/corrected.start"
rm -f "$root/corrected.exit"
finish() {
    rc=$?
    trap - EXIT
    date -u +%FT%TZ > "$root/corrected.finish"
    echo "$rc" > "$root/corrected.exit"
    exit "$rc"
}
trap finish EXIT

export KV_MODEL_DEVICES=0,1,2,3,4
export KV_MODEL_SPLIT=88,0,0,0,0

run_case() {
    local layout=$1 phase=$2 label=$3
    export KV_TENSOR_OVERRIDES_FILE="/state/matched_placement_20261107/${layout}.tsv"
    date -u +%FT%TZ
    echo "CASE $label layout=$layout phase=$phase"
    if [ "$phase" = short ]; then
        bash "$base/run_expert_matrix.sh" two_workers_and_pair "$model" 8192 8192 131072 256 "$label"
    else
        bash "$base/run_expert_matrix.sh" two_workers_depth "$model" 8192 8192 32768 128 "$label"
    fi
}

run_case interleaved_balanced short matched_B_balanced_short
run_case contiguous short matched_A2_short
run_case interleaved_balanced depth matched_B_balanced_depth
run_case contiguous depth matched_A_depth
