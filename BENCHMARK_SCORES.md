# Benchmark Scores

Pure score tables from local rig benchmarking. No commentary — just numbers.

Companion docs:
- [MODEL_LIBRARY.md](MODEL_LIBRARY.md) — model selection hub, best choices, inventory
- [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md) — per-model runtime requirements and best practices
- [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md) — debugging narratives and tuning histories

Machine-readable sources:
- generated score ledger: `/media/bryan/shared/logs/benchmarks/MODEL_BENCHMARK_REFERENCE.md`
- raw records: `/media/bryan/shared/logs/benchmarks/model_benchmark_records.jsonl`
- scoreboard JSON: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json`

## Family Summary Tables

### gemma-4 family

| Model | humaneval | mbpp | gsm8k | bbh | drop f1 | cmd_safety | long_ctx | orch | ambiguity |
|-------|-----------|------|-------|-----|---------|-----------|----------|------|-----------|
| E4B | 6.1% | 19.0% | 0.60 | 0.08 | 0.31 | 50.0% | 85.7% | 83.3% | 61.5% |
| E2B | 6.7% | 22.0% | 0.74 | 0.14 | 0.05 | 58.3% | 92.9% | 83.3% | 7.7% |
| 12B | 11.0% | 36.8% | 0.10 | 0.822 | — | 75.0% | 92.9% | 83.3% | 46.2% |
| 26B-A4B | 13.4% | 42.6% | 0.95 | 0.84 | 0.79 | 58.3% | 100% | 91.7% | 69.2% |
| 31B | 28.7% | 65.6% | 0.95 | 0.84 | 0.79 | 58.3% | 92.9% | 83.3% | 53.8% |

### qwen3.6 family

| Model | humaneval | mbpp | gsm8k | bbh | drop f1 | cmd_safety | long_ctx | orch | ambiguity |
|-------|-----------|------|-------|-----|---------|-----------|----------|------|-----------|
| 27B | 93.3% | 92.6% | 0.94 | 0.893 | 0.883 | 100% | 100% | 83.3% | 53.8% |
| 35B-A3B | 91.5% | 91.0% | 0.96 | 0.876 | 0.830 | 100% | 100% | 83.3% | 46.2% |

## bench-pipeline (worker reliability)

Pipeline tests run all cases (fixed test sets), no limit parameter.

| Model | json_schema | cmd_safety | ambiguity | tool_plan | orch_tradeoff | long_ctx | Time | Date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | 69.2% | 91.7% | 15.4% | 93.3% | 75.0% | 92.9% | — | 2026-03-11 |
| `Llama-3.2-3B` | 7.7% | 33.3% | 23.1% | 80.0% | 75.0% | 92.9% | 42s | 2026-04-28 |
| `SmolLM3-3B` | 15.4% | 100% | 0% | 80.0% | 58.3% | 92.9% | 40s | 2026-04-28 |
| `Gemma-4-E4B` | 23.1% | 50.0% | 61.5% | 93.3% | 83.3% | 85.7% | 2m32s | 2026-04-22 |
| `Gemma-4-E2B` | 30.8% | 58.3% | 7.7% | 93.3% | 83.3% | 92.9% | — | 2026-04-22 |
| `Gemma-4-12B` | 23.1% | 75.0% | 46.2% | 93.3% | 83.3% | 92.9% | ~45m | 2026-06-06 |
| `Qwen2.5-Coder-14B` | 23.1% | 25.0% | 7.7% | 93.3% | 75.0% | 92.9% | 4m48s | 2026-03-14 |
| `Phi-4-14B` | 0% | 100% | 38.5% | 100% | 91.7% | 100% | 3m58s | 2026-03-14 |
| `Gemma-4-26B-A4B` | 30.8% | 58.3% | 69.2% | 93.3% | 91.7% | 100% | 2m57s | 2026-04-22 |
| `Gemma-4-31B` | 23.1% | 58.3% | 53.8% | 93.3% | 83.3% | 92.9% | 7m00s | 2026-04-22 |
| `Qwen3.6-27B` | 23.1% | 100% | 53.8% | 93.3% | 83.3% | 100% | 1m19s | 2026-04-22 |
| `Qwen3.6-35B-A3B` | 15.4% | 100% | 46.2% | 93.3% | 83.3% | 100% | 32s | 2026-04-22 |

## bench-code (EvalPlus generation)

Scores shown as base / plus. Code tests run all problems (fixed sets), no limit parameter.

| Model | humaneval (base/plus) | mbpp (base/plus) | Time | Date |
| --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | 88.4% / 84.8% | 82.5% / 70.4% | — | 2026-03-11 |
| `Llama-3.2-3B` | 64.0% / 59.1% | 63.8% / 53.4% | — | 2026-03-17 |
| `SmolLM3-3B` | 65.9% / 59.8% | 63.8% / 55.0% | — | 2026-03-17 |
| `Gemma-4-E4B` | 6.1% / 5.5% | 19.0% / 17.5% | — | 2026-04-22 |
| `Gemma-4-E2B` | 6.7% / 6.7% | 22.0% / 20.4% | — | 2026-04-22 |
| `Gemma-4-12B` | 11.0% / 11.0% | 36.8% / 34.7% | ~12h | 2026-06-06 |
| `Qwen2.5-Coder-14B` | 90.2% / 86.6% | 84.9% / 73.5% | — | 2026-03-14 |
| `Phi-4-14B` | 78.7% / 73.2% | 73.8% / 64.0% | — | 2026-03-14 |
| `Gemma-4-26B-A4B` | 13.4% / 12.8% | 42.6% / 39.7% | 1h17m | 2026-04-22 |
| `Gemma-4-31B` | 28.7% / 28.7% | 65.6% / 58.7% | 2h56m | 2026-04-22 |
| `Qwen3.6-27B` | 93.3% / 91.5% | 92.6% / 77.5% | 55m | 2026-04-22 |
| `Qwen3.6-35B-A3B` | 91.5% / 89.0% | 91.0% / 76.7% | 20m | 2026-04-22 |

## bench-reasoning (lm-eval generation)

Latest/highest-limit score per model only.

| Model | gsm8k | bbh | drop (f1) | Limit | Time | Date |
| --- | --- | --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | 0.75 | 0.6674 | 0.576 | 100 | 9h13m | 2026-03-14 |
| `Llama-3.2-3B` | 0.72 | 0.5896 | 0.4326 | 100 | 4h09m | 2026-03-18 |
| `SmolLM3-3B` | 0.79 | 0.6678 | 0.3302 | 100 | 4h16m | 2026-03-18 |
| `Gemma-4-E4B` | 0.60 | 0.08 | 0.31 | 10 | 1h41m | 2026-06-07 |
| `Gemma-4-E2B` | 0.74 | 0.141 | 0.051 | 50 | 4h02m | 2026-06-08 |
| `Gemma-4-12B` | 0.10 | 0.822 | — | 100/5 | — | 2026-06-06 |
| `Gemma-4-26B-A4B` | 0.95 | 0.841 | 0.785 | 100 | 1h33m | 2026-06-08 |
| `Gemma-4-31B` | 0.95 | 0.842 | 0.793 | 100 | 1h32m | 2026-06-08 |
| `Qwen2.5-Coder-14B` | 0.89 | 0.5937 | 0.4802 | 100 | 9h25m | 2026-03-16 |
| `Phi-4-14B` | 0.78 | 0.5770 | 0.0925 | 100 | 10h32m | 2026-04-29 |
| `Qwen3.6-27B` | 0.94 | 0.893 | 0.883 | 50 | 16m | 2026-04-25 |
| `Qwen3.6-35B-A3B` | 0.96 | 0.876 | 0.830 | 50 | 45m | 2026-04-25 |

Gemma-4-12B note: GSM8K at limit 100, BBH at limit 5 (A/B test: `--reasoning-budget 0` scored 0.822 vs `--reasoning-budget 1024` scored 0.244 — thinking mode destroys BBH extraction). DROP l5 smoke passed (EM=0.60, F1=0.70). GSM8K low score (0.10) is format mismatch (model outputs `$18` not `#### 18`), not capability.

**Gemma-4 reasoning re-run (2026-06-07/08):** Full campaign with `--reasoning-budget 0` and `--patch-think-tag-strip` via `run_campaign.py`. Brain models (26B-A4B l100, 31B l100) scored strongly — GSM8K 0.95, BBH ~0.84, DROP ~0.79. Competitive with Qwen3.6 on reasoning. E2B (l50) weak across the board (BBH 0.14, DROP 0.05). **E4B l50 failed** — runtime crashed at 35/50 GSM8K (transient llama-server crash on 1060). E4B l10 scores (0.60/0.08/0.31) retained as best available; needs re-run.

## bench-knowledge (lm-eval loglikelihood)

All at limit 5. High variance at this sample size. Excluded from default campaigns.

| Model | mmlu | arc_challenge | hellaswag | truthfulqa_mc2 | boolq | Date |
| --- | --- | --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | 0.270 | 0.20 | 0.40 | 0.200 | 0.20 | 2026-03-13 |
| `Qwen2.5-Coder-32B` | 0.270 | 0.20 | 0.40 | 0.200 | 0.20 | 2026-03-14 |

---

## Archived Model Scores

Historical scores for models no longer actively tested. See [MODEL_LIBRARY.md](MODEL_LIBRARY.md) for archive reasons.

### bench-pipeline (archived)

| Model | json_schema | cmd_safety | ambiguity | tool_plan | orch_tradeoff | long_ctx | Date |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Mistral-7B-v0.3` | 23.1% | 83.3% | 46.2% | 80.0% | 83.3% | 100% | 2026-03-11 |
| `DeepSeek-R1-7B` | 15.4% | 58.3% | 0% | 73.3% | 33.3% | incomplete | 2026-03-11 |
| `Qwen3.5-4B` | 15.4% | 100% | 30.8% | 93.3% | 58.3% | 100% | 2026-03-15 |
| `Qwen3.5-9B` | 38.5% | 91.7% | 53.8% | 93.3% | 75.0% | 100% | 2026-03-15 |
| `Qwen3-1.7B` | — | — | — | — | — | — | 6/6 stages |
| `Phi-4-mini` | — | — | — | — | — | — | 6/6 stages |
| `Gemma-3-4B` | — | — | — | — | — | — | 6/6 stages |
| `DeepSeek-R1-14B` | 7.7% | 8.3% | 0% | 80.0% | failed | 78.6% | 2026-03-14 |
| `Gemma-3-12B` | 0% | 58.3% | 53.8% | 93.3% | 75.0% | 92.9% | 2026-03-14 |
| `DeepSeek-R1-32B` | 0% | 8.3% | 0% | 80.0% | 8.3% | 85.7% | 2026-03-15 |
| `Qwen3.5-35B-A3B` | 23.1% | 100% | 38.5% | 93.3% | 83.3% | 100% | 2026-03-15 |

### bench-code (archived)

| Model | humaneval (base/plus) | mbpp (base/plus) | Date |
| --- | --- | --- | --- |
| `Mistral-7B-v0.3` | 44.5% / 37.8% | 49.7% / 42.1% | 2026-03-11 |
| `DeepSeek-R1-7B` | 4.9% / 4.9% | 19.3% / 19.6% | 2026-03-11 |
| `Qwen3.5-4B` | 37.8% / 36.6% | 65.6% / 56.1% | 2026-03-11 |
| `Qwen3.5-9B` | 40.2% / 39.0% | 67.7% / 58.2% | 2026-03-12 |
| `DeepSeek-R1-14B` | 6.1% / 6.1% | 22.2% / 20.9% | 2026-03-14 |
| `Qwen3.5-35B-A3B` | 90.9% / 87.2% | 86.2% / 72.2% | 2026-03-15 |
| `Qwen3-1.7B` | 5.5% / 5.5% | 21.7% / 20.4% | 2026-03-17 |
| `Phi-4-mini` | 71.3% / 64.0% | 54.0% / 48.4% | 2026-03-17 |
| `Gemma-3-4B` | 67.7% / 60.4% | 77.0% / 65.9% | 2026-03-17 |

### bench-reasoning (archived)

| Model | gsm8k | bbh | drop (f1) | Limit | Date |
| --- | --- | --- | --- | --- | --- |
| `Mistral-7B-v0.3` | 0.48 | 0.5393 | 0.126 | 100 | 2026-03-13 |
| `DeepSeek-R1-7B` | 0.08 | 0.0 | 0.0 | 100 | 2026-03-12 |
| `Qwen3.5-4B` | 0.80 | failed (SWA) | failed (SWA) | 5 | 2026-03-15 |
| `Qwen3.5-9B` | 0.80 | failed (SWA) | failed (SWA) | 5 | 2026-03-15 |
| `DeepSeek-R1-14B` | 0.0 | 0.5852 | 0.0 | 5 | 2026-03-16 |
| `Gemma-3-12B` | 0.60 | failed (OOM) | failed (OOM) | 5 | 2026-03-14 |
| `Qwen3-8B` | 0.90 | 0.6244 | 0.3848 | 50 | 2026-03-15 |
| `Qwen3-1.7B` | 0.44 | 0.0 | 0.1661 | 100 | 2026-03-18 |
| `Phi-4-mini` | 0.70 | — | — | 100 | 2026-03-18 |
| `Gemma-3-4B` | 0.80 | 0.5481 | 0.266 | 5 | 2026-03-17 |

### bench-knowledge (archived)

| Model | mmlu | arc_challenge | hellaswag | truthfulqa_mc2 | boolq | Date |
| --- | --- | --- | --- | --- | --- | --- |
| `Mistral-7B-v0.3` | 0.593 | 0.60 | 0.80 | 0.671 | 0.80 | 2026-03-13 |
| `DeepSeek-R1-7B` | 0.618 | 0.20 | 0.40 | 0.644 | 0.80 | 2026-03-13 |
