# Model integration helpers

Small tools for NEW_MODEL_INTEGRATION.md Phases 3-4.5, written during the October 2026 brain
candidate integration. Run them on the rig (they talk to rig-local runtime ports and read
`/mnt/shared`). Model loads go through `run_runtime.sh`, which holds the rig-wide load lock.

| Script | Phase | What it does |
|---|---|---|
| `litmus.py [port]` | 3 | The three litmus checks (555, JSON, code), no system prompt, temperature 0 |
| `runtime_char.py <model> <port> <gpus> <load_s> <source> <out.json> [k=v ...]` | 3.5 | 768-token decode with 1 s GPU sampling; writes a `results/runtime_experiments/` record |
| `phase4.sh <model> <tag> [port]` | 4 | bench-pipeline, bench-code (full), bench-reasoning limit 10 with raw samples |
| `p45.sh <model> <tag> <gguf> <ctx> "<off args>" "<on args>"` | 4.5 | Thinking off vs on (end-of-text stops, 4096 budget), geoimport output budget 512 vs 1024, thinking-on pipeline and geoimport; loads on the 3090 |
| `smoke_reasoning.sh <model> <run> [flags]` | 4 / 4.5 | bbh + drop limit 10 with raw samples against :11434, for prompt or flag A/Bs |
| `bbh_misses.py <run> ...` | 4 | Classifies BBH misses: wrong answer vs missing answer phrase vs likely cut |
| `run_worker_lanes.sh <gpu-list> <model> [model ...]` | 2-4.5 | Works through a queue of single-GPU models on several GTX 1060s in parallel under one thermal guard; each card takes the next model as soon as it is free. Logs in `/mnt/shared/logs/benchmarks/worker_lanes_<ts>/` |
| `worker_lane.sh <gpu> <queue-file>` | 2-4.5 | One lane (used by the above): load with registry settings, litmus, runtime record, Phase 4 smoke, thinking A/B when the template supports thinking |
| `resolve_model.py <model>` | - | Registry settings as shell assignments (hot-set path, ctx, batch, extra args, thinking budget) |
| `probe_template.py <samples.jsonl>` | 4 | Shows how the loaded model's chat template ends the prompt and what it generates first (thinking-control diagnosis) |

Notes:
- Thinking runs must pass `--gen-kwargs "max_gen_toks=<N>,until=</s>"`: task stop sequences also fire
  inside thinking text and return empty answers.
- `p45.sh` removes every running runtime container before each load; do not run it while another
  benchmark is using the rig.
