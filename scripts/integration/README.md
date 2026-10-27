# Model integration helpers

Small tools for NEW_MODEL_INTEGRATION.md Phases 3-4.5, written during the October 2026 brain
candidate integration. Run them on the rig (they talk to rig-local runtime ports and read
`/mnt/shared`). Model loads go through `run_runtime.sh`, which holds the rig-wide load lock; the
lanes load through the harness (llm-gateway `docs/MANAGER.md`, "Model loads").

| Script | Phase | What it does |
|---|---|---|
| `litmus.py [port]` | 3 | The three litmus checks (555, JSON, code), no system prompt, temperature 0 |
| `runtime_char.py <model> <port> <gpus> <load_s> <source> <out.json> [k=v ...]` | 3.5 | 768-token decode with 1 s GPU sampling; writes a `results/runtime_experiments/` record |
| `phase4.sh <model> <tag> [port]` | 4 | bench-pipeline (whole), bench-code (first 50 HumanEval), bench-reasoning limit 10 with raw samples |
| `p45.sh <model> <tag> <gguf> <ctx> "<off args>" "<on args>"` | 4.5 | Thinking off vs on (end-of-text stops, 4096 budget), geoimport output budget 512 vs 1024, thinking-on pipeline and geoimport; loads on the 3090 | (predates the manager: starts runtimes itself, so only on an otherwise idle rig; the lane runs the thinking A/B with `LANE_START_AT=4.5`)
| `smoke_reasoning.sh <model> <run> [flags]` | 4 / 4.5 | bbh + drop limit 10 with raw samples against :11434, for prompt or flag A/Bs | (predates the manager, like p45.sh)
| `bbh_misses.py <run> ...` | 4 | Classifies BBH misses: wrong answer vs missing answer phrase vs likely cut |
| `run_worker_lanes.sh <lane-list> <model> [model ...]` | 2-4 (4.5 on request) | Works through a queue of models on several lanes in parallel under one thermal guard; a lane is one card (`1`) or a card group (`1+3`, one model split across them), and each takes the next model as soon as it is free. Logs in `/mnt/shared/logs/benchmarks/worker_lanes_<ts>/` |
| `worker_lane.sh <gpu-group> <queue-file>` | 2-4 (4.5 on request) | One lane (used by the above): load through the harness (`rigctl load-model <model> --gpus <group>`: the manager checks the fit and picks context and split, the rig loads and confirms full offload; a model that does not fit is skipped with the reason), litmus, runtime record, Phase 4 smoke and Phase 4.5 suggestions, then it pauses: the model stays loaded and the lane ends. Holds a rig claim `lane-<group>` on its cards for the whole run (refused: `LANE_REFUSED`, the lane does not run). `LANE_STOP_AFTER=3` stops each model after Phase 3 for a quick check; `LANE_START_AT=4.5` runs the thinking A/B when the operator chooses it (Phases 2-4 already done) |
| `harness_lease.sh acquire\|renew\|release` | - | Lease a GPU from the rig manager (llm-gateway on the Pi, `rigctl` over ssh). Unreachable manager: runs without a lease, audited as `no-lease` by `run_runtime.sh` |
| `run_model_context_bounds.py <model> --compact-gpus ... --ceiling-gpus ... --run-id ... --output ...` | 1.5 | Manager min/max fits and real full-offload load/unload checks on the smallest useful and longest-context card groups; checkpoint, summary, and terminal receipt. Start with `rigctl run-start` |
| `run_ram_offload_comparison.py --output ...` | hardware experiment | On an idle rig, compare Qwen3.5 4B at the same prompt, 32K context, and batch in CPU/RAM only, 20 layers on one 1060, fully on one 1060, and fully on the 3090. Direct llama-server runs are experimental and do not change the manager's full-offload profiles; timings, logs, and terminal receipt are saved. |
| `capacity_run.py <model> [--gpus ..|--cards N]` | 4.7 | Probe the validated compact and ceiling contexts at 10%/90% depth (prefill and decode speed, first token, power, final-answer recall); writes a `results/runtime_experiments/` record and unloads. Start it with `rigctl run-start` |
| `resolve_model.py <model>` | - | Registry settings as shell assignments (hot-set path, ctx, batch, extra args, thinking budget) |
| `probe_template.py <samples.jsonl>` | 4 | Shows how the loaded model's chat template ends the prompt and what it generates first (thinking-control diagnosis) |

Notes:
- Thinking runs must pass `--gen-kwargs "max_gen_toks=<N>,until=</s>"`: task stop sequences also fire
  inside thinking text and return empty answers.
- `p45.sh` removes every running runtime container before each load; do not run it while another
  benchmark is using the rig.
