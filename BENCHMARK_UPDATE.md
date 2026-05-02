# Benchmark Update

Purpose: document the current benchmark split between small local model evaluation,
frontier agentic benchmarks, and cloud-model reference data, and define what to
add next without losing the value of the existing local suites.

This is a planning and taxonomy document, not a score ledger.

Use this with:
- [README.md](README.md)
- [MODEL_LIBRARY.md](MODEL_LIBRARY.md)
- [custom_tasks/README.md](custom_tasks/README.md)
- [docker/README.md](docker/README.md)

---

## Short Answer

The benchmark stack should not be replaced wholesale.

Keep:
1. the smaller local-model suites
2. the rig-specific custom tests
3. the current coding/reasoning/knowledge split

Add:
1. a newer agentic coding layer
2. a newer terminal-agent layer
3. optional cloud-only reference rows for models we do not run locally

The old benchmarks are still useful. They are just no longer sufficient by
themselves for frontier agent comparisons.

---

## Benchmark Layers

The current and near-term benchmark stack should be thought of in three layers.

### 1. Small Local Model Layer

This is the default layer for local GGUF models on constrained hardware.

Primary use:
1. compare many small and mid-size local models cheaply
2. catch formatting/reliability failures quickly
3. estimate practical model usefulness on the rig

Main benchmark families:
1. `gsm8k`
2. `bbh`
3. `drop`
4. `math_500`
5. `aime_2024`
6. `mmlu`
7. `arc_challenge`
8. `hellaswag`
9. `boolq`
10. `piqa`
11. `winogrande`
12. `truthfulqa_mc2`
13. `humaneval_plus`
14. `mbpp_plus`
15. local custom reliability tests

Current suite mapping:
1. `bench-pipeline`
2. `bench-code`
3. `bench-reasoning`
4. `bench-knowledge`

Why keep this layer:
1. cheap to run
2. works on 6 GB worker paths
3. good for broad model screening
4. good for prompt/runtime compatibility debugging
5. good for repeated regression checks

---

### 2. Frontier Agentic Layer

This layer captures what newer frontier vendors are increasingly optimizing for.

Primary use:
1. evaluate long-horizon coding
2. evaluate agentic tool use
3. evaluate terminal-based execution
4. better reflect real autonomous workflow performance

Main benchmark families:
1. `LiveCodeBench`
2. `SWE-bench Verified`
3. `SWE-Bench Pro`
4. `Terminal-Bench 2.0`
5. `BFCL`
6. optional web-agent benchmarks like `BrowseComp`

Why this layer matters:
1. cloud frontier model launches increasingly cite these benchmarks
2. older academic sets miss long-horizon execution behavior
3. code generation alone is no longer enough to characterize agent quality

Why this layer is harder:
1. heavier harness requirements
2. more runtime/tooling complexity
3. more expensive runs
4. less suitable as the default "run on every local model" path

---

### 3. Cloud Reference Layer

This is not a runnable local suite. It is a reference layer for vendor-published scores.

Primary use:
1. rough positioning against frontier cloud models
2. sanity-checking whether local results are competitive in a narrow band
3. tracking what external vendors are using as headline evaluations

Examples:
1. `Gemini 3 Pro`
2. `Gemini 3.1 Pro`
3. `GPT-5.3-Codex`
4. `GPT-5.4`
5. `Claude Sonnet 4.5`
6. `Claude Sonnet 4.6`
7. `Claude Opus 4.5`

Important rule:
1. keep vendor-published rows distinct from rig-run rows

---

## What Small Local Models Mostly Use

For local worker-tier models, the benchmark mix should remain mostly:
1. classic generation and reasoning tasks
2. classic MC/loglikelihood tasks
3. EvalPlus-style coding tasks
4. custom local acceptance tests

This is still the correct default for:
1. 1B to 14B local models
2. frequent reruns
3. debugging runtime quirks
4. model selection for real rig workloads

Do not force every small local model through the newest agentic benchmark stack.
That is expensive and usually low-yield early in model screening.

---

## What Frontier Cloud Models Mostly Use Now

Recent public vendor materials increasingly emphasize:
1. `SWE-bench Verified`
2. `SWE-Bench Pro`
3. `Terminal-Bench 2.0`
4. `LiveCodeBench Pro`
5. `BrowseComp`
6. `GPQA Diamond`
7. `Humanity's Last Exam`

This does not mean the local stack is wrong.
It means the benchmark field has split:
1. lighter screening and capability probes
2. heavier agentic end-to-end evaluations

We should support both.

---

## Recommended Update Policy

### Keep As Core

Keep these as the default baseline stack:
1. `bench-pipeline`
2. `bench-code`
3. `bench-reasoning`
4. `bench-knowledge`

These are still the cheapest and most operationally useful first pass.

### Add As Frontier Extensions

Add these incrementally:
1. `LiveCodeBench`
2. `SWE-bench Verified`
3. `SWE-Bench Pro`
4. `Terminal-Bench 2.0`
5. `BFCL`

Suggested order:
1. `LiveCodeBench`
2. `SWE-bench Verified`
3. `Terminal-Bench 2.0`
4. `SWE-Bench Pro`
5. `BFCL`

Reason:
1. `LiveCodeBench` is the easiest next extension of the current coding focus
2. `SWE-bench Verified` is highly relevant and more comparable than jumping straight to Pro
3. `Terminal-Bench 2.0` is useful but heavier operationally
4. `SWE-Bench Pro` is very valuable, but expensive enough that it should not be the first local addition
5. `BFCL` matters for tool calling, but is less urgent than code and terminal-agent coverage

### Keep Separate

Keep these separate from the default worker campaigns:
1. `BrowseComp`
2. cloud-only vendor reference rows
3. browser-use or web-agent benchmarks that assume external browsing infrastructure

---

## Comparison Bridge Benchmarks

If the goal is to compare local models to cloud frontier models using public data,
the best "bridge" benchmarks are the ones that satisfy both:

1. enough vendors publish them officially
2. they are close enough to the capabilities we care about locally

Best bridge set right now:
1. `GPQA Diamond`
2. `LiveCodeBench Pro`
3. `SWE-bench Verified`
4. `SWE-Bench Pro`
5. `Terminal-Bench 2.0`
6. `BrowseComp`
7. `MMMU-Pro`
8. `OSWorld-Verified`

Why these are the best bridge benchmarks:
1. `GPQA Diamond` is the strongest widely published reasoning/knowledge bridge
2. `LiveCodeBench Pro` is the strongest published coding bridge
3. `SWE-bench Verified` and `SWE-Bench Pro` are the strongest agentic coding bridges
4. `Terminal-Bench 2.0` is the strongest command-line agent bridge
5. `BrowseComp` is a strong web-agent bridge
6. `MMMU-Pro` and `OSWorld-Verified` help with broader tool/multimodal/computer-use positioning

Why the older local core does not bridge as well:
1. vendors rarely headline `HumanEval`, `MBPP`, `GSM8K`, `BBH`, `DROP`, `MMLU`, or `HellaSwag` anymore
2. even when they do, methodology often differs enough that comparison is weak
3. the newer public model launches are increasingly centered on agentic benchmarks instead

### Vendor-published bridge matrix

These are source-backed public numbers from official vendor pages. They are not rig-run scores.

Important caution:
1. vendor-published scores are often optimistic
2. vendors may run multiple scaffolds, prompts, tool settings, or effort levels and report the strongest result
3. some published rows use special harness settings or proprietary scaffolding that we do not replicate locally
4. published cloud scores should be treated as upper-bound marketing references, not neutral one-shot baselines
5. when comparing to local runs, assume a favorable bias toward the vendor's own reported number unless methodology is proven equivalent

| Model | GPQA Diamond | LiveCodeBench Pro | SWE-bench Verified | SWE-Bench Pro | Terminal-Bench 2.0 | BrowseComp | MMMU-Pro | OSWorld-Verified |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Gemini 3 Pro` | `91.9%` | `2439` Elo | `76.2%` | `43.3%` | `56.9%` | `59.2%` | `81.0%` | — |
| `Gemini 3.1 Pro` | `94.3%` | `2887` Elo | `80.6%` | `54.2%` | `68.5%` | `85.9%` | `80.5%` | — |
| `GPT-5.3-Codex` | — | — | — | `56.8%` | `77.3%` | — | — | `74.0%` |
| `GPT-5.4` | `92.8%` | — | — | `57.7%` | `75.1%` | `82.7%` | `81.2%` (no tools) / `82.1%` (with tools) | `75.0%` |
| `Claude Sonnet 4.5` | — | — | `77.2%` | — | — | — | — | `61.4%` |
| `Claude Sonnet 4.6` | `89.9%` | — | `79.6%` | — | `59.1%` | `74.7%` | `74.5%` | — |
| `Claude Opus 4.5` | — | — | relative-only public claim | — | relative-only public claim | — | — | — |

### Source-backed notes

#### Gemini 3 Pro / Gemini 3.1 Pro

Google DeepMind's `Gemini 3.1 Pro` comparison page is currently the single best public source because it includes:
1. `Gemini 3 Pro`
2. `Gemini 3.1 Pro`
3. `Claude Sonnet 4.6`
4. `Claude Opus 4.6`
5. `GPT-5.2`
6. `GPT-5.3-Codex`

This is the best current public bridge source for:
1. `GPQA Diamond`
2. `LiveCodeBench Pro`
3. `SWE-bench Verified`
4. `SWE-Bench Pro`
5. `Terminal-Bench 2.0`
6. `BrowseComp`
7. `MMMU-Pro`

#### GPT-5.4

OpenAI's `GPT-5.4` release page is the best current official source for:
1. `GPQA Diamond`
2. `SWE-Bench Pro`
3. `Terminal-Bench 2.0`
4. `BrowseComp`
5. `MMMU Pro`
6. `OSWorld-Verified`

#### Claude Sonnet 4.5

Anthropic's `Claude Sonnet 4.5` release page gives exact public text for:
1. `SWE-bench Verified` leadership claim
2. `OSWorld` at `61.4%`

This is useful, but it is still a weaker bridge source than Google's comparison page or OpenAI's GPT-5.4 page because fewer exact benchmark rows are exposed in text.

#### Claude Sonnet 4.6

For `Claude Sonnet 4.6`, the strongest bridge data comes from:
1. Anthropic's release notes and footnotes
2. Google's `Gemini 3.1 Pro` comparison page

This gives exact public rows for:
1. `GPQA Diamond`
2. `SWE-bench Verified`
3. `Terminal-Bench 2.0`
4. `BrowseComp`
5. `MMMU-Pro`

#### Claude Opus 4.5

`Claude Opus 4.5` still has a public-data gap.

What Anthropic publicly states clearly in text:
1. it is state-of-the-art on real-world software engineering at release
2. at highest effort, it exceeds `Claude Sonnet 4.5` on `SWE-bench Verified` by `4.3` points
3. on Warp's evaluation, it improves `Terminal Bench` by `15%` over `Claude Sonnet 4.5`

What is missing:
1. a clean public text table with exact values across the same bridge benchmarks used by Google and OpenAI

Operational rule:
1. keep `Claude Opus 4.5` in bridge docs, but mark it as relative-claim-only until Anthropic exposes exact rows in a text-accessible public source

### What this means for our local suite updates

If we want better cloud comparison without abandoning the local lightweight stack:
1. keep the current local core for screening
2. add `GPQA Diamond` as the best reasoning bridge
3. add `LiveCodeBench` as the best coding bridge
4. add `SWE-bench Verified` as the best agentic coding bridge
5. add `Terminal-Bench 2.0` as the best terminal-agent bridge

That gives us a realistic mixed stack:
1. local cheap baselines
2. modern cloud-comparable bridges
3. custom rig-specific validation

### Source links

- Google DeepMind:
  - `Gemini 3.1 Pro`: https://deepmind.google/models/gemini/pro/
- OpenAI:
  - `GPT-5.4`: https://openai.com/index/introducing-gpt-5-4/
  - `GPT-5.3-Codex`: https://openai.com/index/introducing-gpt-5-3-codex/
- Anthropic:
  - `Claude Sonnet 4.5`: https://www.anthropic.com/news/claude-sonnet-4-5
  - `Claude Sonnet 4.6`: https://www.anthropic.com/research/claude-sonnet-4-6
  - `Claude Opus 4.5`: https://www.anthropic.com/news/claude-opus-4-5

---

## Community And Third-Party Comparison Sources

Official vendor pages are not enough by themselves.

We should also track community and third-party benchmark sources because they can:
1. expose benchmarks vendors do not headline
2. compare models side by side under one outside methodology
3. provide fresher leaderboard-style updates
4. give us more overlap between local models and cloud models

Important caution:
1. community sources vary widely in rigor
2. some are true independent benchmarks
3. some are secondary aggregators that repackage vendor numbers
4. some are useful only as weak signals, not score-of-record data

### Recommended source tiers

#### Tier 1: strongest community / independent sources

Use these first.

1. `Artificial Analysis`
   - why it matters:
     - independent, recurring evaluation program
     - cross-model comparisons under one methodology
     - good coverage of frontier cloud models
   - especially useful for:
     - `GPQA Diamond`
     - `Humanity's Last Exam`
     - `Terminal-Bench Hard`
     - coding and agentic composite indices
   - examples:
     - Artificial Analysis Intelligence Index: https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index
     - model comparison pages such as `Gemini 3.1 Pro Preview vs Claude Sonnet 4.6`: https://artificialanalysis.ai/models/comparisons/claude-sonnet-4-6-adaptive-vs-gemini-3-1-pro-preview

2. `SWE-rebench`
   - why it matters:
     - community-run, fresh SWE-style benchmark
     - tracks newer frontier models side by side
     - useful when official SWE-bench numbers are sparse or outdated
   - especially useful for:
     - coding-agent comparisons
     - cloud model ranking updates after release
   - source:
     - https://swe-rebench.com/

3. `LiveBench`
   - why it matters:
     - independent benchmark family with regular refreshes
     - useful for contamination-resistant broad capability comparisons
   - especially useful for:
     - general frontier-model tracking
     - another bridge signal beyond vendor self-reporting
   - source:
     - https://livebench.ai/

#### Tier 2: useful aggregators

These are useful for gathering rows quickly, but they should not be treated as primary evidence unless they clearly cite the underlying source.

1. `BenchLM`
   - why it matters:
     - convenient cross-benchmark model pages
     - often combines vendor data and third-party references in one place
   - use:
     - discovery and cross-checking
   - source:
     - https://benchlm.ai/

2. `AgentMarketCap` and similar analysis sites
   - why they matter:
     - sometimes summarize Artificial Analysis or other leaderboard data well
   - use:
     - directional context only
   - source example:
     - https://agentmarketcap.ai/blog/2026/04/09/april-2026-frontier-model-convergence-gpt-gemini-claude-benchmark

#### Tier 3: weak-signal sources

Use these only for ideas, not canonical scoring.

1. `LM Arena` / `WebDev Arena`
   - useful for:
     - preference and interactive quality
     - web-dev task preference
   - not the same as a reproducible benchmark suite
   - sources:
     - https://lmarena.ai/
     - https://web.lmarena.ai/leaderboard

2. forum posts and Reddit benchmark threads
   - useful for:
     - spotting new runs quickly
     - finding harnesses and unexplored comparisons
   - not acceptable as score-of-record without underlying evidence

### Practical collection rule

When adding community rows to our docs, label them explicitly as one of:
1. `vendor-published`
2. `independent benchmark`
3. `third-party aggregator`
4. `community run / provisional`

That prevents accidental mixing of:
1. hard local results
2. vendor marketing rows
3. independent outside runs
4. unverified social-media claims

### What community sources can help us add next

The most promising community additions for better cloud comparison are:
1. `Artificial Analysis Intelligence Index` rows
2. `Artificial Analysis Coding Index` rows
3. `SWE-rebench` leaderboard rows
4. `LiveBench` leaderboard rows

These will likely give us more usable comparison coverage than trying to find
vendor-published `HumanEval`, `MBPP`, `GSM8K`, or `BBH` for every cloud model.

---

## Canonical Comparison Table

We should keep one flat spreadsheet-friendly comparison table in the repo.

Recommended file:
1. `results/benchmark_comparison_table.csv`

Purpose:
1. one sortable sheet for local, vendor, independent, and provisional rows
2. easy import into LibreOffice, Excel, or Google Sheets
3. avoid forcing markdown tables to act like a database

Recommended columns:
1. `model`
2. `benchmark`
3. `score`
4. `metric`
5. `source_type`
6. `source_name`
7. `run_scope`
8. `methodology_note`
9. `date`
10. `url`

Allowed `source_type` values:
1. `local_rig_run`
2. `vendor_published`
3. `independent_benchmark`
4. `community_run_provisional`

Allowed `run_scope` values:
1. `local`
2. `cloud`
3. `mixed_reference`

---

## Upgrade Trigger Framework

The hardware upgrade decision should not be based on subscription cost alone.

For this repo, the trigger should be defined as a three-checkpoint gate:

### Checkpoint A: Cloud Bridge Proximity

A local model becomes a serious upgrade candidate when it is clearly closing the
gap to the cloud checkpoint models on the bridge benchmarks we actually track.

Primary cloud checkpoints:
1. `Claude Sonnet 4.6`
2. `Claude Opus 4.5`
3. `GPT-5.4`
4. `GPT-5.3-Codex`
5. `Gemini 3.1 Pro`

Primary bridge benchmarks for this purpose:
1. `GPQA Diamond`
2. `LiveCodeBench Pro`
3. `SWE-bench Verified`
4. `SWE-Bench Pro`
5. `Terminal-Bench 2.0`

Interpretation rule:
1. do not wait for strict parity on every benchmark
2. look for a local model that enters the same practical band on the tests that matter most for our workflow
3. treat this as a checkpoint, not proof of full cloud replacement

### Checkpoint B: Real Session Feel

Benchmarks are not enough.

A model that looks good on paper still may not feel good in practice because of:
1. verbosity drift
2. poor instruction obedience
3. weak formatting discipline
4. brittle edit behavior
5. annoying refusal or think-tag behavior

The upgrade trigger should therefore require a local model to pass repeated real
coding sessions well enough that we would actually choose it for daily use.

Practical test:
1. use the candidate local model as the primary assistant for several real sessions
2. include boring operational work, not just curated coding prompts
3. record whether the experience is merely impressive or genuinely comfortable

### Checkpoint C: Hardware Constraint

Even if model quality is close enough, a hardware purchase still should not be
triggered until the current rig is the limiting factor.

The actual signal is:
1. the candidate model is good enough to want as a primary local model
2. the current hardware does not fit it comfortably at the context size we want
3. the next useful step requires a larger memory pool, not just more tweaking

Operational interpretation:
1. if the current `3090 Ti` still serves the best local model comfortably enough, wait
2. if the next serious local candidate wants more memory or more context headroom than the `3090 Ti` can provide, that is the real purchase trigger

### Trigger Rule

Only treat a major hardware upgrade as justified when all three are true:
1. `Checkpoint A` is true
2. `Checkpoint B` is true
3. `Checkpoint C` is true

This prevents buying hardware too early just because the trend line is encouraging.

---

## Real Session Evaluation Layer

We should add a lightweight subjective evaluation layer to complement the formal
benchmark suite.

Purpose:
1. capture what it actually feels like to work with a local model
2. distinguish "benchmarks well" from "pleasant to use for hours"
3. create an operator-facing signal for when local models are ready to replace more cloud time

This is not a replacement for benchmark suites.
It is a thin practical layer on top of them.

### Suggested Session Tasks

Use a small repeatable task set based on real repo work:
1. repo navigation and codebase understanding
2. bug fix or patch task
3. code review / QA process task
4. script-following or data import task
5. strict output / JSON / formatting obedience task

These are intentionally closer to everyday use than pure benchmark prompts.

### Suggested Session Ratings

For each serious candidate model, record short operator notes for:
1. `session_feel`
2. `verbosity_control`
3. `instruction_obedience`
4. `format_obedience`
5. `code_edit_reliability`
6. `annoyance_level`
7. `would_use_for_2h`

Rating rule:
1. short notes are better than elaborate prose
2. the point is to track whether a model is pleasant and stable enough for real use
3. the most important field is whether we would willingly use the model for an extended real session

### Session-Layer Outcome Rule

Do not call a model "cloud-adjacent in practice" unless:
1. it looks competitive on the bridge benchmarks
2. it also passes the real-session layer with acceptable operator feel

This keeps us from over-weighting benchmark gains that do not translate into actual workflow value.
2. `cloud`
3. `vendor`
4. `third_party`

Operational rules:
1. markdown docs remain narrative/operator references
2. JSONL remains the append-only local run ledger
3. the CSV is the human-sortable comparison sheet
4. do not mix source types without labeling them explicitly
5. use one row per model-benchmark-result claim

Initial seeding plan:
1. seed the CSV with the cloud bridge rows already collected from official sources
2. later add independent benchmark rows from `Artificial Analysis`, `SWE-rebench`, and `LiveBench`
3. later add curated local bridge rows as we run overlapping benchmarks locally

---

## Practical Suite Taxonomy

The suite taxonomy should become:

### Baseline local suites

1. `bench-pipeline`
2. `bench-code`
3. `bench-reasoning`
4. `bench-knowledge`

### Frontier local extensions

1. `bench-livecodebench`
2. `bench-swebench-verified`
3. `bench-terminal`
4. optional later `bench-swebench-pro`
5. optional later `bench-bfcl`

### Reference-only layer

1. vendor-published cloud rows in `MODEL_LIBRARY.md`

This split keeps the benchmark repo usable for both:
1. practical local hardware benchmarking
2. awareness of where the wider model ecosystem has moved

---

## What Not To Do

Do not:
1. delete the older suites because cloud vendors cite newer ones
2. force every small model through heavy agentic suites
3. mix vendor-published cloud rows into local machine-generated ledgers without labeling
4. collapse custom reliability tests into generic public benchmarks

The custom tests still matter because they measure real rig behavior that public
leaderboards do not.

---

## Next Actions

Recommended near-term actions:
1. keep the existing local benchmark campaigns as the default path
2. add `LiveCodeBench` as the first new frontier extension
3. add `SWE-bench Verified` next
4. document `Terminal-Bench 2.0` as planned but not default
5. keep cloud model reference rows in `MODEL_LIBRARY.md`

If we follow that plan, the benchmark stack stays:
1. cheap enough for local model screening
2. relevant enough for current frontier comparisons
3. explicit about what is local, agentic, and cloud-reference only

---

## Custom-to-Standard Benchmark Mapping Goal

We also want the benchmark stack to support prediction, not just ranking.

Goal:
1. find which public benchmark families best predict performance on our custom rig tasks
2. use vendor-published cloud results as prior signals for likely custom-suite behavior
3. reduce the need to run every expensive custom suite on every candidate model

This matters because the custom suites are measuring behavior we actually care about:
1. strict JSON discipline
2. command safety
3. ambiguity handling
4. tool/plan sequencing
5. orchestration tradeoff reasoning
6. long-context extraction

The public benchmarks do not measure those directly, but some of them may correlate well enough to be operationally useful.

### Working hypothesis

Expected likely relationships:
1. `BFCL` and tool-use benchmarks may predict `custom_tool_plan_sequence`
2. `Terminal-Bench 2.0` may predict `custom_command_safety` and `custom_tool_plan_sequence`
3. `BrowseComp` and long-context/search tasks may predict `custom_long_context_extract`
4. `GPQA Diamond`, `BBH`, and stronger reasoning benchmarks may partially predict `custom_orchestration_tradeoff`
5. coding-agent benchmarks may predict some planning reliability, but probably weakly for JSON discipline
6. older reasoning/knowledge tasks may be poor predictors for exact-format and safety behavior

These are hypotheses only until we test them against actual results.

### Recommended analysis approach

Build a simple crosswalk table with rows like:
1. model
2. standard benchmark score
3. custom benchmark score
4. prompt/runtime notes
5. known formatting pathologies

Then evaluate:
1. pairwise correlations
2. rank correlations
3. obvious failure clusters
4. cases where public scores are strong but custom scores are weak
5. cases where small local models outperform expectation on rig-specific tasks

### Important warning

Do not assume that stronger public benchmarks imply stronger custom-task performance.

Known failure modes:
1. strong reasoning model with poor exact-format compliance
2. strong coding model with weak command safety
3. strong benchmark model with `<think>` or formatting artifacts that break harnesses
4. strong cloud-agent score with poor local-runtime behavior on constrained hardware

### Practical outcome we want

If this works, we should be able to say things like:
1. "models with strong `BFCL` and `Terminal-Bench 2.0` scores are likely worth trying on `custom_tool_plan_sequence`"
2. "models with high `GPQA Diamond` but weak tool-use scores are unlikely to excel at orchestration tasks"
3. "models with only coding benchmark strength are not enough for command-safety or ambiguity-heavy workflows"

That would turn the custom suite from a pure measurement system into a selection aid.
