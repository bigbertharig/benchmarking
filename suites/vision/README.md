# Vision benchmarks

Benchmarking owns the frozen vision suite, its runner, and its result receipts.
The original dashboard research workspace was the preparation area. Run new
comparisons from this repository so checkpoints use the same frozen images and
answer keys. The generation/editing input bank is frozen separately and has
completed SDXL and Instruct Pix2Pix runtime baselines. Image quality review
remains a separate step.

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

## First full local understanding screen (2026-11-20)

All runs used the same 120-image manifest (SHA-256
`f9cd943f8f803af010f1625a5a5b0fe781dcff95bf5bd48af95bfc702f26250f`),
temperature 0, and a 1,024-token response cap. Accuracy is exact answer match;
schema compliance is reported separately. Times are per-case medians, including
image handling and generation, on the stated card.

| Local checkpoint | Card | Correct | Schema | OCR | Median case |
| --- | --- | ---: | ---: | ---: | ---: |
| Gemma 4 12B Q6_K_L | RTX 3090 Ti | 115/120 | 98.3% | 17/20 | 4.06 s |
| Qwen3.5 9B Q3_K_M | GTX 1070 | 80/120 | 97.5% | 0/20 | 6.82 s |
| Qwen3.5 9B Q4_K_M | RTX 3090 Ti | 76/120 | 94.2% | 0/20 | 1.13 s |
| Step3-VL-10B BF16 | RTX 3090 Ti (20 GiB cap) | 108/120 | 98.3% | 20/20 | 5.71 s |

The full case-level receipts are in
[`results/vision`](../../results/vision), under directories beginning
`local-full120-`. These synthetic cases are a deployment screen, not public
OCRBench or other external benchmark scores. The Qwen Q3 and Q4 runs used
different GPUs, so their timing difference is not a quantization speed result.
Both Qwen runs missed all 20 local OCR cases; review those case outputs before
using either for OCR-heavy work. A 256-token diagnostic run truncated many
Gemma answers; the table uses the corrected 1,024-token run.
Step3 used a 20 GiB GPU placement cap with host RAM available; its observed
peak GPU memory was 20,875 MiB. It passed all document, GUI, OCR, and spatial
cases, 19/20 charts, and 9/20 negative cases. Its native reasoning text is
retained in the raw receipt, while scoring uses the final answer after
`</think>`. One chart case exhausted the 1,024-token answer budget without a
final answer. The corrected six-case smoke was 5/6; the earlier uncorrected
zero-score smoke was a parser diagnostic, not model evidence.

## First full local generation runs (2026-11-20)

The frozen generation manifest has 36 text-to-image prompts and 12 edit
prompts, each at four fixed seeds. These are separate tracks. Both baselines
used the RTX 3090 Ti; times are medians for individual completed outputs.

| Track | Checkpoint | Outputs | Blocked | Median output | Peak observed VRAM | Review |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Text-to-image | SDXL base 1.0 fp16 | 144/144 | 0 | 7.765 s | 14,811 MiB | Pending |
| Image editing | Instruct Pix2Pix fp16 | 48/48 files | 3 safety replacements | 1.311 s | 3,897 MiB | Pending |

The Pix2Pix safety checker returned black images for three ordinary edit
requests. Those files are retained for audit and flagged as blocked in the
receipt and review gallery. File completion does not imply edit success.
Each result directory under [`results/vision`](../../results/vision) contains
the case-level JSONL, summary, runtime context and telemetry summary. The PNGs,
raw GPU samples and portable review galleries live outside Git under the
shared archive at `benchmark-results/vision/2026-11-20/` (`sdxl-full144` and
`pix2pix-full48`). No image-quality score has been assigned yet.
