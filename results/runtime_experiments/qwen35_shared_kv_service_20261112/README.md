# Qwen3.6 35B shared-weight chat service ? 2026-11-12

The private patched llama.cpp runtime now keeps one Q4_K_XL model instance on GPU0 and exposes independent Q4_0 KV chat contexts on GPU0 and GPUs1?5. Orchestration commits [`429baf7`](https://github.com/bigbertharig/llm_orchestration/commit/429baf7) and [`c4e3a7c`](https://github.com/bigbertharig/llm_orchestration/commit/c4e3a7c) own the source, build script, named commands, and rig status/stop integration. The [receipt](receipt.json) records the live checks.

The named parent `gpu0-main-q4` loaded a 262K-cap main chat on GPU0. The named `gpu1060-chat-q4` command attached worker chats to free 1060s one by one and returned a per-chat turn route. A worker answered `3+4` as `7` and remembered `7` on the next turn. After detach, GPU1 was reused by a fresh worker that answered `9+6` as `15`. Five worker contexts plus the main context generated concurrently, with all six card claims present. A sixth worker request was rejected. Stopping the parent released all claims; global `rig stop` was also checked and cleared the service and claims. The service was restarted and left with main plus one worker attached.

| 48-token simultaneous window | Main GPU0 | Worker GPU1 | GPU2 | GPU3 | GPU4 | GPU5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Decode tok/s | 83.6 | 41.6 | 39.4 | 41.0 | 40.8 | 41.1 |

Observed memory after all six were attached: GPU0 23,663 MiB; workers 2,037?2,039 MiB each. These short-turn speeds are a service smoke, not the 16K/32K/50K occupied-depth curve. That prior replay remains the depth baseline. The current service is text-only, greedy decoding, loopback-bound, and has no chat checkpoint durability. Gateway needs an adapter or rig tunnel for its returned per-chat routes. The rig mode state remains `idle` while this separate experimental service runs, but `rig status` now reports its presence and global `rig stop` cleans it up. Rig claims and `model_modes.py status` show its actual occupancy. A Manager-ready offer still needs a Gateway adapter, long-context turns, and failure-recovery validation.
