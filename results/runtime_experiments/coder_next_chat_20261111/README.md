# Coder Next dedicated 1060 chat comparison — 2026-11-11

This experiment applies the Nemotron single-chat method to Qwen3-Coder-Next 80B-A3B. The 45,531,949,088-byte Q4_K_S GGUF was copied from the 4 TB share to `/data/model-hotset/qwen3-coder-next/` after the previously verified Nemotron NVMe copy was removed. The model remained on the 4 TB share. An initial Coder attempt from the share was stopped during load and has no speed result. All measured Coder rows use the NVMe file.

The b11669 llama.cpp chat probe loaded the weights once on GPU0 (3090 Ti) and GPUs1–4 (four GTX 1060 6 GB cards). Whole routed-expert tensors from 24 layers were assigned to GPUs1–4 in four six-layer groups; all other weights stayed on GPU0. GPU5 held the one independent chat. This uses the same model placement for all Coder rows. All 49 layers offloaded to GPUs; the loader reported a 166.92 MiB CPU-mapped model buffer and GPU model buffers of 22,130 MiB on GPU0 and 5,568/5,184/5,184/5,184 MiB on GPUs1–4.

The probe reserved the stated context capacity at launch, filled one history with repeated synthetic tokens to 16,384, 32,768, and 50,000 occupied positions, and timed 128 greedy output tokens after each fill. Each variant answered the short Germany prompt with `Berlin`. This is a placement and throughput probe, not a quality or long-context retrieval test. The direct fill and decode phases exclude cold model load. The 1 Hz GPU samples, full logs, scripts, source, and terminal receipts are in this directory.

## Results

| KV format | Reserved positions | GPU5 KV MiB | Peak sampled GPU5 MiB | Short tok/s | 16K tok/s | 32K tok/s | 50K tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q4_0 | 262,144 | 1,728 | 2,325 | 51.32 | 26.12 | 17.53 | 13.04 |
| F16 | 131,072 | 3,072 | 3,151 | 52.83 | 43.67 | 37.32 | 32.38 |
| Q8_0 | 262,144 | 3,264 | 3,861 | 51.81 | 36.26 | 26.73 | 20.72 |

The 262,144-capacity F16 attempt failed before generation: its 6,144 MiB KV allocation alone exceeded the available space on a 6 GB 1060. Its failed terminal receipt and log are preserved. Reducing F16's reserved capacity to 131,072 made the same occupied-depth sequence fit. Thus the F16/Q4 comparison also changes reservation size; it is a useful operational comparison, not a perfectly isolated KV-format experiment.

| KV format | Direct fill 0→16K s | 16K→32K s | 32K→50K s | Cumulative to 50K s |
| --- | ---: | ---: | ---: | ---: |
| Q4_0, 262K cap | 149.67 | 187.13 | 236.40 | 573.20 |
| F16, 128K cap | 144.45 | 171.89 | 211.46 | 527.80 |
| Q8_0, 262K cap | 150.64 | 190.00 | 241.31 | 581.95 |

## 250K-capacity F16 chat: 3090 preparation and one-chat placement

The follow-up reserved 250,000 F16 positions for **one** chat. In the usual 24x4 weight layout, GPU5 allocated 5,862 MiB of KV and had only about 124 MiB free. Direct filling on GPU5 took 530.02 seconds to reach 50K and another 797.60 seconds to reach 100K. It decoded at 32.40 and 23.22 tok/s there. We intentionally stopped this run during the 100K→150K phase; its exit 137 and incomplete 150K phase are cancellation evidence, not an OOM or a 150K result. The probe's printed `FILL_DONE tps` divides the *target depth* by the latest phase time and must not be used as an incremental fill rate.

For faster preparation, a temporary **30x5** map put routed-expert tensors from 30 layers onto all five 1060s (six layers per card). The rest of the model occupied 16,946 MiB on GPU0, the 250K F16 KV occupied 5,862 MiB there, and sampled GPU0 use was about 23,285 MiB. The loader offloaded all 49 layers to GPUs and reported only a 166.92 MiB CPU-mapped model buffer. There was no live RAM or NVMe expert spill. The model was read from NVMe at load; saved chat states were written to NVMe between layouts. All rows below are synthetic repeated-token histories and 128-token generation windows, not long-context recall or real conversation turns.

| Occupied depth | Added 50K on GPU0, s | GPU0 chat tok/s | GPU5 chat tok/s after state handoff | State file, GB | NVMe read + GPU5 restore, s |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50K | 169.75 | 44.13 | 30.77 | 1.31 | 7.98 |
| 100K | 172.67 | 47.64 | 22.40 | 2.54 | 15.59 |
| 150K | 176.02 | 46.80 | 17.94 | 3.77 | 23.26 |
| 200K | 181.31 | 42.24 | 14.83 | 5.00 | 30.91 |

The 50K state was prepared in an initial pilot, saved, and restored into the 30x5 GPU0 context to continue the 100K–200K run. Each depth was saved **before** its 128-token generation measurement. We then reloaded the standard 24x4 weights, restored each saved state into GPU5, and measured its decode. The GPU5 result at 50K is close to direct filling (30.77 versus 32.40 tok/s); at 100K it is likewise close (22.40 versus 23.22). This validates the faster preparation/handoff path without claiming it makes GPU5 decode faster. Initial model load and the model reload between placements are excluded from the phase times and remain part of cold end-to-end latency. The four GPU0 fill phases total 699.75 seconds from empty to 200K, compared with 1,327.62 seconds for direct GPU5 fill only to 100K.

For a single Coder chat, leaving it on GPU0 in the 30x5 expert layout is the faster measured choice: its 200K decode is 2.85 times the GPU5 worker rate. All six GPUs are occupied and there is no second isolated 1060 chat slot in this layout. A reusable [30x5 resident launcher](run_coder_30x5_chat3090.sh) and the [preparation/restore runner](run_coder_prep_restore.sh) are saved with their exact tensor map, probe source, logs, GPU samples, and terminal receipts. The resident `llama-server` passed `/health` and answered the short Germany prompt with `Berlin`; it reported a 250,112-position F16 context on GPU0, 5,862 MiB of GPU0 KV, and 866 MiB of GPU0 VRAM free. This is a fresh empty server chat, not a live restoration of the 200K probe state. A 250K reservation is proven; 250K **occupied** history, longer output, and deep retrieval have not been tested.

## Relation to Nemotron

The saved [Nemotron single-chat probe](../nemo_single_chat_20261109/README.md) used a 39,027,158,016-byte Q3_K_XL model, a different architecture and quant. Its 262K-capacity dedicated-1060 chat reached 32.10/27.15/22.56 tok/s with Q4_0 KV at 16K/32K/50K, and 38.05/34.40/32.50 with F16 KV. Nemotron's F16 KV allocation was only 2,048 MiB at 262K. Coder's F16 speed approaches or exceeds Nemotron's across these depths, but Coder cannot reserve 262K F16 on one 1060. Coder's Q4_0 speed declines much more steeply with occupied history.

Prior saved quality suites give Coder Next 91.46% HumanEval and 90.74% MBPP base; Nemotron scored 95.12% and 91.01%. The saved BBH flexible and DROP F1 results also favored Nemotron (88.52% vs 71.19%, and 86.54% vs 44.96%). These are previous model assessments, not tests of the KV variants here. See `results/MODEL_BENCHMARK_REFERENCE.md` for run status, sample counts, and scorer caveats.

Q8_0 keeps the full 262K reservation and improves 50K decode by 59% over full-capacity Q4_0, but its 20.72 tok/s is still 36% below the 128K-capacity F16 result. The direct fill to 50K is slightly slower than Q4_0, so Q8's measured benefit is generation from an occupied long chat. These are one-run points and small 128-token decode windows.

The practical lesson is that making all weights GPU-resident removes the large live NVMe expert spill seen in the 125B Strata work, but chat-state size and the 1060 attention path then set the useful capacity and decode rate. Coder's 24x4 layout leaves only one empty 1060, while the four weight cards each hold about 5.2–5.6 GiB. Two isolated 1060 chats would require a different quant or weight placement. Next probes: compare Q4_0 at 128K cap to isolate the reservation effect; profile Q8 versus F16 attention and conversion at 50K; then test a second chat at a smaller capacity or a lower weight quant. Use longer generation and a small correctness set before treating a 128-token rate as a serving estimate.

No Manager recipe was changed. After this sequence, the Coder server should be left loaded in the existing 24x4 experimental placement for follow-up work.
