# Qwen3.6 27B GPU weights with RAM KV (2026-11-08)

One guarded private-fork `ram_kv` case loaded Qwen3.6 27B Q4_K_M weights once
on GPU0 and created a 32,768-token Q4 K/V context in host RAM. The model log
reports a 15,345.66 MiB CUDA0 model buffer, a 576.00 MiB CPU KV buffer,
`MODEL_READY one weight load`, and the expected first completion (`Tokyo` for
the capital of Japan). The 32-token continuation completed in 2.73 seconds
(11.72 tok/s). The sequence and harness exited 0.

This establishes a 27B RAM-KV single-chat fit with GPU0 weights. The prompt
occupied only five tokens before generation. It does not test long occupied
history, correctness at depth, or a RAM-backed chat coexisting with 1060-backed
chats on the same weight load. The normal `chat-27b` route was restored after
the experiment.

Artifacts: `terminal.json` is the sequence receipt. The `.log`, `.gpu.csv`,
`.pcie.txt`, `.start`, `.finish`, and `.exit` files are the raw private-harness
receipts. The source runner is the existing private-fork `run_matrix.sh` with
`/data/bench-staging/kvchat-b11669-build` and the exact model path in
[`campaigns/qwen27_ram_kv_sequence.json`](../../../campaigns/qwen27_ram_kv_sequence.json).
