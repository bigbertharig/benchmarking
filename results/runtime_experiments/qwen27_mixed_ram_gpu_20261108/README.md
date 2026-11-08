# Qwen3.6 27B mixed GPU and RAM chat tiers (2026-11-08)

The private-fork harness loaded Qwen3.6 27B Q4_K_M weights once on GPU0,
reported a 15,345.66 MiB CUDA0 model buffer, and added three 32,768-token
Q4 K/V contexts in order: GPU1 (576 MiB KV), CPU RAM (576 MiB KV), and
GPU2 (576 MiB KV). Their first completions were distinct and correct:
`Tokyo`, `Berlin`, and `Madrid` for the three capital prompts.

After the RAM chat was added, GPU1 and RAM chats generated 16 tokens each in
parallel (`ok=1`). After GPU2 was added, all three generated another 16 tokens
each in parallel (`ok=1`). The second phase took 1.510 seconds for 48 tokens
in total (31.78 aggregate tok/s); the RAM chat was the slowest at 10.60 tok/s.
This is a short-history placement and coexistence proof, not a deep recall or
steady serving result. The harness logs only each chat's first answer and
successful later decode, not answer correctness after interleaving.

The archived [`llama_simple_mixed.cpp`](../../../scripts/active/llama_simple_mixed.cpp)
is the exact private-fork harness source built for this run. The command and
resource guard are in
[`qwen27_mixed_ram_gpu_sequence.json`](../../../campaigns/qwen27_mixed_ram_gpu_sequence.json).
The terminal receipt is under the corresponding `model_loading_sequences`
run. Raw `.log`, `.gpu.csv`, `.pcie.txt`, `.start`, `.finish`, and `.exit`
files are copied here from the harness. The normal `chat-27b` route was
restored after the run.
