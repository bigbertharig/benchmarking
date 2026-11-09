# Qwen3.6 serialized-state delta feasibility (2026-11-09)

The proposed handoff keeps Qwen3.6-35B-A3B Q4_K_XL weights on GPU0 and each
chat's authoritative Q4_1 KV on its GTX 1060. This **file-level feasibility
probe** used saved, validated worker checkpoints from the 16K/32K/50K and
50K/100K runs. It compared full serialized states with `zstd -1 --patch-from`
and restored each patch against its exact prior checkpoint. SHA-256 of every
reconstructed state matched the original. Both workers were checked at
32K→50K and 50K→100K, so patches did not cross chat state.

| Worker and transition | Full state | Exact patch | Patch/full | Encode + decode |
| --- | ---: | ---: | ---: | ---: |
| 1, 16K→32K | 276.6 MB | 155.4 MB | 56% | 1.28 s |
| 1, 32K→50K | 387.3 MB | 160.0 MB | 41% | 1.58 s |
| 2, 32K→50K | 387.3 MB | 159.8 MB | 41% | 3.93 s |
| 1, 50K→100K | 708.5 MB | 346.1 MB | 49% | 3.06 s |
| 2, 50K→100K | 708.5 MB | 345.6 MB | 49% | 6.49 s |

The same host/codec was used for all cases; timings vary with file I/O and
cache state. A naive aligned 64 KiB block comparison reused almost no blocks
for most growth steps because serialization shifts existing content. The
content-aware patch works, but it **does not reduce GPU0 state export or GPU1
state restore**: llama.cpp's public state API still serializes and restores
the full chat. Existing live Q4_1 runs measured full GPU0 save→1060 restore
at about 1.06 s at 50K and 2.04 s at 100K; patch encoding/decoding alone
would add time to that path. Thus file-level patching is not a turn-speed
optimization on this rig. This was not an A/B measurement of total live turn
latency or a true partial GPU update.

The long run's 1 Hz GPU memory samples had a GPU0 model-only common value
of 21,319 MiB and a sampled maximum of 23,075 MiB while a temporary chat
was prepared. 378 of 686 GPU0 samples were at or above 22,000 MiB. These
samples establish a memory range, not exact per-turn workspace residency.
The 200K two-chat curve separately measured 93–102 s to prepare each worker
at that stage and kept worker decode near its solo rate. Concurrent worker
decode during GPU0 preparation remains unmeasured.

The next useful prototype needs a **format-aware partial GPU update**: copy
new full-attention KV pages to the worker and replace the small recurrent
state, while preserving existing worker pages. Measure all bytes on the x1
link, GPU0 occupancy time and high-water memory, worker correctness across
repeated turns, first token and full turn latency. Exact attention during
GPU0 preparation still needs the prior context; compare a pinned host source
with reading it back from the 1060. The current public sequence-state reader
replaces a sequence, so this requires a guarded internal extension or a
separate page-copy path. First prove one worker at 16K/32K/50K, then two;
only then try five.

Evidence: [exact patch receipt](receipt.json), the reproducible [patch probe](probe.py),
[aligned block probe](aligned_block_probe.py), [memory summary](gpu0_memory_summary.py),
and saved states/logs under `/mnt/shared/experiments/kv-matrix-20261107/`.
