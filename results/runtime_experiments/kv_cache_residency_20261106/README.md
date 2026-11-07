# Per-chat 1060 cache worker receipts

See [`KV_PER_CHAT_GPU_PLACEMENT_2026-11-06.md`](../../../KV_PER_CHAT_GPU_PLACEMENT_2026-11-06.md)
for the interpretation, limitations, and next runtime gate.

`cache_*_workspace_*.json` are simultaneous five-GPU CUDA allocation
results. `attention_*_all_return.json` verify five-worker attention with the
same marker on every lane. `attention_250000_distinct.json` is the final
isolation check with a different marker on each lane; the matching `_raw.txt`
files preserve full container output. `attention_250k.json` and the earlier
`attention_*_raw.txt` files are the initial version that returned only one
of five results to GPU0. The compiled binary is
`kv_attention_worker_probe`; source is under `scripts/active/`.

The active 27B route was not unloaded, and every 1060 returned to 4 MiB
reported use after the probes. The result is a synthetic placement and
transfer check, not full-model inference.
