# bench-knowledge: MC/loglikelihood benchmarks via llama.cpp + lm_eval gguf model type
# Targets: mmlu, arc_challenge, hellaswag, truthfulqa_mc2, boolq
#
# Build:
#   docker build -t bench-knowledge .
#
# Run:
#   docker run --gpus '"device=1"' \
#     -v /mnt/shared/models:/models:ro \
#     -v /mnt/shared/logs/benchmarks:/results \
#     bench-knowledge /models/qwen2.5-coder-7b/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf

# Stage 1: grab the llama-server binary from the runtime image (b8250, supports qwen35)
FROM llama-runtime:sm61-sm86 AS llama-src

# Stage 2: main image
FROM nvidia/cuda:12.6.3-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl \
    && rm -rf /var/lib/apt/lists/*

# Copy llama-server binary and its CUDA libs from runtime image
COPY --from=llama-src /opt/llama/bin/llama-server /opt/llama/bin/llama-server

# Create venv so pip doesn't complain about externally-managed
RUN python3 -m venv /opt/bench
ENV PATH="/opt/bench/bin:/opt/llama/bin:$PATH"

# Still need llama-cpp-python for the lm_eval gguf client model type
ENV CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=61;86"
RUN pip install --no-cache-dir llama-cpp-python[server]==0.3.16

# Install lm_eval and transformers (needed for tokenizer/chat templates)
RUN pip install --no-cache-dir lm_eval transformers

# Entrypoint script
COPY run.sh /opt/bench/run.sh
RUN chmod +x /opt/bench/run.sh

WORKDIR /opt/bench
ENTRYPOINT ["/opt/bench/run.sh"]
