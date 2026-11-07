#!/usr/bin/env bash
set -euo pipefail
name=rig-remote-chat-27b
model=/data/model-hotset/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf
[ -f "$model" ]
if [ -n "$(docker ps -q -f "name=^/${name}$")" ]; then
    echo "already running: $name"
    exit 0
fi
if [ -n "$(docker ps -aq -f "name=^/${name}$")" ]; then
    echo "container exists but is stopped: $name" >&2
    exit 2
fi
docker run -d --rm --gpus all --network host \
    --name "$name" \
    -v /data/model-hotset:/data/model-hotset:ro \
    llama-runtime:b11669 \
    llama-server --model "$model" --host 127.0.0.1 --port 11434 \
    --n-gpu-layers all --batch-size 512 --threads 8 --parallel 1 \
    --flash-attn on -ctk q8_0 -ctv q8_0 -lv 4 --ctx-size 201728 \
    --device CUDA0 --cache-ram 4096 --reasoning off
for _ in $(seq 1 90); do
    if curl -fsS http://127.0.0.1:11434/health >/dev/null 2>&1; then
        echo "healthy: $name"
        exit 0
    fi
    sleep 2
done
echo "health endpoint did not respond: $name" >&2
exit 3
