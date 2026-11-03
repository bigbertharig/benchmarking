# Model integration helpers

Small tools for NEW_MODEL_INTEGRATION.md Phases 4-7, written during the October 2026 brain
candidate integration. Run them on the rig (they talk to rig-local runtime ports and read
`/mnt/shared`). Model loads go through `run_runtime.sh`, which holds the rig-wide load lock; the
lanes load through the harness (llm-gateway `docs/MANAGER.md`, "Model loads").
The playbook now uses whole-number phases for new imports. Helper filenames and old receipts retain
their historical phase numbers; `LANE_START_AT=4.5` and `LANE_STOP_AFTER=3` remain accepted aliases.

| Script | Phase | What it does |
|---|---|---|
| `litmus.py [port]` | 4 | The three litmus checks (555, JSON, code), no system prompt, temperature 0 |
| `runtime_char.py <model> <port> <gpus> <load_s> <source> <out.json> [k=v ...]` | 5 | 768-token decode with 1 s GPU sampling; writes a `results/runtime_experiments/` record |
| `phase4.sh <model> <tag> [port]` | 6 | bench-pipeline (whole), bench-code (first 50 HumanEval), bench-reasoning limit 10 with raw samples |
| `p45.sh <model> <tag> <gguf> <ctx> "<off args>" "<on args>"` | 7 | Legacy helper: thinking off vs on, geoimport output budget, pipeline and geoimport; starts runtimes itself, so use only on an otherwise idle rig. The manager lane runs the thinking A/B with `LANE_START_AT=7` |
| `smoke_reasoning.sh <model> <run> [flags]` | 6 / 7 | bbh + drop limit 10 with raw samples against :11434, for prompt or flag A/Bs; legacy direct-runtime helper |
| `bbh_misses.py <run> ...` | 6 | Classifies BBH misses: wrong answer vs missing answer phrase vs likely cut |
| `run_worker_lanes.sh <lane-list> <model> [model ...]` | 3-6 (7 on request) | Works through a queue of models on several lanes in parallel under one thermal guard; a lane is one card (`1`) or a card group (`1+3`, one model split across them), and each takes the next model as soon as it is free. Logs in `/mnt/shared/logs/benchmarks/worker_lanes_<ts>/` |
| `worker_lane.sh <gpu-group> <queue-file>` | 3-6 (7 on request) | One lane (used by the above): load through the manager, litmus, runtime record, Phase 6 smoke and Phase 7 suggestions, then pause with the model loaded. Holds a rig claim `lane-<group>` for the run. `LANE_STOP_AFTER=5` stops after Phase 5 runtime characterization; `LANE_START_AT=7` runs the thinking A/B when the operator chooses it |
| `harness_lease.sh acquire\|renew\|release` | - | Lease a GPU from the rig manager (llm-gateway on the Pi, `rigctl` over ssh). Unreachable manager: runs without a lease, audited as `no-lease` by `run_runtime.sh` |
| `run_model_context_bounds.py <model> --compact-gpus ... --ceiling-gpus ... --run-id ... --output ...` | 2 | Manager min/max fits and real full-offload load/unload checks on the smallest useful and longest-context card groups; checkpoint, summary, and terminal receipt. Start with `rigctl run-start` |
| `run_ram_offload_comparison.py --output ... [--model GGUF] [--ctx N] [--only-mode 3090_full] [--gpu-layers N]` | hardware experiment | Default: compare Qwen3.5 4B at the same prompt, 32K context, and batch in CPU/RAM only, 20 layers on one 1060, fully on one 1060, and fully on the 3090. Optional model/context flags support targeted smokes. With `--only-mode 3090_full --gpu-layers N`, use a recorded partial 3090 placement for a larger model; `--load-timeout` extends readiness wait. Direct llama-server runs are experimental and do not change published profiles; timings, logs, and terminal receipt are saved. Acquire a manager lease before starting. |
| `run_strata_qwen36_probe.py --output DIR [--expert-vram GiB]` | hardware experiment | Launch the verified Qwen3.6 XL GGUF in Strata on leased GPU 0, send two fixed requests, sample GPU/host memory and host-wide NVMe counters, save engine logs and terminal receipt, then stop Strata. |
| `run_strata_qwen36_sweep.py --output DIR` | hardware experiment | Sequential Qwen3.6 expert-VRAM budgets 16, 8 and 0 GiB, with checkpoints and memory-pressure stop gates. Start through `rigctl run-start` after acquiring a GPU 0 lease. |
| `download_strata_qwen38_q2_0.py` | hardware experiment | GPU-free, resumable download of the pinned Qwen3.8 Flash-Next Q2_0 GGUF shards to rig NVMe; verifies sizes and SHA-256, writes a durable terminal receipt. Start through `rigctl run-start`; see `STRATA_MEMORY_TEST_PLAN.md`. |
| `run_strata_qwen38_probe.py --output DIR [--resident-budget-gib GiB]` | hardware experiment | After the Qwen3.8 Q2_0 download passes, launch Strata on leased GPU 0 with default or bounded RAM-resident experts, capture request timings, GPU/host memory, engine process I/O and host-wide NVMe counters, then stop the engine. |
| `run_strata_qwen38_sweep.py --output DIR` | hardware experiment | Sequential Qwen3.8 resident expert RAM budgets of 12, 8, 4, and 0.1 GiB, each through the probe and each stopped before the next. A literal zero was rejected in the 2026-11-03 receipt, so 0.1 GiB is the near-mapped case for repeats. Use one GPU 0 manager lease and review the checkpoint/terminal receipts. |
| `run_strata_qwen38_placement.py --output DIR [--data-dir DIR] [--context N] [--resident-budget-gib GiB] [--depth-fractions 0.1,0.9] [--evict-expert-cache]` | hardware experiment | Compare Qwen3.8 Strata GPU/RAM/file placement and long-context recall. A prepared `--data-dir` can put its expert pack on SATA SSD; GGUF source remains at the pinned NVMe path. Targeted cache eviction is available for cold-read comparisons. Captures physical SATA and NVMe reads, process I/O, memory, responses, logs and terminal receipt. Acquire a manager GPU lease first. |
| `run_qwen38_allcard_llama.py --output DIR --model GGUF --only-mode four_gpus\|five_gpus\|all_gpus [--ctx N] [--kv-type q8_0] [--depth-fractions 0.1,0.9] [--resident-ngram --memory-limit-gib N]` | hardware experiment | Run the same Qwen3.8 GGUF across 3090 plus three, four or five 1060s, recording layer placement, GPU and host memory, timings and optional depth probes. `--resident-ngram` disables lazy lookup reads, puts the lookup in a CPU buffer, and requires a no-swap Docker memory cap; an OOM or guard kill is recorded as a failed fit. Each mode gets its own managed run and terminal receipt. |
| `probe_host_ram_budget.py --output DIR [--target-gb-decimal 26] [--min-available-gib 4]` | hardware experiment | GPU-free, managed test of resident host RAM headroom. Touches private anonymous pages in 256 MiB steps, records `MemAvailable` and swap, and uses a conservative 4 GiB headroom gate. The measured 26 GB decimal planning limit is in `RIG_PERFORMANCE.md`. |
| `capacity_run.py <model> [--gpus ..|--cards N]` | 8 | Probe the validated compact and ceiling contexts at 10%/90% depth (prefill and decode speed, first token, power, final-answer recall); writes a `results/runtime_experiments/` record and unloads. Start it with `rigctl run-start` |
| `resolve_model.py <model>` | - | Registry settings as shell assignments (hot-set path, ctx, batch, extra args, thinking budget) |
| `probe_template.py <samples.jsonl>` | 6 | Shows how the loaded model's chat template ends the prompt and what it generates first (thinking-control diagnosis) |

Notes:
- Thinking runs must pass `--gen-kwargs "max_gen_toks=<N>,until=</s>"`: task stop sequences also fire
  inside thinking text and return empty answers.
- `p45.sh` removes every running runtime container before each load; do not run it while another
  benchmark is using the rig.
