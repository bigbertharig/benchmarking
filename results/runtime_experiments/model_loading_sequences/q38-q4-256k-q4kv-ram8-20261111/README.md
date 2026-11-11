# Qwen3.8 Q4 256K cap: compact KV with 8 versus 12 GiB expert RAM

This [single-case follow-up manifest](../../../../campaigns/strata_q4_256k_q4kv_ram8_20261111.json) repeated the same one-chat, GPU0-resident Q4_0 KV, 256K-cap, 16K/32K/50K occupied-depth sequence as the [12 GiB tier series](../q38-q4-256k-tiers-20261110/README.md). Only the resident expert RAM budget changed to 8 GiB. Both loads held 5,225 expert slots / 15.24 GiB on GPU0; the 1060s were idle. Actual prompt depths were 16,893 / 33,726 / 52,959 tokens.

| Expert RAM | Complete request s, 16/32/50K | Prefill tok/s | Generated tok/s | Physical NVMe read GB |
| --- | --- | --- | --- | --- |
| 8 GiB | 362 / 299 / 332 | 53.9 / 62.2 / 66.5 | 5.2 / 9.0 / 5.9 | 153 / 127 / 138 |
| 12 GiB | **344 / 296 / 325** | 57.1 / 63.0 / 65.9 | 5.3 / 8.9 / 7.7 | **142 / 125 / 137** |

The extra 4 GiB RAM helped clearly at 16K, was close at 32K, and improved the 50K generated-token rate in this one series. It did not change GPU0 expert capacity. Physical NVMe bytes are host-wide block deltas and depend on cache warmth; this is not enough repetition for a stable ranking. Each response spent its 256-token budget in `reasoning_content` with no visible final answer, so correctness and Q4 KV quality remain unverified. The model's native metadata context is 262,144 tokens, but only 52,959 occupied tokens were exercised.

The [final loaded-state receipt](final_loaded.json) verifies that the **8 GiB Q4 KV layout remains loaded** after this follow-up. The 12 GiB layout had the shortest complete requests in these tests; it is a candidate for a repeated comparison and visible-answer check, not yet a default.
