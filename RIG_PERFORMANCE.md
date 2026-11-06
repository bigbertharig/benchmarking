# Rig performance

How fast the rig runs models, why, and how to measure it. This is the owner of speed, context-capacity,
split and PCIe knowledge: what is known (with the record behind it), what is still open, and which tool
answers which question. The numbers themselves are in the generated
[results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md) (every record in `results/runtime_experiments/`);
model quality scores are in [results/MODEL_BENCHMARK_REFERENCE.md](results/MODEL_BENCHMARK_REFERENCE.md).
Addresses and host details: llm_orchestration `shared/workspace/local/inventory.md`; the rig hardware layer
(guard, power caps, loads): llm_orchestration `shared/scripts/rig/README.md`.

## Qwen3.6 35B quantization fit check, 2026-11-04

The Strata-compatible UD-Q4_K_XL and existing UD-Q4_K_M completed matching llama.cpp benchmark campaigns. At 16K context, XL decoded 151.91 tok/s versus 155.03 for M. At 262K on all six cards, both passed planted-code recall at 10/25/50/75/90%; at 90%, XL decoded 11.69 tok/s versus 11.71 for M and prefilling was 198.13 versus 183.76 tok/s. The manager's default maximum on GPU 0 alone is 201,984 for XL versus 243,456 for M. XL did load and finish a short probe at 230,144 with a 64 MiB explicit planning margin, but the normal margin did not fit it there. XL is active and M archived after the operator accepted the one-card maximum tradeoff. A managed 262K load on the 3090 plus one 1060 passed with the default 512 MiB margin and a 64.38 tok/s short decode probe. Final-answer recall then passed at 10% and 90% depth on that pair; at 90% it decoded 18.83 tok/s versus 11.69 tok/s on all six cards. The two-card pair is the fewest validated cards for this model's trained ceiling. See [STRATA_MEMORY_TEST_PLAN.md](STRATA_MEMORY_TEST_PLAN.md) for paired quality scores, method, and receipt names.

## Minimum-useful load checks and Nemotron memory placement, 2026-11-04

The provisional workload policy targets 8K for small models, 16K for about 30B, and 32K for 70B+. These are useful-context targets, separate from the registry's 4K/8K planning floor and from the GGUF trained ceiling. Managed load plus short-probe checks passed as follows; they do **not** establish long-context recall for these four placements.

| Model | Context | Cards | Short decode | Receipt |
|---|---:|---|---:|---|
| Nemotron 3.5 Bolt 74B-A9B | 32K | 3090 + three 1060s (0-3) | 23.88 tok/s | `results/runtime_experiments/nemotron_3_5_bolt_74b_a9b_min32k_g0-1-2-3_20261104.json` |
| Qwen3-Coder-Next 80B-A3B | 32K | all six (0-5) | 37.79 tok/s | `results/runtime_experiments/qwen3_coder_next_80b_min32k_g0-1-2-3-4-5_20261104.json` |
| Gemma 4 12B | 8K | two 1060s (1,3) | 13.03 tok/s | `results/runtime_experiments/gemma_4_12b_min8k_g1-3_20261104.json` |
| Devstral Small 2 24B | 16K | 3090 (0) | 52.63 tok/s | `results/runtime_experiments/devstral_small_24b_min16k_g0_20261104.json` |

The manager planned Nemotron 32K on four cards with the normal margin. For Qwen Coder Next 80B, five cards were refused at 32K because its layers/output could not divide within per-card memory; six cards fit and loaded. Neither result changes the model's default benchmark profile yet.

For a **matched Nemotron 32K speed comparison**, the same GGUF, llama-runtime:b11669, 1,542-token prompt, 128-token output, batch 64, 4 CPU threads, and two requests per placement were used. The GPU legs offloaded all 89 layers; the 3090 + host-RAM leg offloaded 48/89. The RAM leg left 12,723 MiB host `MemAvailable` after load, above the 4 GiB planning guard. A 3090 + two-1060 placement does not fit this model at 32K with normal margins, so the sweep begins at three 1060s.

| Placement | Warm prompt processing | Warm decode | End-to-end, second request |
|---|---:|---:|---:|
| 3090 + three 1060s, all layers on GPUs | 233.18 tok/s | **24.63 tok/s** | 12.16 s |
| 3090 + four 1060s, all layers on GPUs | 209.27 tok/s | **22.52 tok/s** | 13.44 s |
| 3090 + five 1060s, all layers on GPUs | 183.33 tok/s | **20.43 tok/s** | 15.08 s |
| 3090 + host RAM, 48/89 layers on GPU | 72.21 tok/s | 6.26 tok/s | 41.88 s |

Each extra 1060 slowed this GPU split, but even all five 1060s decoded **3.26x faster** than the tested 3090 + CPU/RAM layer offload. There is no speed crossover within the available five 1060s for this model, context, and loader configuration. The GPU split with the fewest cards that fits was fastest. This does **not** establish that host RAM is always slower: a different model, a different CPU-layer count, or Strata's expert-cache placement can have a different curve. These are two requests per placement; they measure short 1.5K prompt/decode behavior at a *loaded* 32K context, not long-context performance. Load times were about 93-101 s, but run order and file-cache warmth differ, so they are not a controlled load-time comparison. The runner recorded host available memory and swap, but not physical SSD I/O during decode. Receipts: `results/ram_offload_comparison_nemotron32k_{gpu4,gpu0ram}_20261104/terminal.json` and `results/ram_offload_comparison_nemotron32k_{gpu5,gpu6}_20261106/terminal.json`, with llama-server logs alongside.

## Placement preference from current tests, 2026-11-04

The manager's placement question is whether the **desired model fits at
the desired context** on the cards available now. If the 3090 is free,
try it alone, then add the fewest 1060s required for a full-GPU fit.
If the 3090 is occupied, try one 1060, then add the fewest 1060s
required. A smaller model stops at the first fitting card in either
branch. If no full-GPU placement fits, consider host-RAM offload and
then compatible Strata NVMe-backed placement. Those latter paths are
not yet automatic in the GPU-only manager planner.

This is a measured preference, not a universal throughput ranking across
different models, contexts or engines. The Nemotron GPU/RAM comparison
above supports the middle ordering; storage tiers need separate warm/cold
I/O measurements. Choose the fewest cards that meet the requested context
rather than filling every free card. The gateway/rig manager owns model
loads; a harness consumes the ready route and its capacity.

## Host RAM planning limit, 2026-11-03

The rig has 31,476,852 KiB physical RAM (about 30.0 GiB, marketed as 32 GB). Its `earlyoom -m 10` guard acts when available memory falls to roughly 10% of total, so installed RAM is not an allocation budget. In an otherwise idle rig, the managed, GPU-free `probe_host_ram_budget.py` touched and retained anonymous pages at the following targets; swap-free space did not change:

| Allocation target | Actual allocation | Lowest `MemAvailable` | Result |
|---|---:|---:|---|
| **26 GB decimal** | 24.21 GiB | **4.38 GiB** | Reached target, then released cleanly |
| 26 GiB (27.92 GB decimal) | 26.00 GiB | 2.56 GiB | Briefly reached target, but crossed the 10% guard threshold; unsafe for a sustained load |

**Plan at most 26 GB decimal (about 24.2 GiB) of new host-resident data on an idle rig**, then require at least **4 GiB `MemAvailable` after load and during work**, with no material swap growth. Leave more headroom when other services or jobs are active. This is a planning ceiling and a live admission check, not a promise that every model with a 26 GB file will fit: runtime buffers, pinned host allocations, KV state and file mappings also consume memory. A 25 GiB or 26 GiB allocation is a different, tighter target and should not be described as “25/26 GB” without units. Receipts: `results/runtime_experiments/host_ram_budget_26gb_decimal_20261103/` and `host_ram_budget_26g_20261103/`.

The nominal capacity arithmetic is 54 GB across the 3090 Ti and five 1060s plus a 26 GB host-RAM planning budget, or **80 GB across distinct tiers**. It is not a single addressable 80 GB VRAM pool; placement and per-device buffers decide whether a model fits. Qwen3.8 Q2_0's 26.8 GiB ngram lookup alone exceeds the safe host-resident budget, so the tested lazy NVMe-backed placement remains necessary for that file.

## Strata GPU/RAM/SATA/NVMe placement, 2026-11-03

On the 3090 Ti alone, the verified 66.4 GB Qwen3.8 Flash-Next Q2_0 pack loaded in both llama.cpp and Strata at 8K context. The basic llama.cpp partial-offload smoke put 24/49 layers on GPU 0, used 18,111 MiB VRAM, and decoded two 128-token outputs at 8.36/8.46 tok/s. It did not measure physical SSD reads. Strata 0.2.10/engine 0.1.56 used about 23,500 MiB VRAM in every setting below, with MTP/drafting off and one request slot. These are exploratory placements and different API request paths; the llama.cpp and Strata speeds are not a controlled engine A/B.

| Strata expert RAM | Available host RAM after load | Cold 128-token request / NVMe read | Warm 512-token request / NVMe read |
|---|---:|---:|---:|
| Default: 16.31 GiB pinned | 8.7 GiB | 2.92 s / 24 MB | 5.00 s / 23 MB |
| 12 GiB | 12.9 GiB | 6.21 s / 1.62 GB | 5.18 s / 68 MB |
| 8 GiB | 17.0 GiB | 11.89 s / 4.08 GB | 5.72 s / 248 MB |
| 4 GiB | 21.2 GiB | 17.11 s / 6.48 GB | 5.86 s / 336 MB |
| 0.1 GiB | 25.1 GiB | 22.29 s / 8.73 GB | 6.85 s / 879 MB |

The engine logged zero expert file reads during default requests and increasing file reads as resident RAM fell. A literal 0 GiB budget was rejected (`N > 0`); 0.1 GiB is the near-mapped test. The first Strata launch took 325 s because it built an additional ~34 GB expert pack on NVMe. Warm requests reused 1,478 prompt tokens and benefited from GPU and OS caches, so the large cold-read penalty is the more useful warning for varied or concurrent work. The 1060s hosted a separate GPT-OSS service, though request NVMe block-counter changes matched Strata engine-process I/O. Inputs, settings, failed case and raw receipts: [STRATA_MEMORY_TEST_PLAN.md](STRATA_MEMORY_TEST_PLAN.md), `results/runtime_experiments/strata_q38_q2_*_20261103/`.

At 262,144 configured context, Strata on the 3090 alone loaded with an 8 GiB resident expert budget and 23,527 MiB GPU use. The existing marker-depth test recalled the code in the final answer at 26,943 and 251,864 prompt tokens. Wall times were 40.01 and 115.47 s; physical NVMe reads were 12.60 and 0.54 GB, respectively. The second probe benefited from warmed file cache, and the nominal 90% filler expanded to about 96% of the context, so these numbers do not isolate a context-size effect. Receipts: `results/runtime_experiments/strata_q38_ctx256k_g0_20261103/` and `strata_q38_depth10_90_g0_20261103/`.

With the same GGUF at 8K in llama.cpp, placing all 49 main layers on the 3090 plus three, four, or five 1060s decoded 128 tokens at 23.14/23.33, 20.81/21.41, and 19.77/19.68 tok/s, respectively. More cards cost speed here despite the extra VRAM. The 27,465.95 MiB ngram lookup remained CPU mapped from the NVMe-backed GGUF in every split, though warm requests had negligible physical NVMe reads. These are short-prompt llama.cpp comparisons; they should not be ranked directly against Strata's chat timings. Receipts: `results/runtime_experiments/q38_llama_four_8k_20261103/`, `q38_llama_five_8k_20261103/`, and `q38_llama_all_8k_20261103/`.

At 256K context with q8_0 KV, four GPUs could not allocate the CUDA compute buffers. Five GPUs loaded, and the 10% depth probe recalled the marker at 26,966 prompt tokens: 282.8 s wall time, 96.86 prompt tok/s, and 16.08 generation tok/s over 71 output tokens. Its 90% probe was stopped after the completed 10% result to leave time for the SATA comparison; no five-GPU near-full-context speed or recall is established. Receipts: `results/runtime_experiments/q38_llama_four_256k_20261103/terminal.json` and `q38_llama_five_256k_20261103/terminal.json`.

For a separate 8K **resident ngram** fit test, llama.cpp used `--lazy-mode off --override-tensor per_layer_token_embd=CPU --load-mode none` with all 49 main layers on GPU 0–4. Its load log allocated a 27,465.95 MiB CPU model buffer for the lookup rather than a CPU-mapped, lazy-read buffer. With a 27 GiB no-swap Docker memory cap, the container was OOM-killed before ready. At a 28 GiB no-swap cap, the model briefly reached ready, but the rig's existing `earlyoom` guard sent SIGTERM when host available memory fell to its 10% threshold; Docker recorded a 27.8 GB memory peak and no completed inference. This rig's ~30 GiB physical RAM therefore cannot sustain the whole lookup resident with safe OS/runtime headroom. The normal lazy NVMe-backed placement remains the working configuration. Receipts: `results/runtime_experiments/q38_llama_ngram_ram_{27g,28g}_20261103/`; the 28 GiB directory includes `earlyoom_utc.log`.

The matched Strata expert-file storage test kept the Qwen3.8 GGUF and ngram lookup on NVMe, while placing only the verified 33.97 GB `experts.bin` on NVMe or the rig's SATA SSD. The same 3090, 8K context, int8 KV, one slot, prompts and output limits were used. Each run requested targeted eviction of that expert file's cached pages before launch; the physical block counters show which drive supplied request reads.

| Expert RAM | Expert file | Cold 128-token request / physical read | Warm 128-token request | 512-token request |
|---|---|---:|---:|---:|
| 8 GiB | NVMe | 11.64 s / 4.03 GB NVMe | 1.39 s | 6.21 s |
| 8 GiB | SATA SSD | 15.25 s / 4.04 GB SATA | 1.46 s | 5.47 s |
| 0.1 GiB | NVMe | 22.16 s / 8.71 GB NVMe | 1.80 s | 7.23 s |
| 0.1 GiB | SATA SSD | 30.31 s / 8.63 GB SATA | 1.93 s | 6.53 s |

The cold SATA requests were 31% and 37% slower than their NVMe partners. Warm timings do not preserve that order because GPU and OS caches absorb many expert reads. These are one-run measurements on this particular SATA drive, not general SSD/NVMe throughput claims. The SATA copy passed SHA-256 comparison, was removed after the tests, and root filesystem free space returned to 39 GB. Receipts: `results/runtime_experiments/strata_q38_{nvme,sata}{8,0p1}_matched_20261103/` and `strata_q38_sata_pack_copy_20261103.json`.

## The cards and links

The live list is the rig's scan, not this file: `ssh rig rig status` (cards, and what moved since the last boot)
and rig-local `brain/hw/gpu_layout.json` (index, UUID, board, PCI bus per card, recorded at each boot). A card's
index follows PCI bus order and changes whenever cards move, so a record names a card by UUID and link, not by
index alone.

The cards (by UUID prefix), with the 2026-10-25 layout and the x16 speed updated after the BIOS change:

| Card | Board (power default), UUID | Cap (rig-power.service) | Index, root port, link |
|---|---|---|---|
| RTX 3090 Ti 24 GB | `409c0fe8` | 350 W | 0, CPU x16, gen 3 x16 |
| GTX 1060 6 GB | EVGA (120 W), `fd82a1a6` (GPU 1 before 2026-10-25) | 100 W | 1, 1b.5, gen 2 x1 |
| GTX 1060 6 GB | EVGA (120 W), `d24dca6a` (GPU 3 before 2026-10-25) | 100 W | 2, 1b.7, gen 2 x1 |
| GTX 1060 6 GB | ASUS Dual (120 W), `ac5b4fea` | 100 W | 3, 1c.7, gen 2 x1 |
| GTX 1060 6 GB | ASUS overclocked (156 W), `6073db94` | 100 W | 4, 1d.0, gen 2 x1 |
| GTX 1060 6 GB | ASUS overclocked (156 W), `8d1110ae` | 100 W | 5, 1d.3, gen 2 x1 |

The NVMe (SK hynix PC300) is on root port 1b.0 at gen 2 x1.

**Board: ASUS B250 MINING EXPERT (BIOS 1001), 1 x16 + 18 x1 slots.** Most x1 slots go straight to a chipset
root port and train at gen 2. Slots C17 and C18 do not: they hang off an ASMedia ASM1187e 7-port x1 switch
(04:00.0, downstream ports 05:01-05:07) whose one uplink to root port 1b.6 trains at gen 1 on every boot
(`LnkCtl2` target 2.5 GT/s on 1b.6, 5 GT/s on every other root port; both ends support 5 GT/s), so any card in
C17 or C18 runs gen 1 x1, whatever the riser, cable or card. Seen 2026-10-25 with the old GPU 3 EVGA, the 3090
and the ASUS Dual on switch ports 05:02 and 05:04; the BIOS gen 2 option does not change it. Keep cards out of
C17/C18; with more cards than direct slots, the card that runs alone least often goes there. Chipset root
ports renumber when slots fill (Intel root port swapping), so a moved card or the NVMe can land on a different
port number; read `lspci -tv` for which cards sit under 1b.6.

`nvidia-smi --query-gpu=index,uuid,pci.bus_id,pci.sub_device_id,pcie.link.gen.max,pcie.link.width.current --format=csv`
shows the links (vendor in the sub device id: 3842 EVGA, 1043 ASUS). The PCH PCIe Speed setting stays
at gen 2 for the x1 risers, where gen 3 logged link replays. The separate PEG Port Configuration >
PCIEX16_1 Link Speed setting is now gen 3 for the CPU x16 slot. At boot the x16 root port reported
`LnkCap` and `LnkCtl2` at 8 GT/s; a short qwen3.5:4b run sampled its negotiated speed 271 times
and observed gen 3 under work. The run completed with 174.02 decode tok/s at ctx 4096 and no AER or Xid
messages; this is a link check, not a matched gen 2/gen 3 speed comparison. Its record is
`results/runtime_experiments/qwen3_5_4b_capacity_g0_ctx4096_gen3-x16_20261025.json`. All five
1060s remained at gen 2 x1, and the 350 W / 100 W power caps held. The rig config's brain card,
`brain` placements and pinned `gpus: [0]` assume the
3090 is GPU 0; the rig itself works with whatever cards the scan finds (llm_orchestration
`shared/scripts/rig/README.md`, "The cards are whatever the scan finds").

## Runtime upgrade smoke baseline, 2026-10-25

The image-promotion smoke list now includes six-card
`nemotron-3.5-bolt:74b-a9b` and split `mellum2.1:12b-a2.5b`,
even though neither is in an active role or gateway offer. On the current
`llama-runtime:b11669`, both passed the clean 555 litmus and completions
request. Nemotron fully offloaded 89/89 layers across GPUs 0-5 from NVMe
and loaded in 201.8 s. Mellum loaded on GPUs 1,3 from the shared archive
in 98.6 s and decoded 128 tokens at 49.62 tok/s. Both were unloaded;
the rig returned to idle. PCIe replay counts stayed at 0 on GPUs 0-3 and 5,
and 15 on GPU4; no AER, Xid, NVRM error, or fallen-off-bus kernel message
appeared during the test. The Mellum throughput is a matched baseline
for any new candidate image, with a 70% minimum speed gate in
`scripts/llama_runtime/smoke_runtime.py`. Receipt:
`/mnt/shared/logs/runtime_upgrades/b11669_20261025_192107.json`.
The official release lookup from the rig failed DNS resolution, so no
new candidate image was built or promoted.

## GPU4 link control and manager speed, 2026-10-25

GPU4 (ASUS 1060, bus 11:00.0, root port 00:1d.2) was the only card with PCIe replays
after the six-card runs. A matched `ministral-3:3b` solo load and short response added
one replay on GPU4 (14 to 15) and zero on GPU3. GPU4 loaded in 25.0 s and decoded at
38.44 tok/s; GPU3 loaded in 18.4 s and decoded at 39.85 tok/s. Neither run logged
AER, Xid, NVRM, or fallen-off-bus errors. This isolates the replay to GPU4's path
under this small workload; a card versus riser or cable diagnosis requires a physical
swap or inspection. Leave the x1 Gen2 BIOS setting and power caps in place. Evidence:
`results/runtime_experiments/gpu4_link_control_20261025.txt` and the two
`ministral_3_3b_gpu{4,3}_pcie_control_20261025.json` records.

For manager placement, matched `ministral-3:8b` runs at 16,384 context and batch 64
measured GPU0 at 25.2 s load, 2,616.16 tok/s prefill and 121.82 tok/s decode; GPUs
1,3 at 34.9 s, 474.7 tok/s and 20.24 tok/s. The 3090 was 5.51 times faster at
prefill and 6.02 times faster at decode. The manager now uses comparable measurements
for available fitting card sets; the working worker context is 8,192. Evidence:
`results/runtime_experiments/ministral_3_8b_capacity_g0_ctx16384_b64_20261025.json`
and the prior matched two-1060 capacity record.

## Dense 70B versus 74B MoE on NVMe, 2026-10-25

Llama-3.3-70B-Instruct-Q4_K_M (dense; 42.52 GB/39.6 GiB) was copied
from the archive to the rig NVMe hotset with a full byte-for-byte
comparison before atomic promotion. The existing Nemotron-3.5-Bolt
74B-A9B-UD-Q3_K_XL (74B total, 9B active MoE; 39.03 GB/36.3 GiB)
was already local. Both managed runs used GPUs 0-5, 2,048 context,
micro-batch 32, a cleared page cache, and the unchanged 350/100 W
power caps. The live container path confirmed each GGUF under
`/data/model-hotset`. The manager chose each model's layer split.

| Model | Load to ready | 512-token decode | Probe wall time | GPU4 replay delta |
|---|---:|---:|---:|---:|
| Llama 3.3 70B dense | 226.1 s (3m46s) | 4.57 tok/s | 113.2 s | +7 |
| Nemotron 3.5 Bolt 74B-A9B MoE | 203.6 s (3m24s) | 19.16 tok/s | 30.5 s | +1 |

Nemotron's decode rate was 4.19 times Llama's in this one matched
placement/context/batch test; its load was 22.5 s faster. The GGUF
sizes and quantizations differ, so this is a comparison of these
two deployable artifacts, not an isolated architecture experiment.
Their prompt token counts also differ (86 versus 68), so prefill and
time-to-first-token are not directly matched. The dense model's
128K-context fit was refused by the manager because full-attention KV
needs more memory; Nemotron's prior 226,816-context run cannot be
used as the same-context dense comparison.

Both runs exited 0 and unloaded. GPU4 gained 7 and then 1 PCIe
replays; the other five counters did not change, and the kernel
reported no AER, Xid, NVRM error, or fallen-off-bus message. This
continues the GPU4 link/riser concern noted below. Llama remains
`archived` in the model catalog; NVMe staging does not promote it.
The older 19m44s shared-storage first load used an earlier runtime
and is historical context, not a controlled NVMe/NFS speedup ratio.
Evidence: `results/runtime_experiments/llama3_3_70b_nvme_stage_20261025.txt`,
`dense_moe_cold_nvme_compare_20261025.txt`, and the two
`*_capacity_g0-1-2-3-4-5_nvme_cold_ctx2048_b32_20261025.json` records.

## Six-card 74B NVMe cold load, 2026-10-25

Nemotron-3.5-Bolt 74B-A9B is a 74B-total, 9B-active MoE, in a 37 GiB
Q3_K_XL GGUF on the rig NVMe. Two managed `capacity_run.py --skip-depth`
runs at 226,816 context used GPU 0 (3090 Ti) and GPUs 1-5 (1060s).
The manager chose split `47,8,12,9,7,6`. The page cache was cleared
before each run and the live container's `--model` path was verified at
`/data/model-hotset/nemotron-3.5-bolt-74b-a9b/`. Power caps remained
350 W on GPU 0 and 100 W on each 1060.

| Cold run | Load to ready | Short decode | GPU4 PCIe replay delta |
|---|---:|---:|---:|
| First | 206.3 s (3m26s) | 20.37 tok/s | +4 |
| Repeat | 206.2 s (3m26s) | 20.58 tok/s | +2 |

Both runs exited 0 and unloaded; the other five cards' replay counts
did not change. Neither run logged a kernel AER, Xid, NVRM error, or
fallen-off-bus message. GPU4's recurring replay increase warrants
checking its link/riser before calling this a clean hardware pass; the
x1 BIOS settings were left unchanged. The earlier six-card result was
185.6 s at the same context, but its cache state was not recorded, so
it is not a controlled NVMe-cold comparison. These figures describe
this quantized MoE, not a dense 70B. Receipts and JSON records:
`results/runtime_experiments/nemotron_3_5_bolt_74b_a9b_nvme_cold_20261025.txt`
and `nemotron_3_5_bolt_74b_a9b_nvme_cold_repeat_20261025.txt`,
with the corresponding `*_capacity_g0-1-2-3-4-5_nvme_cold*_20261025.json`.

## NVMe cold loads for the assigned models, 2026-10-25

One managed `capacity_run.py --skip-depth` load per current role, at its
`default` profile context and batch, after clearing the rig's page cache.
The selected GPU set matches that role's lane; the manager calculated the
layer split. Each live container's `--model` argument was observed under
`/data/model-hotset`. Load seconds measure the manager's request through
**model ready**, including container and GPU setup, not just GGUF read time.
The short probe also confirms the model answered; its decode rate is shown
for context, not used to rank these different models.

| Role | Model | Context | GPUs | Cold load | Short decode |
|---|---|---:|---|---:|---:|
| `single_1060_compact` | ministral-3:3b | 16,384 | 1 | 25.1 s | 38.47 tok/s |
| `text_extraction` | gemma-4:e2b-q8 | 4,096 | 1 | 34.9 s | 31.51 tok/s |
| `single_1060_code` | qwen2.5-coder:7b | 16,384 | 1 | 34.9 s | 22.44 tok/s |
| `single_1060` | ornith-1.5:9b | 8,192 | 1 | 41.5 s | 18.52 tok/s |
| `split_speed` | ministral-3:8b | 16,384 | 1,3 | 34.9 s | 20.24 tok/s |
| `split_quality` | ministral-3:14b | 8,192 | 1,3 | 51.4 s | 13.59 tok/s |
| `safe_tool_use` | phi-4:14b | 8,192 | 1,3 | 58.0 s | 12.33 tok/s |
| `brain_code` | qwen3-coder:30b-a3b | 16,384 | 0 | 58.0 s | 193.81 tok/s |
| `brain` | qwen3.6:27b | 16,384 | 0 | 54.8 s | 44.41 tok/s |

These are **single samples**, not averages. All nine exited 0 and unloaded.
All six cards' replay and rollover counters remained 0/0 across the runs,
with no AER, Xid, NVRM error, or fallen-off-bus kernel message. Receipts:
`results/runtime_experiments/nvme_role_cold_loads_20261025.txt` (first
model) and `nvme_role_cold_loads_remaining_20261025.txt` (other eight);
the nine `*_role_*_nvme_ctx*_20261025.json` records supply exact model,
context, card identity, buffer measurements, and decode.

A fit check for `ministral-3:8b` at 16,384 refused one 1060 but fit two.
Its role says `2x1060` while the older registry `schedule.placement`
still says `single_gpu`. The manager did not use that label; it calculated
a 18/16-layer split on GPUs 1 and 3 and the model loaded. The label remains
a legacy orchestration/catalog inconsistency to remove when that placement
metadata is moved out of the model requirements.

## CPU x16 Gen 2 / Gen 3 solo tests, 2026-10-25

The 3090 Ti stayed on GPU 0, CPU x16, with its 350 W cap; the five 1060s stayed at
Gen 2 x1 with 100 W caps. We used the existing managed `capacity_run.py` short probe
at fixed context, then changed only the CPU root port 00:01.0 target between Gen 2
and Gen 3 with `setpci` and retrained the link. Each cold pass dropped the rig's
Linux page cache. The manager's load spec contains the logical archive path,
but the rig's `resolve_hotset_gguf` selects a local copy under
`/data/model-hotset` when present. The 35B GGUF was **already on the rig NVMe**
for these runs; the 4B GGUF was absent then, so its first series used the Pi's
NFS archive. Order was Gen 3, Gen 2, Gen 2, Gen 3. The BIOS setting stayed
Gen 3 and the root target was restored to Gen 3 afterward. The endpoint
01:00.0 target remained Gen 3 throughout the temporary downshifts, so this
is **not equivalent to a native BIOS Gen 2 boot**.

| Solo model and fixed context | Temporary Gen 2 cold loads | Gen 3 cold loads | Short chat decode, temporary Gen 2 / Gen 3 |
|---|---:|---:|---:|
| qwen3.6:35b-a3b, 131,072, batch 128 | 94.6 / 88.6 s (mean 91.6) | 84.5 / 84.6 s (mean 84.6; 7.7% less) | 136.5 / 133.6 versus 147.1 / 146.8 tok/s |
| qwen3.5:4b, 32,768, batch 64 | 44.9 / 44.9 s (mean 44.9) | 48.0 / 38.2 s (mean 43.1; variable) | 108.2 / 108.0 versus 173.8 / 174.1 tok/s |

The 35B NVMe cold load shows a modest Gen 3 gain in this two-pass software
comparison. The 4B NFS load times vary enough that there is no clear gain.
The NVMe result cleared the rig's page cache, which covers its local model.
The NFS server cache was not cleared for the original 4B series. These
timings describe **model load to ready**, not prefill or time to first token
for a long prompt.

After staging the 4B GGUF on `/data/model-hotset`, a second four-pass series
used the same contexts, batch, order, cache clearing, and error checks. A
live `docker inspect` showed the container bound
`/data/model-hotset/qwen3.5-4b` and passed that GGUF to `llama-server`:

| 4B source | Temporary Gen 2 cold loads | Gen 3 cold loads | Short decode, temporary Gen 2 / Gen 3 |
|---|---:|---:|---:|
| Original NFS fallback | 44.9 / 44.9 s | 48.0 / 38.2 s | 108.2 / 108.0 versus 173.8 / 174.1 tok/s |
| Rig NVMe hotset | 25.0 / 21.7 s | 21.7 / 21.6 s | 108.0 / 108.8 versus 174.0 / 173.3 tok/s |

For the relevant production Gen 3 setting, putting this 2.74 GB model on
NVMe reduced measured cold load from 38-48 seconds to about 22 seconds.
Decode stayed the same for each link setting. The temporary Gen 2 versus
Gen 3 decode comparison retains the caveat below. The NVMe receipt is
`results/runtime_experiments/pcie_x16_gen2_gen3_nvme_qwen4b_20261025.txt`
with individual `x16-gen{2,3}-nvme-cold{1,2}` JSON records. All four
passes exited 0, all six replay counters stayed 0/0, and the kernel error
check was empty.

**Do not use the temporary Gen 2 decode values as a BIOS Gen 2 baseline.**
A prior native BIOS Gen 2 x16 run of the same 4B model at 32,768 decoded at
172.0 tok/s; its original baseline was 172.6. A prior BIOS Gen 2 35B batch
128 short probe decoded at 152.3 tok/s. Gen 3 4B short decode here was about
174 tok/s, only about 1% above the prior native Gen 2 result. The temporary
downshift reproducibly lowered 4B decode to 106-108 tok/s in a focused repeat.
Live sampling confirmed Gen 2 **x16** during that run and Gen 3 **x16** after
restoration, with the same observed maximum SM (2070 MHz) and memory
(10,501 MHz) clocks and P0/P2 states. The temporary Gen 2 run drew less power
(roughly 275-289 W versus 333-357 W). Why a root-port-only downshift behaves
differently from native Gen 2 is unresolved; a BIOS-to-BIOS matched run would
be needed to attribute decode changes to generation.

The previous Gen testing's error checks were reused: before and after each
cold pass, all six cards' `Replays Since Reset` and `Replay Number Rollovers`
remained 0/0; no AER, Xid, NVRM error, or fallen-off-bus message appeared in
the kernel log for either cold series. Every managed run exited 0. Receipts:
`results/runtime_experiments/pcie_x16_gen2_gen3_cold_20261025.txt`,
`pcie_x16_gen2_gen3_cold_qwen4b_20261025.txt`, and
`pcie_x16_live_clocks_20261025.txt`; individual JSON records with
`x16-gen{2,3}-cold{1,2}` and `-clockdiag` in their names. The earlier
warm-cache A/B receipt is `pcie_x16_gen2_gen3_ab_20261025.txt`; its load
times are not cold-load evidence.

## What is known

| Finding | Evidence |
|---|---|
| **The 1060 is the slow part, not the bus.** The same model alone on the 3090 decodes 6.2x faster than alone on a 1060 and prefills 8x faster (12x deep in the context). | qwen3.5:4b at 32K, capacity runs 2026-10-24; nex-n2.5:mini 6.5x and gemma-4:26b-a4b 6.3x in earlier splits |
| **Splitting across 1060s costs decode nothing measurable.** 0 to 4 hops stay within card-to-card variation; the links carry 6-58 MB/s per card against about 500 MB/s for gen 2 x1. A layer split runs the cards one after another, so each card's VRAM bandwidth sets the speed. | split_sweep gen 2 / gen 3, qwen2.5-coder:7b, 2026-10-19; qwen3.5:4b on 1, 2 and 5 1060s, 2026-10-24 |
| **Fewest cards wins.** For a given model and context every added card was slower; a split buys capacity, not speed. | qwen3.6:35b-a3b at 131K: 152 / 65 / 43 / 40 tok/s decode on 1 / 2 / 4 / 6 cards; at 262K, 2 cards beat 4 and 6 |
| **A 3090 + 1060 split loses more decode than the 1060's share of layers.** One of 33 layers on a 1060 took decode from 173 to 79 tok/s while prefill did not move. Suspected: the output layer goes on the last card in the order, the 1060, and it runs for every generated token but once per prompt. Not yet tested. | qwen3.5:4b, 2026-10-24 |
| **Speed falls as the context fills.** From 10% to 90% of the context, decode about halves and prefill drops a quarter to two thirds (more on more cards). At 217K tokens the first token took 23 min on six cards. | capacity depth probes, 2026-10-24 |
| **Micro-batch is the prefill lever, and costs no decode.** Batch 128 (the ~30B profiles) to 512 at 32K: qwen3.6:35b-a3b prefill 2.3x on the 3090 (1669 to 3881 tok/s at 3K tokens) and 2.1-3.2x on five 1060s (322 to 689; 258 to 817 at 29K); gemma-4:31b (dense) 1.2-1.3x on the 3090. Decode moved under 1%. The cost is the compute buffer per card: 86 to 152 MiB on the 3090, 123 to 299 MiB on a 1060, for qwen3.6 at 32K. An earlier split_sweep (`-b 2048 -ub 512`) gave 2.4x on five 1060s. Capacity prefill numbers describe the profile's batch. | `*_capacity_*_ctx32768_b{64,128,256,512}_20261025.json`; split_sweep 2026-10-19 |
| **PCIe gen 3 helps loads only.** A cold five-card load went from 132 to 90 s; inference did not change, and the risers logged replays, so the BIOS stays at gen 2. | split_sweep and pcie_split_test, 2026-10-19 |
| **An x1 link costs a fixed ~3 ms per generated token on gen 2 and ~9 ms on gen 1, on any card.** qwen3.5:4b alone at 32K: the 3090 goes from 172.6 tok/s on x16 to 114.3 on gen 2 x1 (5.79 to 8.75 ms per token, +3.0 ms); the same EVGA 1060 runs 30.5 on x16, 28.0 on gen 2 x1 (the other EVGA, matched on two different slots within 0.04 tok/s) and 24.0 on gen 1 x1 behind the C17/C18 switch (32.8 / 35.7 / 41.7 ms: +2.9 and +8.9 ms). Fits the per-token copy of the full output scores to the CPU (about 1 MB for a 248K vocabulary), sized larger than the 2 ms estimate. Prefill also drops on x1, which the copy does not explain: 3090 at 3K tokens 3976 to 2372 tok/s (-40%), the 1060 523 to 488 (-7%); loads take longer (3090 43 to 108 s). So a large-vocabulary model on any x1 card pays a fixed cost per token, and so does a split whose last card is on x1. The 24 vs 28 tok/s gap between the two EVGA 1060s was the gen 1 slot, not the card (it was repasted before the baseline) or the riser. | qwen3.5:4b capacity runs 2026-10-25: `*_g1_*`, `*_g3_*`, `*_3090-x1_*`, `*_evga3-x16_*`, `*_evga1-x1_*` |
| **Context capacity is set by the trained context or by card memory, and the manager's old estimate set it lower.** The ~30B hybrid MoEs (qwen35moe) stop at their trained 262,144 on two cards; memory would allow about 500K on six, which needs rope scaling (not used). Dense or full-attention models run out of card memory first. The planner's compute-buffer formula was 2.7x what llama.cpp allocates (qwen3.6:35b-a3b: 762 planned vs 280 MiB per card at 89K), so its limits were low; calibrated from measured loads (llm-gateway `docs/MANAGER.md`, "Learning from loads") qwen3.6:35b-a3b loads at 230,144 on the 3090 alone (was 174,336) and 158,976 on five 1060s (was 89,344; 131K was refused by 56 MiB). | capacity runs 2026-10-24; fit calibration matrix 2026-10-25 (table under "Fit calibration") |
| **The first card of a 1060 split carries a fixed extra** (about 1.3 GB for nex-n2.5:mini), so an equal split overfills it near capacity; the manager's planner balances headroom per card. | 2026-10-17 |
| **Pascal and Ampere kernels give different greedy outputs**, so a model's scores on 1060s can differ slightly from the 3090. | nex-n2.5:mini GSM8K, 2026-10-17 |
| **Row split** (tensor parallel) is not available for the hybrid recurrent architectures in llama.cpp b11669. | 2026-10-17 |

## Open questions

| Question | Test | State |
|---|---|---|
| Why does x1 cost prefill as well as decode? | the 3090 on gen 2 x1 lost 40% prefill at 3K tokens; a prefill sweep by prompt length and micro-batch on x1 vs x16 | open; the riser and x1 questions above it were answered 2026-10-25 (finding "An x1 link costs...") |
| Can C17/C18 run gen 2? | `setpci` the 1b.6 target link speed to 5 GT/s and retrain with a card on the switch; or a BIOS option for the switch uplink | not tried; the cards are kept out of C17/C18 instead |
| Is the 3090 + 1060 decode drop the output layer on the 1060? | the same model with the 3090 last in the card order | needs the manager to place cards in a chosen order |
| How much does micro-batch lift long-context prefill? | matched 128/512 capacity runs at 131,072 on the 3090 | done 2026-10-25: 1.87-2.32x prefill through 125K tokens, decode unchanged; details below |
| Five 1060s against the 3090 at the same depths | `capacity_run.py qwen3.6:35b-a3b --gpus 1,2,3,4,5 --depth-of 131072` | done 2026-10-25: the five 1060s hold ctx 89,344; at 13K / 34K / 68K tokens the 3090 alone is 5.5-7.3x faster at prefill and 6.3-7.5x at decode |

## Micro-batch at working context, 2026-10-25

Matched managed capacity runs on the 3090 used the standing 350 W cap, the same model, cards, context, and five recall probes. Load time is not a batch comparison: the first load was cold (qwen3.6:35b-a3b 87.7 s at 512, then 21.8 s at 128; qwen3.6:27b 51.3 s at 512, then 15.0 s at 64). Every recall probe passed.

| Model, context | Batch | Prefill at 10% / 50% / 90% (tok/s) | First token at 90% | Decode at 90% (tok/s) | llama.cpp compute on GPU0 |
|---|---:|---:|---:|---:|---:|
| qwen3.6:35b-a3b, 131,072 | 128 | 1,640 / 1,458 / 1,319 | 94.5 s | 74.06 | 302 MiB |
| qwen3.6:35b-a3b, 131,072 | 512 | 3,797 / 3,007 / 2,468 | 50.5 s | 74.15 | 440 MiB |
| qwen3.6:27b, 16,384 (brain) | 64 | 977 / 1,067 / 1,049 | 14.2 s | 40.58 | 79 MiB |
| qwen3.6:27b, 16,384 (brain) | 512 | 1,426 / 1,527 / 1,483 | 10.1 s | 40.37 | 180 MiB |

For qwen3.6:35b-a3b, batch 512 lifts prefill 2.32x at 13K prompt tokens and 1.87x at 125K; depth decode matches within 1%. For the current qwen3.6:27b brain, the 64-to-512 change lifts prefill 1.41-1.46x through 15K; depth decode again matches. The extra compute allocation is 138 MiB and 101 MiB respectively. Measured peak GPU memory differs by 124 MiB and 88 MiB. The records are `qwen3_6_35b-a3b_capacity_g0_ctx131072_b{128,512}_20261025.json` and `qwen3_6_27b_capacity_g0_ctx16384_b{64,512}_20261025.json` in `results/runtime_experiments/`.

The model registry now sets batch 512 for the tested qwen3.6:35b-a3b and gemma-4:31b interactive and orchestration profiles, and for qwen3.6:27b orchestration. The benchmark default profiles keep their former batches so campaign comparisons remain on the same settings. The 32K Gemma sweep supports its smaller 1.2-1.3x prefill gain; a matched long-context Gemma run has not been done. The manager now calibrates compute per card count and full-depth growth margin for matching layouts.

## Hardware swaps 2026-10-25 (done)

The riser and x1 plan (commit 34d37f7) ran as one session of moves, each checked with `rig status` and
`nvidia-smi` before a run. The new riser on the old GPU 3 changed nothing: its gen 1 link was the C17/C18 switch
slot. The 3090 on the old GPU 1 slot (gen 2 x1) and that EVGA on the x16 gave the x1 cost (finding above). The
split runs of the plan were not run on the swapped layout. The rig went back to the 3090 on x16 with all six cards
on direct gen 2 root ports (table at the top); runs on that layout:

| Run | Record | Baseline (2026-10-24, one card on gen 1) | Result |
|---|---|---|---|
| `qwen3.5:4b --gpus 0 --ctx 32768` (3090) | `qwen3_5_4b_capacity_3090-x16-restored_ctx32768_20261025.json` | 172.6 tok/s | 172.0 tok/s, prefill 3965 at 3K, load 48 s: back to the x16 baseline |
| `qwen3.5:4b --gpus 2 --ctx 32768` (old GPU 3 EVGA, now direct gen 2) | `qwen3_5_4b_capacity_evga3-direct-x1_ctx32768_20261025.json` | 24.0 tok/s (gen 1) | 27.8 tok/s, prefill 484 at 3K, load 22 s: the same as the other EVGA on gen 2 x1 (28.0) |
| `qwen3.6:35b-a3b --gpus 0,1,2,3,4,5 --ctx 131072` | `qwen3_6_35b-a3b_capacity_g0-1-2-3-4-5-allgen2_ctx131072_20261025.json` | 39.7 tok/s, prefill 554 / 256, decode 35.7 / 16.1, first token at 90% 8.1 min | 38.7 tok/s, prefill 561 / 269, decode 36.0 / 16.2, first token 7.7 min, recall ok: the same within run-to-run variation, so the one gen 1 card in the old layout cost the split nothing measurable (second attempt, after rewiring the ASUS Dual; the first lost that card in the first depth probe) |
| `qwen3.6:35b-a3b --gpus 1,2,3,4,5 --ctx 131072` | `qwen3_6_35b-a3b_capacity_g1-2-3-4-5_ctx131072_nofit_20261025.json` | won't fit (2026-10-24, not recorded then) | won't fit: 56 MiB short (22,006 MiB needed, 21,950 after margins); the five 1060s hold 89,344 |

**The ASUS Dual (`ac5b4fea`) falls off the bus.** Twice on 2026-10-25: idle in a C17/C18 switch slot (10:09),
and under the six-card load on direct root port 1c.7 (10:47). It follows the card (or the riser, cable and
power that moved with it), not the slot. Its fan goes to 100% when it drops; the rig reports `FAULT` and holds
loads until a power cycle. Rewired after the second drop. **If it keeps dropping, it is the first card to
replace when the new GTX 1070s arrive** (the white two-fan board).

## Fit calibration 2026-10-25

Each model loaded at the largest context the manager planned, twice per card set: pass 1 planned from the old
formula (or the first measured load), pass 2 from what pass 1 measured (`capacity-calibrate-20261025`,
`--skip-depth`: load and short probe; the context is allocated at load, so a load that serves holds it).

| Model | Cards | Pass 1 ctx | Pass 2 ctx | Decode, short prompt |
|---|---|---|---|---|
| qwen3.6:35b-a3b | 3090 | 230,144 (already calibrated) | - | 152.0 |
| qwen3.6:35b-a3b | five 1060s | 158,976 (already calibrated) | - | 26.3 |
| gemma-4:31b | 3090 | 90,368 | 101,888 | 38.2 |
| gemma-4:31b | five 1060s | 87,296 | 78,336 | 5.4 |
| qwen3-coder:30b-a3b | 3090 | 96,256 | 120,064: out of memory (CUDA graphs, 3090) | 190.8 |
| qwen3-coder:30b-a3b | five 1060s | 143,872 | 135,680 | 33.9 |
| gemma-4:26b-a4b | 3090 | 262,144 (trained) | 262,144 | 139.6 |
| gemma-4:26b-a4b | five 1060s | 262,144 (trained) | 261,888 | 24.3 |
| qwen3.6:27b | 3090 | 185,344 | 219,648 | 44.2 |
| qwen3.6:27b | five 1060s | 190,208 | 168,704 | 6.3 |
| gpt-oss:20b | 3090 | 131,072 (trained) | 131,072 | 194.2 |
| gpt-oss:20b | five 1060s | 131,072 (trained) | 131,072 | 31.8 |

- The calibration moves both ways: a measured buffer larger than the formula's lowers the plan (gemma-4:31b and
  qwen3.6:27b on five 1060s, sliding-window and dense models), a smaller one raises it.
- The qwen3-coder:30b-a3b 120K OOM still sets a ceiling for that GGUF and card-size
  layout. The manager now rejects explicit requests at or above that boundary too.
- **Memory is almost entirely allocated at load.** Full-depth runs at the calibrated limits held to
  90% with recall okay. Peak memory rose 18 MiB on the 3090 at 195,840 context and 8 MiB per
  1060 at 145,152. The manager uses four times measured growth with a 128 MiB floor only
  for the matching GGUF and card-size layout; unmeasured layouts keep 512 MiB. It calibrates
  compute separately by card count and pads the highest observed serving overhead by 64 MiB.
  This replaced the previous pooled compute and 624 MiB padded 3090 overhead. The previously
  refused qwen3.6:35b-a3b 230,144 GPU0 fit now passes. A real managed load reached ready
  in 84.5 s and decoded at 148.34 tok/s, then unloaded successfully. Evidence:
  `results/runtime_experiments/qwen3_6_35b_a3b_fit_calibrated_20261025.txt` and
  `qwen3_6_35b_a3b_capacity_g0_ctx230144_fit_calibrated_20261025.json`.

| qwen3.6:35b-a3b, full depth | ctx | Prefill 10% / 90% | Decode 10% / 90% | First token at 90% | Record |
|---|---|---|---|---|---|
| 3090 | 195,840 | 1604 / 1196 | 132.3 / 58.4 | 2.6 min | `*_g0_ctx195840_20261025.json` |
| five 1060s | 145,152 | 300 / 140 | 22.0 / 8.6 | 16.5 min | `*_g1-2-3-4-5_ctx145152_20261025.json` |
- The 3090 against five 1060s, decode on the same model: 5.7x (qwen3.6:35b-a3b, gemma-4:26b-a4b), 5.6x
  (qwen3-coder), 6.1x (gpt-oss), 7.0-7.1x on the dense models (gemma-4:31b, qwen3.6:27b): the ballpark 6x holds,
  and dense models lose more.

## Which tool answers which question

| Question | Tool | Output |
|---|---|---|
| The most a model can do on given cards (largest or fixed context, speed by depth, recall) | benchmarking `scripts/integration/capacity_run.py` | `results/runtime_experiments/*_capacity_*.json` |
| A new model's speed and power at its lane load (Phase 3.5) | benchmarking `scripts/integration/runtime_char.py` (the lane runs it) | `results/runtime_experiments/*_runtime_characterization_*.json` |
| Split scaling over 1 to 5 cards and link settings, micro-batch | llm-gateway `tools/split_sweep.py` | `~/rig_stress/split_sweep_<label>.json` on the Pi; copy a result worth keeping to `results/runtime_experiments/split_scaling_*.json` |
| PCIe traffic under sustained split load | llm-gateway `tools/pcie_split_test.py` | `~/rig_stress/` logs |
| Power and heat at full load, per card by UUID | llm-gateway `tools/rig_stress.py` | `~/rig_stress/run_*.log` and its `--compare` summary |
| Speed and energy across power caps for one card | llm-gateway `tools/power_cap_sweep.py` | `results/runtime_experiments/*_power_cap_sweep_*.json` |
| Both rigs at once | llm-gateway `tools/multi_rig_tests.py`, `tools/dual_rig_bench.sh` | llm-gateway `docs/multi_rig_tests.md` |
| Will it fit, at what context and split (no load) | `rigctl fit MODEL [--gpus ..] [--use chat] [--batch-size B]` | the answer, with what it planned from (`compute_basis`, `overhead_mb`, `failed_ceiling`) |
| What the manager has learned from loads (measured buffers, overhead, failed loads) | `rigctl observations [--kind load_failed] [--model M]` | llm-gateway `lessons/load_observations.jsonl`; copied here by `scripts/active/collect_lessons.py` into `results/imported_lessons/` |
| Prefill and memory by micro-batch | `capacity_run.py ... --ctx N --batch-size B` | `*_capacity_*_b<B>_*.json` |
| Which slot and link each card is on now | `ssh rig rig status` (notes on slow links), rig-local `brain/hw/gpu_layout.json` | the scan |

`context_window_benchmark.py` predates the manager (it probes orchestration's configured workers) and is kept
for that path only. Raw tool output on the Pi (`~/rig_stress`) is outside the repos: a result that answers a
question goes into `results/runtime_experiments/` and its finding into the table above.

## When adding a finding

Put the record in `results/runtime_experiments/` (the generated reference picks it up), state the finding here
in one row with the record's date and model, and remove or update any row it replaces. A finding that changes how
models are loaded (a placement or setting rule) also goes into the manager or the registry, not only here.


## Strata Qwen3.8 Q2_0 mixed-card placement (2026-11-06 UTC)

Matched 8K full-model Strata 0.1.56 CUDA 12 runs, one request at a time with a 512-token warm output: 3090 only **80.3 effective tok/s**, 3090 + one 1060 **68.5**, 3090 + five 1060s **38.0**, and all six cards plus an 8 GiB pinned expert RAM budget **37.7**. The corresponding file-tier sizes were 12.9, 10.8, 2.5 and 0.0 GiB. Extra 1060s reduced storage reads but slowed this short-context Q2 workload. These are output tokens divided by whole-request wall time, not isolated decode rates. Methods, physical NVMe reads and case receipts: [`results/runtime_experiments/strata_q38_mixed_matched_20261106/README.md`](results/runtime_experiments/strata_q38_mixed_matched_20261106/README.md). The Q4 same-model quant is downloading to the 4 TB drive for a later capacity test; it has no measured speed yet.
