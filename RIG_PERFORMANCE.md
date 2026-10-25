# Rig performance

How fast the rig runs models, why, and how to measure it. This is the owner of speed, context-capacity,
split and PCIe knowledge: what is known (with the record behind it), what is still open, and which tool
answers which question. The numbers themselves are in the generated
[results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md) (every record in `results/runtime_experiments/`);
model quality scores are in [results/MODEL_BENCHMARK_REFERENCE.md](results/MODEL_BENCHMARK_REFERENCE.md).
Addresses and host details: llm_orchestration `shared/workspace/local/inventory.md`; the rig hardware layer
(guard, power caps, loads): llm_orchestration `shared/scripts/rig/README.md`.

## The cards and links

| GPU | Card | Board (power default) | PCIe link | Cap (rig-power.service) |
|---|---|---|---|---|
| 0 | RTX 3090 Ti 24 GB | | gen 2 x16 | 350 W |
| 1 | GTX 1060 6 GB | EVGA (120 W) | gen 2 x1 riser | 100 W |
| 2 | GTX 1060 6 GB | ASUS overclocked (156 W) | gen 2 x1 riser | 100 W |
| 3 | GTX 1060 6 GB | EVGA (120 W) | gen 1 x1 riser: the card and slot support gen 2, the link trains at gen 1 (riser) | 100 W |
| 4 | GTX 1060 6 GB | ASUS overclocked (156 W) | gen 2 x1 riser | 100 W |
| 5 | GTX 1060 6 GB | ASUS Dual (120 W) | gen 2 x1 riser | 100 W |

`nvidia-smi --query-gpu=index,pci.sub_device_id,pcie.link.gen.max,pcie.link.width.current --format=csv` shows
the links (vendor in the sub device id: 3842 EVGA, 1043 ASUS). The BIOS stays at gen 2: gen 3 logged link
replays on every 1060 riser. GPU numbers follow PCI bus order, so moving cards between slots can renumber them;
the rig config's brain card, `brain` placements and pinned `gpus: [0]` assume the 3090 is GPU 0.

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
| **GPU 3's gen 1 link costs a few percent, not yet separated from the board.** GPUs 1+3 ran about 3 ms per token slower than 1+2, but GPU 2 is a different board. GPUs 1 and 3 are the same EVGA board, which makes them the clean comparison. | 2026-10-19, 2026-10-24 |
| **Context capacity is set by the trained context or by card memory.** The ~30B hybrid MoEs (qwen35moe) stop at their trained 262,144 on two cards; qwen3.6:35b-a3b holds 174K on the 3090 alone; memory would allow about 500K on six, which needs rope scaling (not used). Dense or full-attention models run out of card memory first. | capacity runs and the manager's planner, 2026-10-24 |
| **The first card of a 1060 split carries a fixed extra** (about 1.3 GB for nex-n2.5:mini), so an equal split overfills it near capacity; the manager's planner balances headroom per card. | 2026-10-17 |
| **Pascal and Ampere kernels give different greedy outputs**, so a model's scores on 1060s can differ slightly from the 3090. | nex-n2.5:mini GSM8K, 2026-10-17 |
| **Row split** (tensor parallel) is not available for the hybrid recurrent architectures in llama.cpp b11669. | 2026-10-17 |

## Open questions

| Question | Test | State |
|---|---|---|
| Does GPU 3's riser cost speed? | qwen3.5:4b at 32K on GPU 3 alone and GPU 1 alone (same board), before and after swapping the riser | before: queued (`capacity-queue7-20261024`); riser swap planned |
| Does the 3090 slow down on an x1 link? | swap the 3090 with a gen 2 1060 (GPU 1); rerun the 3090 alone, 3090 + 1060 and six-card capacity runs | baseline: the 2026-10-24 capacity runs; check GPU numbering after the move |
| Is the 3090 + 1060 decode drop the output layer on the 1060? | the same model with the 3090 last in the card order | needs the manager to place cards in a chosen order |
| How much does micro-batch lift long-context prefill? | a capacity run with `-ub 512` against the profile's batch | not started |
| Five 1060s against the 3090 at the same depths | `capacity_run.py qwen3.6:35b-a3b --gpus 1,2,3,4,5 --depth-of 131072` | queued (`capacity-queue6-20261024`) |

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
