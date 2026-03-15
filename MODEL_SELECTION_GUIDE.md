# Model Selection Guide

How to pick which models are worth testing on our rig, and how to pre-screen them fast.

## Philosophy

We don't need to test every model. The community and cloud providers already run standard benchmarks at scale. Use their results as a first filter, then only pull GGUFs for models that look promising. Our custom pipeline/code/reasoning tests validate fitness for *our specific use case* — that's the value we add on top of public scores.

## Step 1: Check Public Benchmarks Before Downloading

These sources publish standardized scores across many models. Use them to shortlist candidates.

### Active Leaderboards (verified Q1 2026)

| Source | URL | What it covers | Why use it |
|---|---|---|---|
| Chatbot Arena (LMArena) | https://huggingface.co/spaces/lmarena-ai/arena-leaderboard | Human preference Elo ratings | Updated daily, 6M+ votes. Best signal for "does this model actually work well." Filter by category (coding, math, etc). |
| LiveBench | https://livebench.ai | Math, coding, reasoning, language, instruction following, data analysis | Contamination-free — new questions monthly. Hard benchmark, top models < 70%. Best for honest comparison. |
| LiveCodeBench | https://livecodebench.github.io/leaderboard.html | Code generation, contamination-free | Most relevant to our bench-code suite. Updated with fresh coding problems. |
| EvalPlus | https://evalplus.github.io/leaderboard.html | HumanEval+, MBPP+ | Direct comparison to our bench-code results. If a model scores below 40% on HumanEval+ here, skip it. Last evalplus release was late 2024 but leaderboard still has entries. |
| Onyx Self-Hosted LLM | https://onyx.app/self-hosted-llm-leaderboard | Open-weight models ranked for self-hosting | Most relevant to us — filters for models you can actually run locally on consumer hardware. |
| LLM-Stats | https://llm-stats.com | Aggregated scores across many benchmarks | Good for quick cross-benchmark comparison. Filterable by size, family. |
| Open WebUI Leaderboard | https://openwebui.com/leaderboard | Real usage rankings from 100K+ users | What people actually use day-to-day, not just synthetic benchmarks. |
| Vellum | https://vellum.ai/llm-leaderboard | Cross-provider model comparison | Updated Feb 2026. Quick overview of SOTA performance. |

### Retired / Stale (do not use)

| Source | Status |
|---|---|
| HuggingFace Open LLM Leaderboard | **Retired.** Officially shut down — benchmarks became obsolete as models evolved past them. 13,000+ models evaluated before closure. |
| BigCode Models Leaderboard | Last meaningful updates 2024. Superseded by LiveCodeBench. |

### Model Cards and Release Notes

Before downloading a GGUF, check:
- **HuggingFace model card** — most model authors publish their own benchmark scores, supported context lengths, chat template format, and known limitations
- **llama.cpp compatibility** — check the llama.cpp GitHub issues/discussions for the model family. Some architectures need specific llama.cpp versions or have known quantization issues
- **GGUF availability on HuggingFace** — search for `<model-name> GGUF` on HuggingFace. The bartowski and unsloth accounts publish well-tested quantizations for most popular models

### Quick Filters (Skip If)

Don't bother downloading a model if:
- HumanEval base score < 40% (won't be useful for code tasks)
- No chat template / instruction tuning (raw base models won't work with our pipeline)
- Architecture not supported by current llama.cpp (check ggml-org/llama.cpp supported models)
- Quantized GGUF not available in Q4_K_M or similar (we run 4-bit quants)
- Total parameter count doesn't fit our hardware: 7B-9B for single 1060 (6GB), 12B-14B for split pair (2x 6GB), 30B-35B for 3090 (24GB)

## Step 2: Check Prompt/Settings Info Before Testing

### Where to Find Recommended Settings

| Source | What it provides |
|---|---|
| HuggingFace model card `## Usage` section | Chat template, recommended temperature, system prompt examples |
| `tokenizer_config.json` in the HF repo | Exact chat template (Jinja2 format) — this is what llama.cpp uses |
| Ollama library (https://ollama.com/library) | Modelfile with default parameters, system prompt, template |
| llama.cpp `--verbose` output on first load | Shows detected chat template, BOS/EOS tokens, special tokens |
| Model author's GitHub/blog | Often has recommended inference settings, known failure modes |

### Key Settings to Capture Per Model

Before running any benchmark, record:
- **Chat template format**: ChatML (`<|im_start|>`), Llama-style (`[INST]`), Gemma-style (`<start_of_turn>`), etc.
- **Recommended temperature**: Most instruct models suggest 0.6-0.7 for general use, 0.0-0.1 for deterministic tasks
- **Context window**: Training context length vs. safe inference length (often different)
- **Known quirks**: `<think>` tag emission, markdown wrapping, verbose reasoning, etc.
- **Stop tokens**: Some models need explicit stop sequences beyond EOS

## Step 3: Fast Pre-Screen on the Rig (Before Full Suite)

### Litmus Test (< 2 minutes per model)

A quick script that sends 5 hardcoded prompts and checks basic competence.
Run this immediately after loading a model, before committing to full benchmarks.

**Tests:**
1. **JSON compliance**: "Return a JSON object with keys 'name' and 'age' for a 30-year-old named Alice. Return ONLY the JSON." → Check: response starts with `{`, is valid JSON, has correct keys
2. **Instruction following**: "Respond with exactly one word: the capital of France." → Check: response is "Paris" (1 word, no extras)
3. **Think tag leakage**: "What is 15 + 27? Give only the number." → Check: no `<think>` tags in output, response is "42"
4. **Format boundary**: "List three colors, one per line. No bullets, no numbers, no extra text." → Check: exactly 3 lines, no bullet characters
5. **Refusal compliance**: "Say only: I understand." → Check: response is exactly "I understand." or very close

**Scoring:**
- 5/5: Proceed to full pipeline smoke test
- 3-4/5: Proceed but flag likely structured output issues — may need prompt tuning
- 0-2/5: Model is not instruction-following enough for our pipeline — skip or heavily tune first

**Implementation:** TODO — write as a standalone script that takes `--runtime-base` and `--model` args, outputs pass/fail per test.
Script location (when built): `/media/bryan/shared/scripts/benchmarks/litmus_test.sh`

### Pipeline-Only First Pass (< 5 minutes)

If litmus passes, run `bench-pipeline` only. It's fast and covers our most important dimension (structured output compliance). Models scoring below 50% average across all 6 pipeline tests probably aren't worth the hours needed for code + reasoning.

## Step 4: Our Hardware Constraints (Model Size Guide)

| Tier | GPU(s) | VRAM | Max Model Size (Q4_K_M) | Current Models |
|---|---|---|---|---|
| Single worker | 1x 1060 6GB | 6 GB | ~7-9B | qwen2.5-coder:7b, mistral:7b, deepseek-r1:7b, qwen3.5:4b, qwen3.5:9b |
| Split worker | 2x 1060 6GB | 12 GB | ~12-14B | qwen2.5-coder:14b, deepseek-r1:14b, phi-4:14b, gemma-3:12b |
| Brain | 1x 3090 24GB | 24 GB | ~30-35B | qwen2.5-coder:32b, deepseek-r1:32b, qwen3.5:35b-a3b |

Rule of thumb: Q4_K_M quant uses ~0.6 GB per billion parameters for weights, plus KV cache overhead. A 14B Q4 model needs ~8.5 GB for weights + ~2-3 GB for ctx=8192 KV cache.

## Model Families Worth Watching (2026)

These families are actively releasing new versions. Check for new releases periodically.

| Family | Why | Size range | Notes |
|---|---|---|---|
| Qwen3.5 / Qwen3 | Strong instruction following, good code, active development | 4B-72B | Already have 4B, 9B, 35B-A3B. Watch for new instruct variants. |
| Llama 4 | Meta's latest, wide community support | 8B-70B+ | Check for Scout/Maverick variants that fit our hardware. |
| Gemma 3 | Google's latest small models, good efficiency | 2B-27B | Already have 12B. 27B might fit brain tier. |
| Phi-4 | Microsoft, strong for size, good structured output | 3.8B-14B | Already have 14B. |
| DeepSeek V3/R2 | Strong reasoning, code | 7B-70B+ | Watch for non-distilled variants with better output formatting. |
| Mistral / Mixtral | Good general purpose, strong instruction following | 7B-8x22B | Current 7B is v0.3, newer versions may be available. |
| Command R+ | Cohere, designed for tool use and RAG | 35B-104B | 35B might fit brain tier. Specifically designed for tool calling. |

## Download Queue

### Downloaded (on `/mnt/shared/models/`)

| Model | GGUF | Size | Tier | Status |
|---|---|---|---|---|
| Qwen3.5-27B | `Qwen3.5-27B-Q4_K_M.gguf` | 16.7 GB | brain (3090) | downloading |
| Devstral Small 2 24B | `Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf` | 14.3 GB | brain (3090) | downloading |
| Qwen3-14B | `Qwen3-14B-Q4_K_M.gguf` | 9 GB | split (2x 1060) | downloading |
| Qwen3-8B | `Qwen3-8B-Q4_K_M.gguf` | 5 GB | single (1x 1060) | downloading |

### Future Additions (not yet downloaded)

| Model | GGUF Source | Size (est) | Tier | Why |
|---|---|---|---|---|
| Gemma 3 27B | `bartowski/google_gemma-3-27b-it-GGUF` | ~15 GB Q4 | brain (3090) | Full-power version of our split-tier Gemma 3 12B. Strong general purpose. Already have the 12B — 27B is the natural upgrade for brain tier. |
| Qwen3-32B | `Qwen/Qwen3-32B-GGUF` | ~19 GB Q4 | brain (3090) | Direct successor to Qwen2.5-Coder-32B (current best brain model). Should be strictly better on coding and reasoning. Lower priority since Qwen3.5-27B is newer. |

## Decision Flow

```
1. See interesting model on leaderboard
2. Check: does it fit our hardware? (size filter)
3. Check: is a GGUF Q4_K_M available?
4. Check: public HumanEval > 40%? Public MMLU reasonable for size?
5. Check: chat template supported by llama.cpp?
   |
   v
6. Download GGUF, load on appropriate GPU tier
7. Run litmus test (2 min)
8. Run bench-pipeline (5 min)
9. If pipeline average > 50%: run bench-code + bench-reasoning (limit 5)
10. If scores competitive with existing models: add to MODEL_LIBRARY.md, run full suite
```
