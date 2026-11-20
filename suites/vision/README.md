# Vision benchmarks

Benchmarking owns the frozen vision suite, its runner, and its result receipts.
The original dashboard research workspace was the preparation area. Run new
comparisons from this repository so checkpoints use the same frozen images and
answer keys. The image-generation track is a separate planned suite.

The installed rig at the first smoke run has one RTX 3090 Ti, one GTX 1070,
and four GTX 1060s. The five-1070 layout in [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md)
is a future capacity scenario, not the hardware used for current results.

`understanding/local-v1/smoke.jsonl` selects six cases from its frozen
24-case `cases.jsonl`. The 120-case `understanding/local-full-v1/cases.jsonl`
adds 96 deterministic images, with 20 cases per category. Both are synthetic
local screens, not scores for public vision benchmarks. Verify the selected
suite's `SHA256SUMS` before a comparison. The runner
accepts only a loopback endpoint and requires local assets; it does not
download data. It writes one result per case and a summary to the requested
output directory. Record the runtime checkpoint, projector, context, GPU,
peak memory, and cold-load time beside the output. The six-case smoke checks
the pipeline; use all 120 full-suite cases for a larger local comparison.

Example after loading a Qwen vision runtime on port 11434:

```sh
python3 scripts/active/run_vision_understanding.py \
  --base-url http://127.0.0.1:11434/v1 \
  --model /path/to/model.gguf \
  --manifest suites/vision/understanding/local-v1/smoke.jsonl \
  --output results/vision/my-smoke-run
```

See [understanding/README.md](understanding/README.md) for case coverage and
[generation/README.md](generation/README.md) for the separate generation plan.
