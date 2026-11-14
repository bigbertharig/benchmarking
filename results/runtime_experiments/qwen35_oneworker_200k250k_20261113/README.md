# 35B model on 3090: one 1060 versus one 1070 at 200K and 250K

Run date: 2026-11-13 (Denver). The Qwen3.6 35B-A3B Q4_K_XL model weights stayed on the RTX 3090 Ti. One main chat kept Q4_1 KV on the 3090, and one secondary chat kept Q4_1 KV on either a GTX 1060 6GB or GTX 1070 8GB. Both chats restored the same validated histories and generated 256 tokens. The worker was tested in 1060 → 1070 → 1060 order at 200,000 and 250,000 occupied tokens. All four sequence stages passed, and the session claim was released.

The model reports `n_ctx_train = 262144`. At 250K the saved chats restored with 250,036 tokens used, then generated to 250,292, within the 262,144-token reservation. Both new 250K histories passed independent private-code recalls before replay. Their checkpoints are about 1.6 GiB each. This establishes that 250K fitted this Q4_1 configuration on the current rig; it does not imply F16 KV or additional 3090 chats would fit.

## Worker chat speed with the 3090 chat active

| Occupied context | 1060 before | 1070 | 1060 after | 1070 gain versus mean 1060 |
| ---: | ---: | ---: | ---: | ---: |
| 200K | 9.928 tok/s | 13.385 tok/s | 9.916 tok/s | **+34.9%** |
| 250K | 8.087 tok/s | 10.917 tok/s | 8.073 tok/s | **+35.1%** |

The 1060 controls differ by 0.1–0.2%, so the relative gain is much larger than control drift. The 3090 chat with the 1060 before/after measured 36.47/36.60 tok/s at 200K and 30.87/30.86 at 250K; with the 1070 it measured 36.21 and 30.60 tok/s. Its paired speed changed by less than 1%.

The 1070's *relative* advantage grew from about 20% at 50K in the earlier one-worker study to about 35% at 200K, then remained near 35% at 250K. Both cards' absolute worker rates fell as context grew. This is one worker alongside the 3090 main chat; it does not establish that replacing every 1060 with a 1070 would produce a 35% gain under six-chat load. In each 256-token paired window the 3090 chat finished before the worker, so each worker's wall-time rate includes a period after the main stopped generating.

## Method and evidence

- The 200K states came from the validated Q4_1 tile curve (`qwen35_moe_q41_tile_curve_50k100k150k200k_20261109.states`). The new `moe_prepare_250k` mode restored each 200K state on the 3090, appended unrelated notes to 250K, checked recall, and saved the new state. The replay used worker1 for the main chat and worker2 for the secondary chat at each depth.
- `campaigns/qwen35_oneworker_200k250k_20261113.json` uses schema 2 hardware roles and PCI-bus-mapped CUDA ordinals. Host GPU0 was the 3090, GPU1 the 1060, and GPU2 the 1070. The replay binary was built separately against the validated Q4_1 tile libraries by `scripts/integration/build_deep_replay.sh`.
- The sequence receipt is `results/runtime_experiments/model_loading_sequences/qwen35-oneworker-deep-20261113/terminal.json`. Raw `GEN_METRIC`, recall, CUDA mapping, UUID, GPU and PCIe logs are under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_deep_250k_prep_20261113*` and `qwen35_oneworker_200k250k_20261113_*` on the rig, also shared to the Pi under `/home/bryan/llm_orchestration/shared/experiments/`.
