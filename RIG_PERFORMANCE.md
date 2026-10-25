# Rig performance

How fast the rig runs models, why, and how to measure it. This is the owner of speed, context-capacity,
split and PCIe knowledge: what is known (with the record behind it), what is still open, and which tool
answers which question. The numbers themselves are in the generated
[results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md) (every record in `results/runtime_experiments/`);
model quality scores are in [results/MODEL_BENCHMARK_REFERENCE.md](results/MODEL_BENCHMARK_REFERENCE.md).
Addresses and host details: llm_orchestration `shared/workspace/local/inventory.md`; the rig hardware layer
(guard, power caps, loads): llm_orchestration `shared/scripts/rig/README.md`.

## The cards and links

The live list is the rig's scan, not this file: `ssh rig rig status` (cards, and what moved since the last boot)
and rig-local `brain/hw/gpu_layout.json` (index, UUID, board, PCI bus per card, recorded at each boot). A card's
index follows PCI bus order and changes whenever cards move, so a record names a card by UUID and link, not by
index alone.

The cards (by UUID prefix), and the layout from 2026-10-25 10:36:

| Card | Board (power default), UUID | Cap (rig-power.service) | Index, root port, link |
|---|---|---|---|
| RTX 3090 Ti 24 GB | `409c0fe8` | 350 W | 0, CPU x16, gen 2 x16 |
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
shows the links (vendor in the sub device id: 3842 EVGA, 1043 ASUS). The BIOS stays at gen 2: gen 3 logged link
replays on every 1060 riser. The rig config's brain card, `brain` placements and pinned `gpus: [0]` assume the
3090 is GPU 0; the rig itself works with whatever cards the scan finds (llm_orchestration
`shared/scripts/rig/README.md`, "The cards are whatever the scan finds").

## What is known

| Finding | Evidence |
|---|---|
| **The 1060 is the slow part, not the bus.** The same model alone on the 3090 decodes 6.2x faster than alone on a 1060 and prefills 8x faster (12x deep in the context). | qwen3.5:4b at 32K, capacity runs 2026-10-24; nex-n2.5:mini 6.5x and gemma-4:26b-a4b 6.3x in earlier splits |
| **Splitting across 1060s costs decode nothing measurable.** 0 to 4 hops stay within card-to-card variation; the links carry 6-58 MB/s per card against about 500 MB/s for gen 2 x1. A layer split runs the cards one after another, so each card's VRAM bandwidth sets the speed. | split_sweep gen 2 / gen 3, qwen2.5-coder:7b, 2026-10-19; qwen3.5:4b on 1, 2 and 5 1060s, 2026-10-24 |
| **Fewest cards wins.** For a given model and context every added card was slower; a split buys capacity, not speed. | qwen3.6:35b-a3b at 131K: 152 / 65 / 43 / 40 tok/s decode on 1 / 2 / 4 / 6 cards; at 262K, 2 cards beat 4 and 6 |
| **A 3090 + 1060 split loses more decode than the 1060's share of layers.** One of 33 layers on a 1060 took decode from 173 to 79 tok/s while prefill did not move. Suspected: the output layer goes on the last card in the order, the 1060, and it runs for every generated token but once per prompt. Not yet tested. | qwen3.5:4b, 2026-10-24 |
| **Speed falls as the context fills.** From 10% to 90% of the context, decode about halves and prefill drops a quarter to two thirds (more on more cards). At 217K tokens the first token took 23 min on six cards. | capacity depth probes, 2026-10-24 |
| **Micro-batch is the prefill lever.** `-b 2048 -ub 512` gave 2.4x prefill on a five-1060 split with no decode cost (2048 fell back). Profiles default to batch 64, so capacity prefill numbers describe the profile's batch. | split_sweep, 2026-10-19 |
| **PCIe gen 3 helps loads only.** A cold five-card load went from 132 to 90 s; inference did not change, and the risers logged replays, so the BIOS stays at gen 2. | split_sweep and pcie_split_test, 2026-10-19 |
| **An x1 link costs a fixed ~3 ms per generated token on gen 2 and ~9 ms on gen 1, on any card.** qwen3.5:4b alone at 32K: the 3090 goes from 172.6 tok/s on x16 to 114.3 on gen 2 x1 (5.79 to 8.75 ms per token, +3.0 ms); the same EVGA 1060 runs 30.5 on x16, 28.0 on gen 2 x1 (the other EVGA, matched on two different slots within 0.04 tok/s) and 24.0 on gen 1 x1 behind the C17/C18 switch (32.8 / 35.7 / 41.7 ms: +2.9 and +8.9 ms). Fits the per-token copy of the full output scores to the CPU (about 1 MB for a 248K vocabulary), sized larger than the 2 ms estimate. Prefill also drops on x1, which the copy does not explain: 3090 at 3K tokens 3976 to 2372 tok/s (-40%), the 1060 523 to 488 (-7%); loads take longer (3090 43 to 108 s). So a large-vocabulary model on any x1 card pays a fixed cost per token, and so does a split whose last card is on x1. The 24 vs 28 tok/s gap between the two EVGA 1060s was the gen 1 slot, not the card (it was repasted before the baseline) or the riser. | qwen3.5:4b capacity runs 2026-10-25: `*_g1_*`, `*_g3_*`, `*_3090-x1_*`, `*_evga3-x16_*`, `*_evga1-x1_*` |
| **Context capacity is set by the trained context or by card memory.** The ~30B hybrid MoEs (qwen35moe) stop at their trained 262,144 on two cards; qwen3.6:35b-a3b holds 174K on the 3090 alone; memory would allow about 500K on six, which needs rope scaling (not used). Dense or full-attention models run out of card memory first. | capacity runs and the manager's planner, 2026-10-24 |
| **The first card of a 1060 split carries a fixed extra** (about 1.3 GB for nex-n2.5:mini), so an equal split overfills it near capacity; the manager's planner balances headroom per card. | 2026-10-17 |
| **Pascal and Ampere kernels give different greedy outputs**, so a model's scores on 1060s can differ slightly from the 3090. | nex-n2.5:mini GSM8K, 2026-10-17 |
| **Row split** (tensor parallel) is not available for the hybrid recurrent architectures in llama.cpp b11669. | 2026-10-17 |

## Open questions

| Question | Test | State |
|---|---|---|
| Why does x1 cost prefill as well as decode? | the 3090 on gen 2 x1 lost 40% prefill at 3K tokens; a prefill sweep by prompt length and micro-batch on x1 vs x16 | open; the riser and x1 questions above it were answered 2026-10-25 (finding "An x1 link costs...") |
| Can C17/C18 run gen 2? | `setpci` the 1b.6 target link speed to 5 GT/s and retrain with a card on the switch; or a BIOS option for the switch uplink | not tried; the cards are kept out of C17/C18 instead |
| Is the 3090 + 1060 decode drop the output layer on the 1060? | the same model with the 3090 last in the card order | needs the manager to place cards in a chosen order |
| How much does micro-batch lift long-context prefill? | a capacity run with `-ub 512` against the profile's batch | not started |
| Five 1060s against the 3090 at the same depths | `capacity_run.py qwen3.6:35b-a3b --gpus 1,2,3,4,5 --depth-of 131072` | done 2026-10-25: the five 1060s hold ctx 89,344; at 13K / 34K / 68K tokens the 3090 alone is 5.5-7.3x faster at prefill and 6.3-7.5x at decode |

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
| Will it fit, at what context and split (no load) | `rigctl fit MODEL [--gpus ..] [--use chat]` | the answer |

`context_window_benchmark.py` predates the manager (it probes orchestration's configured workers) and is kept
for that path only. Raw tool output on the Pi (`~/rig_stress`) is outside the repos: a result that answers a
question goes into `results/runtime_experiments/` and its finding into the table above.

## When adding a finding

Put the record in `results/runtime_experiments/` (the generated reference picks it up), state the finding here
in one row with the record's date and model, and remove or update any row it replaces. A finding that changes how
models are loaded (a placement or setting rule) also goes into the manager or the registry, not only here.
