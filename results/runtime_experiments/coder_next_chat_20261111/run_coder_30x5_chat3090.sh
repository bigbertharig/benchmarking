#!/usr/bin/env bash
set -euo pipefail

repo=/mnt/shared/plans/shoulders/benchmarking
map="$repo/results/runtime_experiments/coder_next_chat_20261111/coder_experts_12345_prep.tsv"
runtime=/home/bryan/llm_orchestration/shared/scripts/llama_runtime/run_runtime.sh
model=/data/model-hotset/qwen3-coder-next/Qwen3-Coder-Next-Q4_K_S.gguf
overrides=()
while IFS=$'\t' read -r gpu pattern; do
  overrides+=("${pattern}=CUDA${gpu}")
done < "$map"
override_csv="$(IFS=,; echo "${overrides[*]}")"

exec "$runtime" \
  --name coder-chat3090-30x5-11522 --model "$model" --port 11522 \
  --gpus device=0,1,2,3,4,5 --image llama-runtime:b11669 \
  --ctx-size 250000 --batch-size 512 --parallel 1 --memory-limit 20g \
  --tensor-split 48,0,0,0,0,0 \
  --extra-arg --ubatch-size --extra-arg 32 \
  --extra-arg -ctk --extra-arg f16 --extra-arg -ctv --extra-arg f16 \
  --extra-arg --override-tensor --extra-arg "$override_csv"
