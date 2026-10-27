# New Model Integration Playbook

The process for taking a new model from download to published scores (Part 1, current), and the log of
past integrations (Part 2, history). Rewritten 2026-10-23 for how the rig runs now: every load goes
through the rig manager (llm-gateway), Phases 2-4 run as a lane, and Phase 5 as a campaign, both
started as runs in the rig's report.

What is current where:
- How a model loads and which settings it uses: [model_registry.json](model_registry.json) (the one
  source of truth), resolved by [scripts/active/model_library.py](scripts/active/model_library.py).
  Which model each job uses: [model_roles.json](model_roles.json).
- Scores: [results/MODEL_BENCHMARK_REFERENCE.md](results/MODEL_BENCHMARK_REFERENCE.md) and
  `results/model_library_scoreboard.json`, regenerated on every recorded result.
- Model choices, statuses and settings written in Part 2 are history; the registry wins where they differ.

Companion docs:
- [MODEL_LIBRARY.md](MODEL_LIBRARY.md): picking a model, prompt methodology
- [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md): per-model runtime notes
- [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md): debugging narratives
- [docker/README.md](docker/README.md): the suites; [scripts/integration/README.md](scripts/integration/README.md): the lane tools
- llm-gateway `docs/MANAGER.md`: model loads, fit, waits, runs (`rigctl`)

`rigctl` below is llm-gateway's `tools/rigctl.py`, run on the Pi (`python3 ~/llm-gateway/tools/rigctl.py`).
Commands it starts run on the rig, so their paths are the rig's (`/mnt/shared/...`).

---

# Part 1: Process Reference

## Overview

| Phase | What | How | Gate |
|-------|------|-----|------|
| 0 | Download | on the rig, to the NVMe hotset, then the shared library | download: size and SHA-256 match the source; library copy: size |
| 1 | Register | registry entry, `model_library.py export`, `rigctl fit` | `check` ok, `fit` says it fits |
| 2 | First load | the lane (`rigctl load-model` through the manager) | the model serves, every layer on the GPUs |
| 3 | Litmus | the lane (`litmus.py`) | the 3 checks pass, or each failure is documented |
| 3.5 | Runtime characterization | the lane (`runtime_char.py`) | a `results/runtime_experiments/` record |
| 4 | Smoke (limit 10) | the lane (`phase4.sh`) | every suite scores; raw answers read |
| 4.5 | Settings experiments (optional) | operator's choice after reading Phase 4: the lane's thinking A/B (`LANE_START_AT=4.5`), experiments by hand | each Phase 4 problem tried against the options that could fix it |
| 5 | Full run (limit 50 + full code) | a campaign | all blocks complete |
| 6 | Finalize | registry status and notes, integration log | the model is discoverable with its settings |
| - | Capacity run (any time after Phase 1) | `capacity_run.py` on chosen cards | a `results/runtime_experiments/` capacity record |

Phases 2-4 are one command (a lane), which stops after the smoke; Phase 4.5 is a separate, deliberate step; Phase 5 is one campaign. The manager does placement: say which cards
a lane uses, and it checks the fit and picks context and split.

### Philosophy: model settings, not suite changes

The goal is to see how a model works with our **existing suites** using only model-level settings (system
prompt, runtime args, registry profile). If a model has quirks with a suite, **document the limitation**
in the registry notes and the integration log, then move on.

Do not modify suite code for one model, add model-specific extraction, or build custom harnesses. Do tune
the system prompt, set runtime args (`extra_args` such as `--reasoning off`, `--jinja`), and use existing
suite flags. Harness changes are only for defects that hit every model (record them in the suite history
and version the rows, as extract v5 did: reasoning is scored leniently, a correct answer counts however it
is written, and answers that cannot be read at all are counted separately).

## Phase 0: Download

Download on the rig (it has its own internet route), straight to the NVMe hotset, resumable, renamed into
place only when complete:

```bash
ssh <rig-ip>
mkdir -p /data/model-hotset/<model-dir> && cd /data/model-hotset/<model-dir>
nohup bash -c 'curl -L -C - --retry 20 --retry-delay 10 -o <file>.gguf.part \
  https://huggingface.co/<org>/<repo>/resolve/main/<file>.gguf && mv <file>.gguf.part <file>.gguf && echo DONE' \
  > download.log 2>&1 < /dev/null &
```

Verify the download once, on the rig: the size, and the SHA-256 Hugging Face lists for the file
(`curl -s https://huggingface.co/api/models/<org>/<repo>/tree/main` gives `size` and `lfs.oid` per file).
Hash here, on the NVMe, where it is fast and puts no load on the Pi:

```bash
sha256sum /data/model-hotset/<model-dir>/<file>.gguf
```

The hash is the one check a load cannot replace: llama.cpp validates the header and tensor shapes, not the
weight bytes, so a corrupted chunk still loads and passes litmus and only shows up as skewed scores. Copies
made after this (the library copy below) get a size check only; Phase 2 loading the model is the
functional check.

Then copy it to the shared library, the archive every machine sees and the copy the manager's fit reads:

```bash
mkdir -p /mnt/shared/models/<model-dir>
cp /data/model-hotset/<model-dir>/<file>.gguf /mnt/shared/models/<model-dir>/<file>.gguf.part && \
  mv /mnt/shared/models/<model-dir>/<file>.gguf.part /mnt/shared/models/<model-dir>/<file>.gguf
```

Loads use the hotset copy when it exists (same relative path under `/data/model-hotset/`), the library
otherwise. Directory: lowercase-hyphenated model name (`gemma-4-12b`); keep the upstream file name.
Choosing a quant: leave room for context and the compute buffers on every card (`rigctl fit` in Phase 1
shows it); a slightly smaller quant that fits with headroom beats one that barely fits.

**Gate**: the hotset download matches the source size and SHA-256; the library copy matches the size.

## Phase 1: Register

Add one entry to `model_registry.json` (keyed by the short model id), then regenerate the derived files.
Never edit `models.catalog.json`, `model_tuning_profiles.json` or `custom_tasks/model_prompt_profiles.json`;
they are generated and `check` fails if they drift.

```json
"<short-id>": {
  "gguf": "<model-dir>/<file>.gguf",
  "source_url": "https://huggingface.co/<org>/<repo>/resolve/main/<file>.gguf",
  "status": "candidate",
  "schedule": {
    "tier": <1 single card, 2 split, 3 brain or capacity>,
    "placement": "<single_gpu|split_gpu>",
    "tags": ["<relevant>", "<tags>"]
  },
  "profiles": {
    "default": {
      "system_prompt": "<a prompt family below>",
      "inference": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 512},
      "runtime": {"ctx_size": <4096-8192 worker, 16384 brain>, "batch_size": <64 worker, 128 brain>,
                  "parallel": 1, "n_gpu_layers": 999},
      "extra_args": [],
      "tuning": {"status": "untuned", "last_tuned_at": null, "benchmark_suite": "agent_reliability"},
      "notes": "<what it is, why this quant, placement>"
    }
  }
}
```

`source_url` lets a lost model be fetched again (same model and quant; byte-identical not required).
Named variants (for example `thinking`, or a long-context `interactive` profile) go under `profiles`
next to `default` and list only what differs. A model whose template thinks by default and should not:
`"extra_args": ["--reasoning", "off"]` in `default`.

**Prompt families**:

| Family | When to use | Prompt |
|--------|-------------|--------|
| Worker (strict) | default for most models | `"You are a strict worker assistant. Follow instructions exactly and keep output minimal. When JSON is requested, return raw JSON only with no markdown or extra text."` |
| Thinking suppression | models that leak reasoning into the answer | `"You are a worker assistant. Never output <think> tags, chain-of-thought, or internal reasoning. Respond with only the final answer in the exact format requested. When JSON is requested, return raw JSON with no markdown or extra text. When a short answer is requested, give only that answer."` |
| Benchmark assistant | small models (3B and under) | `"You are a strict benchmark assistant. Think silently and output only the final answer. Never include reasoning, analysis, or extra text. For GSM8K-style math, end with exactly: #### <answer>. For BBH-style reasoning, end with exactly: So the answer is <answer>. For short reading-comprehension questions, output only the shortest final answer phrase."` |

A prompt that is mostly format rules can make a model answer everything in that format (phi-4:14b answered
every DROP question as JSON, 2026-10-22); keep format rules short.

Then:

```bash
python3 scripts/active/model_library.py export
python3 scripts/active/model_library.py check
python3 scripts/active/model_library.py model <short-id>
rigctl fit <short-id>                  # the harness picks the cards: ctx, split, MiB per card
rigctl fit <short-id> --gpus 1,2       # or for the cards a lane will use
```

**Gate**: `check` reports ok; `model <short-id>` resolves the expected GGUF and settings; `fit` says it
fits on the cards you intend to use, with headroom on every card.

## Phases 2-4: the lane

One command runs Phases 2 to 4 for a model on a card group, as a run in the rig's report (a reboot shows
it as interrupted and offers to resume it; MANAGER.md, "Runs"):

```bash
rigctl run-start --run lanes-<slug> -- /bin/bash \
  /mnt/shared/plans/shoulders/benchmarking/scripts/integration/run_worker_lanes.sh <group> <short-id>
```

`<group>` is the cards: `0` (the 3090), `1` (one 1060), `1+2` (a 1060 pair), `0+1+2+3+4+5` (every card,
for capacity models). Several groups and models in one command share a queue: `run_worker_lanes.sh 0,1+2
modelA modelB`. Options (`--env K=V` on run-start): `LANE_STOP_AFTER=3` (stop after litmus),
`LANE_START_AT=4.5` (the thinking A/B, started by the operator after reading the smoke, for a model whose
Phases 2-4 already ran), `LANE_RUN_SUFFIX=_r2` (fresh run names for a re-run after a settings fix).

The lane claims its cards for its whole run, then for each model:

| Phase | What the lane does | Where the output goes |
|---|---|---|
| 2 | `rigctl load-model <id> --gpus <group> --use benchmark --wait`: the manager fits it, the rig loads it and refuses a load not fully on the GPUs | lane log: profile, ctx, split, VRAM per card, the end of the chat template |
| 3 | `litmus.py`: 15 x 37 (expect 555, no think tags), a JSON object, a Python function | lane log and `/mnt/shared/logs/benchmarks/phase3_<run>_litmus.txt` |
| 3.5 | `runtime_char.py`: sustained decode with GPU sampling | `results/runtime_experiments/<slug>_runtime_characterization_<date>.json` |
| 4 | `phase4.sh`: bench-pipeline (whole), bench-code (first 50 HumanEval), bench-reasoning limit 10 with raw samples | the records ledger; suite logs `/mnt/shared/logs/benchmarks/phase4_<run>_*.log` |
| 4 (end) | `suggest_p45.py`: what Phase 4 showed and what might fix it; then the lane pauses: the model stays loaded and the lane ends | lane log (`PAUSED` line names the profile) |
| 4.5 (only with `LANE_START_AT=4.5`) | the thinking on vs off A/B when the template has a thinking control | lane log; runs `<slug>_w_p45_off` / `_w_p45_think` in the ledger |

Watch it: `rigctl runs`, the lane log (`/mnt/shared/logs/benchmarks/worker_lanes_<time>/lane_gpu<cards>.log`, cards joined with `-`),
the dashboard. The lane pauses after Phase 4 with the model still loaded; unload it (`rigctl unload <profile>`)
or go on to Phase 4.5 as a separate step.

Debug-only, by hand (a first look at a model that misbehaves): `rigctl load-model <id> --gpus <cards>`, then
`python3 scripts/integration/litmus.py <port>` on the rig, then `rigctl unload <profile>`. Never start a
runtime with `run_runtime.sh` or `docker run` directly: the manager would not know the cards are busy.

### Phase 2 gate
The model serves and every layer is on the GPUs (the rig refuses anything else). A load that fails says
why in the lane log (won't fit, out of memory, unknown architecture): see the decision trees.

### Phase 3 gate
All 3 checks pass, or each failure is understood and documented in the registry notes (a fenced JSON
answer fails the raw-JSON check but is read fine by the suites).

### Phase 4: reading the smoke
Every suite must produce a score. Then read the results, not just the numbers:

- The reasoning rows that count are the lenient ones (`bbh_flexible`, `gsm8k_flexible`, `drop_flexible`,
  `mmlu_pro_flexible`, and `ifeval` strict). Each flexible row records how many answers could not be read
  at all (`extractor_failure_count`, notes `rescued N; unreadable M`): a high unreadable count is a format
  problem, not a capability one.
- The lane's suggestions (`SUGGEST ...` lines, or `NOTHING TO FIX`) name the problem and the options.
- Read 2-3 raw answers of any task that looks wrong (`/mnt/shared/logs/benchmarks/bench-reasoning/history/`).

**Gate**: every suite scores, raw answers have been read, and format problems are noted for Phase 4.5.

## Phase 4.5: Settings Experiments

Phase 4 proves the model works. Phase 4.5 looks for the model's best settings before hours of full runs.
Every model behaves differently; do not inherit a family default because it passed Phase 4.

Phase 4.5 is a menu, not a checklist (operator, 2026-10-22), and never automatic: the lane stops after
the Phase 4 smoke, and the operator reads the results and decides whether 4.5 runs and with which
experiments (operator, 2026-10-23). It is optional: a model whose Phase 4 results
show nothing to fix can go straight to Phase 5, and a model only tries the options that bear on what Phase 4
showed. Pick experiments from the symptoms:

| Phase 4 symptom | Options to try |
|---|---|
| A task's answers unreadable or cut off (`unreadable` count in the flexible rows, empty or one-line samples) | system prompt; output budget; thinking off |
| Answers wrapped in JSON or markdown the task did not ask for | system prompt (one that does not talk about formats) |
| Thinking model: empty answers, or very slow | thinking on vs off; reasoning budget |
| Scores fine, but slow for its intended use | thinking off; context and batch size (speed only: they do not move benchmark scores) |
| Template quirks in litmus (think tags, missing generation prompt) | template switches |

Example: phi-4:14b (2026-10-22) answered every DROP question as multi-line JSON, so DROP's newline stop cut
all 50 answers to `{` or a fenced `json` line, while its other tasks scored normally. Its system prompt is
mostly JSON formatting rules; the experiment is a system prompt without them, A/B on the smoke set.

The lane runs the thinking A/B when started for it: `rigctl run-start --run lanes-<slug>-p45 --env
LANE_START_AT=4.5 -- /bin/bash .../run_worker_lanes.sh <group> <short-id>`. For the others, change the registry profile (a new named
profile, or the `default` once it wins) and re-run the smoke with a suffix:
`rigctl run-start --run lanes-<slug>-r2 --env LANE_RUN_SUFFIX=_r2 -- /bin/bash
.../run_worker_lanes.sh <group> <short-id>`. A one-off system prompt: bench-reasoning `--system-prompt-override`.
Then compare the two runs (`python3 scripts/integration/suggest_p45.py <id> <run>` on each).
(`p45.sh` and `smoke_reasoning.sh` predate the manager and start runtimes themselves: do not use them while
anything else runs on the rig.)

For each experiment, change one setting at a time against the Phase 4 configuration, at smoke size, on the
suites that setting can move:

| Setting | How to vary it | Measure on |
|---|---|---|
| Thinking / reasoning mode | `extra_args` (`--reasoning on/off`, `--reasoning-budget N`, template kwargs such as `reasoning_effort`); thinking runs need `--gen-kwargs "max_gen_toks=4096,until=</s>"` (the lane passes this): task stop sequences fire inside thinking text and return empty answers | bbh, gsm8k, drop, ifeval |
| System prompt | registry `system_prompt`, or `--system-prompt-override` for a one-off | pipeline, bbh, drop, ifeval |
| Output budget | registry `inference.max_tokens` | pipeline and custom suites with long structured output (geoimport) |
| Template switches | `--chat-template-kwargs` (read the template's `add_generation_prompt` block) | litmus and the suite that exposed the issue |

Rules:
- Read raw outputs for every experiment; a score change without a visible cause is noise at limit 10.
- Change the model's registry profile for model behavior; change the harness only for defects that hit
  every model.
- Keep the speed/quality trade-off explicit: record wall time next to each A/B (thinking on can cost 5-10x
  the time for a few points).

**Gate**: every setting changed from the Phase 4 configuration has an A/B result behind it, and each Phase 4
problem was either fixed or recorded as a known limit. A model with no Phase 4 problems passes with no
experiments.

## Phase 5: Full Run

Reasoning at limit 50 (gsm8k, bbh, drop, ifeval), MMLU-Pro at limit 20, the full code suite (HumanEval +
MBPP, 542 problems), geoimport, pipeline and runtime, with the Phase 4.5 settings. Run it as a campaign:
one manifest, any number of models, started as a run so a reboot is recoverable.

```bash
# Manifest: one block per suite per model (see campaigns/overnight_phase5_20261022.json for the shape;
# no placement: the rig manager picks the cards; gpus: [..] pins them; ctx from the registry profile)
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaigns/<name>.json --dry-run      # on the rig
rigctl run-start --run <name> \
  --resume "python3 /mnt/shared/scripts/benchmarks/run_campaign.py /mnt/shared/plans/shoulders/benchmarking/campaigns/<name>.json --run-id <name>" -- \
  python3 /mnt/shared/scripts/benchmarks/run_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/<name>.json --run-id <name> --max-active-models 3
```

Placement: omit it and the rig manager picks the cards (the fewest that hold the model at its profile's
context, across the 3090 and the 1060s alike), or pin them with `gpus: [0, 1, 2, 3]` (`brain` is GPU 0).
The campaign puts the rig in bench mode; busy cards are waited for. `--max-active-models` caps how many
models run at once. See [CAMPAIGN_RUNNER.md](docker/CAMPAIGN_RUNNER.md) and
[CAMPAIGN_RUNNER_REFACTOR.md](docker/CAMPAIGN_RUNNER_REFACTOR.md).

Time to expect (2026-10-22, at the standing power caps): mixture-of-experts models on the 3090 about 1-1.5 h;
dense 24-31B on the 3090 2.5-4.5 h; 12-14B models on a 1060 pair 5.5 h (MoE) to 17 h (dense).

**Gate**: all blocks complete (`rigctl runs`, the campaign status), scores recorded.

## Capacity run

Bench mode loads the bare minimum (the fewest cards at the profile's context). The capacity run answers the
other question: the most the model can do on a given set of cards, for chat and harness settings.

```bash
rigctl run-start --run capacity-<slug> -- python3 \
  /mnt/shared/plans/shoulders/benchmarking/scripts/integration/capacity_run.py <short-id> [--gpus 0,1,2,3,4,5 | --cards N]
```

`--gpus` pins the cards, `--cards N` lets the manager pick N, neither uses every card. The manager plans the
largest context that fits on them (its largest-that-fits rule, the default profile's batch and args); the
model is loaded at exactly that context; a short probe measures decode speed and power, and depth probes
fill 10, 25, 50, 75 and 90% of the context (`--fractions`) with a code planted at the start and ask for it
back: at each depth, prefill speed, time to first token, decode speed (160 generated tokens by default) and
whether recall still works. `--decode-tokens N` raises the generated-token cap for models that spend the
default budget thinking before answering; keep the depth and cap in the receipt when comparing results.
`--allow-eos` lets a depth probe stop naturally, for a realistic answer check; the default forces the full
decode budget for comparable speed measurements.
`--concise-instruction` adds a system instruction requesting only the code and no visible reasoning; it
changes the prompt, so compare it only with runs using the same instruction.
Prompt caching is off, so prefill is measured over the whole prompt. The record is
`results/runtime_experiments/<slug>_capacity_g<cards>_ctx<context>_<date>.json`; the model is unloaded at the end.
The run rebuilds [results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md); what the numbers mean, and the
other speed and PCIe tools, are in [RIG_PERFORMANCE.md](RIG_PERFORMANCE.md).

## Phase 6: Finalize

| What | Where |
|---|---|
| Status `candidate` -> `active` once it completed the gates (roles may only point at active models); `tuning.status` and `last_tuned_at` | `model_registry.json`, then `model_library.py export` |
| What was learned: chosen settings and why, known limits, speed | the profile `notes` in the registry |
| An integration entry: phases, settings, known limits, run names | Part 2 of this file (template below) |
| A role, if it is the best at a job | `model_roles.json`, and `MODEL_BEST_OF.md` |
| Runtime notes worth keeping | `MODEL_RUNTIME_GUIDE.md` |
| A debugging story worth keeping | `BENCHMARK_LESSONS_LEARNED.md` |

Score tables are generated (`results/MODEL_BENCHMARK_REFERENCE.md`, the scoreboard, the dashboard); there
is nothing to copy by hand. `BENCHMARK_SCORES.md` is retired (last updated 2026-06-13).

**Gate**: the registry has the chosen settings and status, and the integration entry exists.

## Runtime retention

The lane loads its model and pauses after Phase 4 with it still loaded; the campaign loads and unloads its own. A model loaded by hand (debugging, chat) stays
loaded until it is unloaded (`rigctl unload <profile>`) or its owner is cancelled (`rigctl cancel-owner`):
nothing unloads it at the end of a test on its own. Record what you left loaded.

---

## Decision Trees

### Litmus Fails: Think Tags in Output

```
Litmus shows <think> tags or empty content
+-- Check model family
|
+-- OpenAI gpt-oss (channel-based thinking)
|   -> thinking=1 but content field is CLEAN
|   -> Reasoning goes to reasoning_content field via channel system
|   -> No --reasoning-budget 0 needed, no --patch-think-tag-strip needed
|   -> This is the ideal behavior - litmus should pass all 3 checks
|   -> If litmus passes: proceed normally, no special bench flags
|
+-- Qwen 3.x / 3.5 / 3.6
|   -> Set registry extra_args `--reasoning off` (older runtimes: `--reasoning-budget 0`)
|   -> Re-run the lane with a suffix (LANE_RUN_SUFFIX=_r2)
|   -> If still shows empty <think></think> wrappers:
|     add --patch-think-tag-strip at bench time
|
+-- Gemma 4 (any size)
|   -> Expected: model uses <|channel>thought prefix
|   -> Content field should still have the answer
|   -> If content empty: reasoning consumed max_gen_toks
|   -> Fix: registry extra_args `--reasoning off` (REQUIRED for ALL sizes; earlier `--reasoning-budget 0`)
|   -> A/B tested on 12B: budget=0 scored BBH 0.82, budget=1024 scored 0.24
|   -> Confirmed on 26B-A4B: budget=0 scored BBH 0.87, previous thinking-on was 0.27
|   -> Thinking tokens consume generation budget -> answer truncated
|   -> Also apply --patch-think-tag-strip at bench time (BBH + DROP)
|   -> Mark litmus PASS with note
|
+-- DeepSeek-R1 (any size)
|   -> Structural: <think> tokens baked into vocabulary
|   -> --reasoning-budget 0 does NOT help
|   -> --patch-think-tag-strip partially helps (BBH yes, DROP no, code no)
|   -> Record limitation, proceed with known constraints
|
+-- Phi-4-mini-reasoning (and similar reasoning-finetuned models)
    -> Structural: <think> tokens from reasoning finetune
    -> --reasoning-budget 0 does NOT help (runtime shows thinking=0 anyway)
    -> --patch-think-tag-strip needed for BBH/DROP
    -> Code suite will have degraded results (think tokens stripped with code)
    -> Same behavior pattern as DeepSeek-R1
```

### Smoke Suite Scores All Zero

```
All scores 0 in a suite
+-- Check container logs for "Use model prompts: 1"
|   +-- Shows 0 -> Stale Docker image
|       -> Rebuild: docker build -t bench-<suite> bench-<suite>
|
+-- Check container logs for "thinking = 1"
|   +-- Shows 1 -> Thinking mode active
|       -> Set `--reasoning off` in the registry profile, re-run the lane with a suffix
|       -> Verify: docker logs <ctr> 2>&1 | grep "thinking ="
|
+-- Check if model ID fuzzy-matches tuning profiles
|   +-- No match -> Model prompts not resolving
|       -> Add an alias in the registry entry (`aliases`), then `model_library.py export`
|       -> Or run with --allow-generic-prompt-fallback
|
+-- Check for stop sequence truncation
    +-- BBH: \n\n stop truncates after think tags
    |   -> Apply --patch-think-tag-strip
    +-- DROP: . stop truncates inside think chains
        -> Apply --patch-think-tag-strip + max_gen_toks 512
```

### Runtime Won't Load (OOM / Timeout)

```
Runtime fails to start or gets OOM-killed
+-- Exit code 137 (Docker OOM)
|   -> Container hit its memory limit (loads through the manager: the rig's limit, rig.py REMOTE_MEMORY_LIMIT)
|   -> Lower the context, or check host RAM (the rig guard frees RAM at critical)
|
+-- "won't fit" from the manager, or a load refused as not fully on the GPUs
|   -> `rigctl fit <id> --gpus <cards>` shows MiB per card
|   -> More cards, a smaller context (`--ctx`), or a smaller quant (layers are never left to the CPU)
|
+-- Timeout (the load never serves)
|   -> The lane log shows the rig's reason; a cold first load from the shared drive is slow
|   -> Check the cards are free (`rigctl status`)
|
+-- "unknown model architecture" error
|   -> Runtime image too old for this model family
|   -> Check required image tag in MODEL_RUNTIME_GUIDE.md
|   -> Rebuild/pull updated runtime image
|
+-- System RAM pressure
    -> Check: free -h; docker stats --no-stream
    -> See docker/README.md "Memory Protection" section
    -> Reduce number of concurrent models
```

### Code Suite All-Zero but Pipeline/Reasoning Work

```
bench-code produces 0% but other suites score
+-- Think tags consumed code output
|   -> evalplus sanitizer strips <think> + code together
|   -> No clean fix for thinking models
|   -> Record as known limitation
|
+-- Model emits markdown fences around code
    -> evalplus expects raw code
    -> Check if code output starts with ```python
    -> May need prompt tuning to suppress fences
```

### Special Model Types

**MoE (Mixture of Experts)** - e.g., Gemma 4 26B-A4B, Qwen3.5 35B-A3B, gpt-oss 20B:
- GGUF file size reflects total params but active params per-token are much smaller
- Inference speed closer to the active param count (3-4B active runs like a 3-4B dense model)
- VRAM usage depends on total params (all experts must be loaded), not active params
- Brain tier for models >12GB GGUF, single tier if GGUF fits in 6GB

**MXFP4/Native Quantization** - e.g., gpt-oss 20B:
- Some models ship as MXFP4 (Microscaling FP4) GGUFs instead of post-training quantized Q4/Q8
- llama.cpp handles MXFP4 natively (supported since ~b6962, our runtime is b8884+)
- No special flags needed - treat like any other GGUF
- File size may differ from Q4_K_M expectations for same param count

**OpenAI-family models** - e.g., gpt-oss:
- Require `--jinja` flag for chat template processing
- Add `--extra-arg "--jinja"` to run_runtime.sh invocation
- Add `"--jinja"` to `extra_args` in tuning profiles

---

## Integration entry template

Add one per model to Part 2 (newest first), short:

```markdown
## Integration: <model> (<date>)

Cards: <group> | GGUF: <file> (<size>, SHA-256 checked) | Source: <url>

- Phase 0-1: hotset + library; registry `<short-id>` (<prompt family>, extra args); fit: ctx <N>, split <..>
- Lane: run `<run id>`, log `<path>`
- Phase 2: loaded in <s>; VRAM <per card>
- Phase 3: litmus <pass, or what failed and why>
- Phase 3.5: decode <tok/s>, power <W>
- Phase 4 smoke: <key scores>; suggestions: <SUGGEST lines or NOTHING TO FIX>
- Phase 4.5: <experiments and results, or none>; chosen: <settings>
- Phase 5: campaign `<name>`: <key scores>, <time>
- Known limits: <...>
```

---

# Part 2: Integration Log

## Integration: nemotron-3.5-bolt:74b-a9b (2026-10-23)

Cards: manager-placed, GPUs 0-3 | GGUF: NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL.gguf (39.0 GB, SHA-256 checked) | Source: unsloth/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-GGUF

- Phase 0-1: hotset + library; registry `nemotron-3.5-bolt:74b-a9b` (worker strict, `--reasoning off`); fit: ctx 16384 on GPUs 0-3, split 57,16,10,6
- Lane: run `lanes-nemotron-bolt`, log `/mnt/shared/logs/benchmarks/worker_lanes_20261023_133057/`
- Phase 2: loaded in 215 s; VRAM 23555 / 5134 / 5126 / 4116 MiB
- Phase 3: litmus 3/3, no think tags, no fences
- Phase 3.5: decode 24.1 tok/s; 3090 142 W, 1060s about 42 W
- Phase 4 smoke: run `nemotron-3_5-bolt_74b-a9b_w_smoke_v1`; suggestions: NOTHING TO FIX
- Phase 4.5: none; chosen: registry default (thinking off)
- Phase 5: campaign `nemotron_bolt_phase5_20261023`, run `nemotron-bolt-phase5`, 6 h
- Known limits: asks for clarification less than peers (pipeline ambiguity, command safety)

## Re-integration: qwen3.6:35b-a3b (2026-10-17)

Tier: brain (3090 Ti 24GB) | GGUF: `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (20.6 GB) | active model, last scored
2026-04-25 on an older runtime and scoring. Rerun through Phases 2-5 on b11669 and extract v4 so it compares
directly with the October brain candidates.

### Phase 2: First Load
- [x] From the NVMe hot-set (`sync-gguf --model qwen3.6:35b-a3b`), `--reasoning off`: 165 s, 21201 MiB,
  41/41 layers, `thinking = 0`; warnings: reasoning-preserve default, "no API key, CORS open" (127.0.0.1 only)
- Registry gap found: the profile had no reasoning flag, so on b11669 thinking was on by default.

### Phase 3: Litmus Test
- [x] 3/3 clean (555, valid JSON, bare function)

### Phase 3.5: Runtime Characterization
- [x] `results/runtime_experiments/qwen36_35b_a3b_runtime_characterization_20261017.json`: decode 137.6 tok/s,
  avg 270.5 W, peak 314.7 W, peak 60 C, 0.435 Wh

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline: json_schema 0.231, cmd_safety 1.0, ambiguity 0.538, tool_plan 0.933, orch 0.75, long_context 1.0
- [x] bench-code (full 542): HumanEval 0.927 / 0.896, MBPP 0.907 / 0.767
- [x] bench-reasoning: GSM8K 1.00 / 1.00, BBH 0.907 / 0.911 flexible, DROP EM 0.80 / F1 0.80 / flexible 0.80,
  MMLU-Pro 0.821, IFEval prompt strict 0.80 / inst strict 0.889
- Run name `qwen36_35b_a3b_smoke_v1`. Pipeline and code ran while a Nex split load ran on the 1060s; the rig
  stayed up.

### Phase 4.5: Settings Experiments
- [x] Thinking A/B (`--reasoning on`, end-of-text stops), limit 10:

  | | Off | On, 4096 budget | On, 8192 budget |
  |---|---|---|---|
  | GSM8K flexible | 1.00 | 0.90 | 0.90 |
  | BBH flexible | 0.911 (7:53) | 0.800, 47/270 empty (49:43) | 0.852, 29 empty (65:30) |
  | DROP flexible | 0.80 | 0.80 | 0.80 |
  | IFEval prompt / inst | 0.80 / 0.889 | 0.70 / 0.611 | 0.80 / 0.778 |

  It thinks past both budgets (empty answers), and when it finishes it is very accurate (216 of 223 completed
  BBH answers right at 4096), but thinking off scores higher overall at 1/8 of the time. Thinking off.
  Runs: `qwen36_35b_a3b_p45_off`, `_p45_think`, `_p45_think8k`.
- [x] Thinking-on pipeline / geoimport (4096): ambiguity 0.538 -> 0.462, orchestration 0.75 -> 0.833, rest equal
- [x] Output budget A/B (geoimport): 512 and 1024 identical (prep plan 0.879); 512 kept
- [x] Chosen settings written to the registry: `--reasoning off`, family prompt, max_tokens 512

### Phase 5: Full Run (limit 50/100)
- Campaign `qwen36_35b_a3b_phase5_202610` (2026-10-17, run 20261017_164139), thinking off, extract v4,
  same blocks as `october_brain_phase5_202610`; 16:41-17:48 (reasoning block 46 min).
- [x] bench-reasoning limit 50: GSM8K 0.94 / 0.94, BBH 0.910 / 0.913 flexible, DROP EM 0.82 / F1 0.86 /
  flexible 0.88, IFEval prompt strict 0.86 / inst strict 0.908
- [x] MMLU-Pro limit 20 (280): 0.782
- [x] bench-geoimport: classify 1.0 / 1.0, prep plan 0.879, handoff 1.0 / 0.905
- [x] bench-pipeline: json_schema 0.231, cmd_safety 1.0, ambiguity 0.538, tool_plan 0.933, orch 0.75, long_context 1.0
- [x] bench-runtime: 4/4
- [x] bench-code: Phase 4 full run stands (HumanEval 0.927 / 0.896, MBPP 0.907 / 0.767)

## Integration: Nex-N2.5 mini 35B-A3B (2026-10-16)

Tier: brain (3090 Ti 24GB) | GPU target: GPU 0 | Port: 11434
GGUF: `nex-agi_Nex-N2.5-mini-Q4_K_M.gguf` | Size: 22.32 GB | Source: bartowski/nex-agi_Nex-N2.5-mini-GGUF

The `october_brain_202610` limit-50 run used `--reasoning off` and is invalid for reasoning: DROP 0.0 and
BBH 0.454 came from the thinking-control problem below, not the model.

### Phase 0: Download
- [x] GGUF in `/mnt/shared/models/nex-n2.5-mini/`
- [x] SHA-256 matched the Hugging Face LFS oid (desktop download); archive copy size 22318512256 bytes

### Phase 1: Register
- [x] `model_registry.json` entry `nex-n2.5:mini` (status candidate), `export` + `check` ok
- [x] System prompt: thinking-suppression family (kept)
- [x] Runtime config: ctx_size=8192, batch_size=128, n_gpu_layers=999
- [x] Extra args: `--chat-template-kwargs {"reasoning_effort":"none"}` (registry commit 79a406c), replacing `--reasoning off`

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh` (container `llama-nex-test`, port 11434, 10g/12g)
- [x] `/v1/models` responds with the GGUF path as model id
- [x] Docker logs: 41/41 layers offloaded; MoE 256 experts, 8 used; n_ctx_train 262144; `thinking = 1` is
  reported, but the rendered prompt ends `<think>\n\n</think>\n\n` (closed, empty) with the template switch
- [x] Warnings: reasoning-preserve default (multi-turn only); "no API key, CORS open" (server binds 127.0.0.1)
- [x] VRAM usage: 21275 MiB of 24564 MiB (tightest of the three brain candidates)
- [x] Load time: 253.3 s cold from the shared archive (NFS)
- [x] Runtime image: `llama-runtime:b11669`
- Thinking control: the template always ends the prompt with an open `<think>` and ignores `--reasoning off`,
  `--reasoning-budget 0` and `enable_thinking=false`. The model's first token is the newline after
  `<think>`, so any newline stop (DROP) returns an empty answer. The template's own
  `reasoning_effort == 'none'` branch emits an empty closed think block; set with `--chat-template-kwargs`.
  Diagnosed by replaying a DROP prompt through `/apply-template` and `/completion`.

### Phase 3: Litmus Test
- [x] Reasoning check (555): PASS
- [x] JSON check: PASS, `{"name":"Alice","age":30}`
- [x] Code generation check: PASS, bare function
- Note: litmus would also pass with `--reasoning off` (no stop sequences, thinking lands in
  reasoning_content); only the DROP stop exposed the problem.

### Phase 3.5: Runtime Characterization
- [x] Record: `results/runtime_experiments/nex_n25_mini_runtime_characterization_20261016.json`
- Decode 142.22 tok/s (768 tokens, 5.6 s wall), prompt 508 tok/s
- GPU 0: avg 294.8 W, peak 320.1 W, peak 60 C, 88% utilization; decode energy 0.46 Wh (6 samples)

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline: json_schema 0.231, cmd_safety 0.833, ambiguity 0.923, tool_plan 1.0, orch_tradeoff 0.667, long_context 1.0
- [x] bench-code (full 542): HumanEval base 0.878 / plus 0.823, MBPP base 0.794 / plus 0.648
- [x] bench-reasoning --limit 10: GSM8K 0.90 / 0.90, BBH 0.719 (flexible 0.763), DROP EM 0.60 / F1 0.725
  (flexible 0.90), MMLU-Pro 0.686, IFEval prompt strict 0.90 / inst strict 0.944
- [x] BBH rerun on extract v3 (`\nQ:` stop): strict 0.752, flexible 0.807 (`nex_n25_mini_smoke_v1_x3`)
- [x] Raw outputs inspected
- [x] All suites produce non-zero scores
- Flags needed: none
- Findings:
  - BBH has the most plain wrong answers of the three (54 of 270 at extract v2); a real weakness, not format.
  - Before extract v3, `(Q)` answers were cut by the bare `Q` stop ("Answer: ("); fixed in the harness.
  - json_schema_strict: all 10 failures are the undefined "priority" convention (suite limitation).
  - ambiguity_handling 0.923: asks or confirms with the expected wording (Ornith-35B: 0.538).
- Run names: `smoke_nex_reasoning_off_v1` (diagnosis), `smoke_nex_effort_none_v1`,
  `smoke_nex_effort_none_bench_prompt_v1` (prompt A/B: DROP 0.60 -> 0.40, family prompt kept),
  `nex_n25_mini_smoke_v1`, `nex_n25_mini_smoke_v1_x3`

### Phase 4.5: Settings Experiments
- [x] Thinking mode A/B (template default, open think block vs `reasoning_effort` none), limit 10:
  - GSM8K: off 0.90 / 0.90, on 0.70 strict / 0.90 flexible (thinking drops the `#### N` format)
  - BBH (1024 budget, thinking run 4096): off 0.763 strict / 0.837 flexible in 8:33;
    on 0.519 strict / 0.833 flexible (85 rescued: it answers a bare option after thinking) in 10:30
  - Verdict: no accuracy gain, 23% slower on BBH. Thinking stays off.
  - Runs: `nex_n25_mini_p45_think` (GSM8K), `nex_n25_mini_p45_think_bbh2` (BBH; first attempt failed on a
    network outage while downloading the dataset)
- [x] System prompt A/B: done in Phase 4 (benchmark prompt DROP 0.40 vs family 0.60); family kept
- [x] Output budget A/B (bench-geoimport, `--inference-config-json`): max_tokens 512 average 0.845
  (prep plan cut mid-JSON at 2169 chars, 0.333) vs 1024 average 0.967 (complete plan 2523 chars, 0.939)
  (`nex_n25_mini_p45_geo_mt512`, `_mt1024`)
- [x] BBH output budget (harness, all models): 512 vs 1024 on this model drove the extract-v4 change
- [x] Chosen settings written to the registry: `reasoning_effort` none, family prompt, max_tokens 1024
- Load note: from the NVMe hot-set (Gen1 x1) with a cold page cache the load took 214 s vs 253 s over
  NFS; about 200 s of it is reading the 20.7 GB file through mmap (~100 MB/s).
- Split placement on the GTX 1060s (2026-10-17, 3090 busy with another model): fits on 4 cards with
  `--tensor-split 0.75,1,1,1` or 5 cards with `1,1,1,1,1`; decodes 22.0 / 21.7 tok/s vs 142.2 on the 3090
  (about 6.5x); litmus 3/3; `--split-mode row` unsupported. Details and command in
  BENCHMARK_LESSONS_LEARNED.md, "Brain MoE across the 1060 farm".

### Phase 5: Full Run (limit 50/100)
- Campaign `october_brain_phase5_202610` (2026-10-17, run 20261017_011528), thinking off, extract v4,
  hot-set load 175 s. Nex blocks 01:15-02:12.
- [x] bench-reasoning limit 50: GSM8K 0.78 strict / 0.82 flexible, BBH 0.738 / 0.821 flexible,
  DROP EM 0.58 / F1 0.723 / flexible 0.88, IFEval prompt strict 0.82 / inst strict 0.842 (49 min)
- [x] MMLU-Pro limit 20 (280): 0.693
- [x] bench-geoimport: classify 1.0 / 0.941, prep plan 0.939, handoff 1.0 / 0.952
- [x] bench-pipeline: json_schema 0.231, cmd_safety 0.833, ambiguity 0.923, tool_plan 1.0, orch 0.667, long_context 1.0
- [x] bench-runtime: 4/4
- [x] bench-code: Phase 4 full run stands (HumanEval 0.878 / 0.823, MBPP 0.794 / 0.648)

### Phase 6: Finalize
- [ ] pending

## Integration: Ornith-1.5 35B-A3B (2026-10-16)

Tier: brain (3090 Ti 24GB) | GPU target: GPU 0 | Port: 11434
GGUF: `Ornith-1.5-35B-Q4_K_M.gguf` | Size: 21.71 GB | Source: ornith-ai/Ornith-1.5-35B-A3B-GGUF

Same process note as Qwen3.8: the `october_brain_202610` limit-50 run came before Phases 3.5 and 4.

### Phase 0: Download
- [x] GGUF in `/mnt/shared/models/ornith-1.5-35b-a3b/`
- [x] SHA-256 matched the Hugging Face LFS oid (desktop download); archive copy size 21713463040 bytes

### Phase 1: Register
- [x] `model_registry.json` entry `ornith-1.5:35b-a3b` (status candidate), `export` + `check` ok
- [x] System prompt: thinking-suppression family (kept; see Phase 4)
- [x] Runtime config: ctx_size=8192, batch_size=128, n_gpu_layers=999, extra args `--reasoning off`

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh` (container `llama-ornith35-test`, port 11434, 10g/12g)
- [x] `/v1/models` responds with the GGUF path as model id
- [x] Docker logs: `thinking = 0`; 42/42 layers offloaded; MoE 256 experts, 8 used; n_ctx_train 262144
- [x] Warnings: 20 "unused tensor" lines, all `blk.40.*`, the next-token-prediction (MTP) layer
  (`nextn_predict_layers = 1`), skipped unless speculative decoding is enabled; benign. Also the llama.cpp
  "no API key, CORS open" notice (server binds 127.0.0.1).
- [x] VRAM usage: 20417 MiB of 24564 MiB
- [x] Load time: 362.0 s cold from the shared archive (NFS)
- [x] Runtime image: `llama-runtime:b11669`

### Phase 3: Litmus Test
- [x] Reasoning check (555): PASS
- [x] JSON check: PASS, `{"name": "Alice", "age": 30}`
- [x] Code generation check: PASS, function wrapped in a ```python fence (EvalPlus sanitizes it; code scores below)

### Phase 3.5: Runtime Characterization
- [x] Record: `results/runtime_experiments/ornith15_35b_runtime_characterization_20261016.json`
- Decode 164.86 tok/s (768 tokens, 4.9 s wall), prompt 346 tok/s; about 3.8x Qwen3.8 27B dense
- GPU 0: avg 298.0 W, peak 329.5 W, peak 62 C, 89.8% utilization; decode energy 0.41 Wh
  (only 5 one-second samples because the decode is short)

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline: json_schema 0.154, cmd_safety 1.0, ambiguity 0.538, tool_plan 0.933, orch_tradeoff 0.75, long_context 1.0
- [x] bench-code (full 542): HumanEval base 0.902 / plus 0.854, MBPP base 0.886 / plus 0.754
- [x] bench-reasoning --limit 10: GSM8K 0.80 / 0.80, BBH 0.830 (flexible 0.830), DROP EM 0.40 / F1 0.47
  (flexible 0.60), MMLU-Pro 0.757, IFEval prompt strict 0.90 / inst strict 0.944
- [x] Raw outputs inspected
- [x] All suites produce non-zero scores
- Flags needed: none
- Settings: no changes. `--reasoning off` gives a clean empty think block; the family prompt beat the
  benchmark-assistant prompt in an A/B smoke (`smoke_ornith35_bench_prompt_v1`: DROP EM 0.40 -> 0.10,
  the "think silently" wording made it reason in the visible first line).
- Findings:
  - json_schema_strict: 9 of 11 failures are the undefined "priority" convention (suite limitation, see Qwen3.8).
  - ambiguity_handling: some failures are correct answers in other words ("prompt the user to provide",
    "verify with the user") that miss the confirm/clarify/ask keyword groups; others act without asking.
    Candidate for a versioned keyword update, not a model setting.
  - DROP misses that flexible scoring keeps failing are wrong answers (counting errors, wrong field goal).
  - BBH misses without the answer phrase are all cut at the 512-token BBH cap on long tasks
    (dyck, geometric shapes, logical deduction); same pattern as Qwen3.8.
- Run names: `ornith15_35b_smoke_v1`

### Phase 4.5: Settings Experiments
- Loads from the NVMe hot-set: 205 s (thinking off) and 182 s (thinking on), vs 362 s over NFS.
- [x] Thinking mode A/B (`--reasoning off` vs `--reasoning on`, thinking runs `max_gen_toks=4096`), limit 10,
  extract v4:
  - GSM8K: off 0.80 / 0.80 (Phase 4), on 1.00 / 1.00
  - BBH: off 0.844 strict / 0.844 flexible in 6:48; on 0.922 / 0.930 in 13:15 (about 2x the time)
  - Verdict: thinking is a real gain for this model (unlike Nex). DROP cannot be scored with thinking on
    (its newline stop cuts the thinking); IFEval with thinking not yet measured.
  - Runs: `ornith15_35b_p45_off` (BBH), `ornith15_35b_p45_think`
  - Invalid attempt, removed: a first `ornith15_35b_p45_off` run was answered by a leftover Nex runtime on
    the same port (the new container failed to bind and the readiness probe hit Nex). Two GSM8K rows were
    deleted from the ledger (backup `logs/model_benchmark_records.jsonl.bak-20261017-misattributed`) and the
    output moved to `gsm8k.nex-served-invalid-20261017`. `run_runtime.sh` now refuses an occupied port and
    verifies the served GGUF (llm_orchestration 8de590c).
- [x] System prompt A/B: done in Phase 4 (benchmark prompt DROP 0.40 -> 0.10); family kept
- [x] Output budget A/B (geoimport): max_tokens 512 and 1024 identical (complete 2147-char plan, all cases
  1.0 except prep_plan 0.939); Ornith writes concise plans, 512 kept
  (`ornith15_35b_p45_geo_mt512`, `_mt1024`)
- [x] Thinking on, DROP and IFEval with end-of-text stops (`ornith15_35b_p45_think_eosonly`): DROP EM 0.10 /
  flexible 0.90 (off 0.40 / 0.60; it answers in full sentences after thinking), IFEval 0.90 / 0.944 (unchanged)
- [x] Thinking-on pipeline / geoimport at max_tokens 4096 (`ornith15_35b_p45_think_pipeline`, `_think_geo`):
  json_schema 0.154 -> 0.385, ambiguity 0.538 -> 0.769, cmd_safety 1.0 -> 0.833, tool_plan 0.933 -> 0.867,
  orchestration and long_context unchanged; geoimport unchanged
- [x] Chosen settings written to the registry: `--reasoning on` (max scores, about 2x time), family prompt,
  max_tokens 4096 (covers the thinking); reasoning runs use `--gen-kwargs "max_gen_toks=4096,until=</s>"`

### Phase 5: Full Run (limit 50/100)
- Campaign `october_brain_phase5_202610` (2026-10-17, run 20261017_011528), thinking on, extract v4,
  hot-set load 160 s. Ornith blocks 02:12-03:55.
- [x] bench-reasoning limit 50: GSM8K 0.94 / 0.94, BBH 0.924 / 0.926 flexible (13 of 1350 answers empty:
  thinking past the 4096 budget), DROP EM 0.34 / F1 0.628 / flexible 0.98 (answers in full sentences after
  thinking), IFEval prompt strict 0.82 / inst strict 0.882 (75 min)
- [x] MMLU-Pro limit 20 (280): 0.771 (23 min)
- [x] bench-geoimport: classify 1.0 / 1.0, prep plan 0.939, handoff 1.0 / 1.0
- [x] bench-pipeline: json_schema 0.385, cmd_safety 0.833, ambiguity 0.769, tool_plan 0.867, orch 0.75, long_context 1.0
- [x] bench-runtime: 4/4
- [x] bench-code: Phase 4 full run stands, thinking off (HumanEval 0.902 / 0.854, MBPP 0.886 / 0.754);
  code with thinking on not measured

### Phase 6: Finalize
- [ ] pending

## Integration: Qwen3.8 27B (2026-10-16)

Tier: brain (3090 Ti 24GB) | GPU target: GPU 0 | Port: 11434
GGUF: `Qwen3.8-27B-UD-Q4_K_M.gguf` | Size: 16.46 GB | Source: unsloth/Qwen3.8-27B-GGUF

Process note: a limit-50 brain campaign (`october_brain_202610`) ran on 2026-10-16 before
Phases 3.5 and 4 were done. Its scores are real but were taken with untuned settings; this entry
is the integration proper.

### Phase 0: Download
- [x] GGUF in `/mnt/shared/models/qwen3.8-27b/`
- [x] SHA-256 matched the Hugging Face LFS oid (desktop download); archive copy size 16464440224 bytes
- Notes: downloaded on the desktop over Wi-Fi in 49.1 min, pushed to the Pi archive.

### Phase 1: Register
- [x] `model_registry.json` entry `qwen3.8:27b` (status candidate), `export` + `check` ok
- [x] System prompt: started on the thinking-suppression family; replaced by a model-specific prompt in Phase 4
- [x] Runtime config: ctx_size=16384, batch_size=128, n_gpu_layers=999, extra args `--reasoning off`

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh` (container `llama-qwen38-test`, port 11434, 10g/12g memory limits)
- [x] `/v1/models` responds with the GGUF path as model id
- [x] Docker logs: `thinking = 0`; 66/66 layers offloaded; one warning, reasoning preservation on by default (multi-turn only)
- [x] VRAM usage: 15797 MiB of 24564 MiB
- [x] Load time: 275.9 s cold from the shared archive (NFS); tensors done at 168 s, the rest is 16k context setup
- [x] Runtime image: `llama-runtime:b11669`
- [x] Extra args needed: `--reasoning off` (template ends the prompt with an empty closed think block)

### Phase 3: Litmus Test
- [x] Reasoning check (555): PASS, content `555`, no reasoning_content
- [x] JSON check: PASS, valid `{"name": "Alice", "age": 30}`
- [x] Code generation check: PASS, bare function, no fences
- Fixes applied: none

### Phase 3.5: Runtime Characterization
- [x] Record: `results/runtime_experiments/qwen38_27b_runtime_characterization_20261016.json`
- Decode 43.47 tok/s (768 tokens, 19.1 s wall), prompt 106 tok/s
- GPU 0: avg 411.7 W, peak 449.8 W, peak 68 C, 89% utilization, 2005 MHz; decode energy 2.18 Wh

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline (v1 prompt): json_schema 0.308, cmd_safety 0.917, ambiguity 0.923, tool_plan 0.933, orch_tradeoff 0.75, long_context 1.0
- [x] bench-code (full 542): HumanEval base 0.933 / plus 0.902, MBPP base 0.907 / plus 0.775
- [x] bench-reasoning --limit 10 (v1 prompt): GSM8K strict 0.90 / flexible 0.90, BBH 0.800, DROP EM 0.60, MMLU-Pro 0.821, IFEval prompt strict 0.80 / inst strict 0.889
- [x] Raw outputs inspected
- [x] All suites produce non-zero scores
- Flags needed: none at bench time
- Fixes applied:
  - json_schema_strict: 8 of 9 failures are "priority mismatch"; all 13 responses are valid JSON. The cases
    expect a priority the prompt never defines (for example priority 4 for "restart gpu 4"). Suite limitation,
    not a model setting.
  - BBH: 40 of 270 answers lacked the "the answer is" phrase the extractor needs (bare `(D)`, or
    `{"answer": "(C)"}`); 3 were cut by the 512-token BBH generation cap on long tasks (dyck, geometric shapes).
  - DROP: 2 of 4 misses were JSON-wrapped answers (`{"answer": "80"}`) to plain questions.
  - Prompt experiments, reverted: v2 (limit JSON to explicit requests, end with the examples' closing
    phrase) lifted strict BBH to 0.878 but strict DROP fell to 0.20 because "So the answer is 3" leaked into
    plain questions; v3 scoped that rule. Both were chasing the strict extractors, not better answers.
  - Scoring fix instead (commit 28b20fc): BBH and DROP gained flexible rows beside the strict ones
    (`bbh_flexible`: final answer without the demonstrated phrase; `drop_flexible`: response contains every
    gold span, lead-ins and fuller sentences accepted). IFEval stays strict (its prompts instruct format).
  - Re-scored limit-10 runs (strict -> flexible): family prompt BBH 0.800 -> 0.841, DROP 0.60 -> 0.90;
    v2 BBH 0.878 -> 0.878, DROP 0.20 -> 0.70. Qwen3.8 stays on the family prompt (commit 0a863f5).
  - Remaining BBH misses are real: long tasks (dyck, geometric shapes, logical deduction, word sorting)
    cut at the 512-token BBH generation cap, and wrong answers.
  - Real-use observation: on plain questions it sometimes answers in JSON (`{"answer": "80"}`).
- bench-code recording: EvalPlus results were never written to the ledger (parser looked for a `pass@1`
  key EvalPlus does not write). Fixed in `bench-code/run.sh` (commit c979698) and re-recorded from the
  existing samples.
- Run names: `qwen38_27b_smoke_v1` (family prompt), `qwen38_27b_smoke_v2` (v2 prompt, reverted),
  `qwen38_27b_smoke_v1_flex` (family prompt, BBH/DROP with flexible rows)

### Phase 4.5: Settings Experiments
- Loads from the NVMe hot-set: 142 s (thinking off), 126 s (on), vs 276 s over NFS.
- [x] Baseline on extract v4: GSM8K 0.90 / 0.90, BBH 0.830 strict / 0.878 flexible in 22:17 (`qwen38_27b_p45_off`)
- [x] Thinking mode A/B (`--reasoning on`, `max_gen_toks=4096`):
  - First attempt with task stop sequences: GSM8K 0.70, BBH 0.374 / 0.896 with empty answers. GSM8K empties
    were the "Question:" stop firing inside the thinking; with `until=</s>` GSM8K is 0.70 strict / 1.00
    flexible (`qwen38_27b_p45_think`, `qwen38_27b_p45_think_eosonly`).
  - End-of-text stops (`qwen38_27b_p45_think_eosonly_b`): DROP EM 0.70 / flexible 0.90 (off 0.60 / 0.90),
    IFEval prompt 0.90 / inst 0.833 (off 0.80 / 0.889), BBH 0.374 / 0.896 in 67:12 (off 22:17).
  - The 10 empty BBH answers are runaway thinking past 4096 tokens, not stops: one causal_judgement item
    probed with a 12k budget thought for 8402 tokens (189 s) and answered wrong.
  - Thinking-on pipeline / geoimport at max_tokens 8192 (`qwen38_27b_p45_think_pipeline`, `_think_geo`):
    equal or better everywhere (orchestration 0.75 -> 0.833, json_schema 0.308 -> 0.385, prep_plan 0.939 -> 0.970).
  - Verdict: small gains at 3x the time with multi-minute outliers. The operator's rule is max scores with
    time secondary unless about 5x the next slowest, so thinking is on.
- [x] Output budget A/B (geoimport, thinking off): 512 prep plan cut mid-JSON at 1974 chars (0.0); 1024
  complete at 2200 chars (0.939); other cases unchanged (`qwen38_27b_p45_geo_mt512`, `_mt1024`)
- [x] Chosen settings written to the registry: `--reasoning on`, family prompt, max_tokens 8192 (covers the
  thinking); reasoning runs use `--gen-kwargs "max_gen_toks=8192,until=</s>"`

### Phase 5: Full Run (limit 50/100)
- Campaign `october_brain_phase5_202610` (2026-10-17, run 20261017_011528), thinking on, extract v4,
  hot-set load 101 s. Qwen3.8 blocks 03:55-12:48.
- [x] bench-reasoning limit 50: GSM8K 0.62 strict / 0.94 flexible, BBH 0.416 / 0.910 flexible (667 answers
  given without the phrase after thinking; 26 of 1350 empty: thinking past the 8192 budget), DROP EM 0.78 /
  F1 0.866 / flexible 0.96, IFEval prompt strict 0.92 / inst strict 0.934 (6 h 40 min)
- [x] MMLU-Pro limit 20 (280): 0.811
- [x] bench-geoimport: classify 1.0 / 1.0, prep plan 0.970, handoff 1.0 / 0.952
- [x] bench-pipeline: json_schema 0.385, cmd_safety 1.0, ambiguity 0.923, tool_plan 0.933, orch 0.833, long_context 1.0
- [x] bench-runtime: 4/4
- [x] bench-code: Phase 4 full run stands, thinking off (HumanEval 0.933 / 0.902, MBPP 0.907 / 0.775);
  code with thinking on not measured

### Phase 6: Finalize
- [ ] pending

## Integration: August 2026 Modern Models (2026-08-12 to 2026-08-20)

Models: `qwen3.5:27b`, `qwen3-coder:30b-a3b`, `devstral-small:24b`,
`ministral-3:14b`, `ministral-3:8b`, and `ministral-3:3b`.

### Current gate state

| Model | Download/register/load | Broad smoke | Full code | Validated reasoning | Final state |
| --- | --- | --- | --- | --- | --- |
| `qwen3.5:27b` | complete | complete | complete | retry invalidated; ranked brain-only l50 rerun paused for smoke coverage | provisional brain default |
| `qwen3-coder:30b-a3b` | complete | complete | complete | retry invalidated; ranked brain-only l50 rerun paused for smoke coverage | code-focused brain alternative |
| `devstral-small:24b` | complete | complete | complete | retry invalidated; ranked brain-only l50 rerun paused for smoke coverage | brain runner-up |
| `ministral-3:14b` | complete | complete | complete | l50 reasoning/runtime complete | split-quality default |
| `ministral-3:8b` | complete | complete | complete | l50 reasoning/runtime complete | split-speed default |
| `ministral-3:3b` | complete | partial with retained failed attempts | full rerun complete | smoke reasoning and runtime complete | tested compact alternative |

The August campaign used limit 5 per leaf task. Grouped suites therefore produced
135 BBH samples (27 subtasks) and 70 MMLU-Pro samples (14 categories), but remain
smoke evidence because each leaf had only five examples. Pipeline, import, agent,
routing, runtime, and DaedalMap suites have bounded case sets and cannot be made
full merely by applying a larger global limit. EvalPlus code runs use their full
HumanEval+ and MBPP+ datasets unless the runner explicitly limits them.

Earlier failed attempts remain in the append-only ledger. The final August logs
show all five reasoning tasks completed for the five selected models; do not
interpret the preserved parent-task failure rows as the final campaign state.

### Closure campaign outcome

- Manifest: `campaigns/modern_models_validation_202608.json`
- Five selected models: validated GSM8K, DROP, and IFEval at limit 50.
- Ministral 3B: full EvalPlus code and the operational runtime suite.
- No archived or superseded model is included.
- Retry3 completed all 12 manifest lanes sequentially. The Ministral 14B and 8B
  reasoning/runtime results and Ministral 3B code/runtime results are valid.
- Ministral 3B completed 164 HumanEval and 378 MBPP cases. HumanEval base/plus
  pass rates were 76.2%/74.4%; MBPP base/plus were 69.0%/56.1%.

Attempt `20260820_modern_validation_l50` was interrupted by a rig thermal
shutdown and reboot. CPU temperature reached 100C while four model lanes were
active. Any rows written before the reboot are partial evidence and must not be
promoted. After physical fan/wiring checks and a clean SSH reboot, a two-lane
retry approached 90C and was stopped. Sequential retry
`20260820_modern_validation_l50_retry3` completed with a 94C maximum and no
95C guard activation.

The retry's three brain lanes are invalid despite their successful exit codes.
Port 11434 remained owned by a `qwen3.6:27b` container, and process snapshots
showed that same GGUF during the Qwen3.5, Qwen Coder, and Devstral suites. Their
misattributed rows were removed from the canonical ledger. The first brain-only attempt `modern-brain-revalidate-20261025` stopped
before its first suite while the user prioritized Nemotron and Mellum runtime
smokes. Both passed on b11669. The ranked sequential rerun started as
`modern-brain-revalidate-20261025-r2` using
`campaigns/modern_brain_reasoning_revalidation_20261025.json`: Qwen3.5
27B first (provisional brain), Qwen Coder 30B next (code alternative), then
Devstral 24B (runner-up). It was paused in its first reasoning suite
after a receipt audit found ten missing b11669 runtime promotion smokes.
`runtime-smoke-b11669-missing10-20261025` is running those before Phase 5 resumes. The current
campaign runner loads through the manager, verifies `/v1/models` identity,
and can run one active model with the 95C thermal guard. Its checkpoint is
under `/mnt/shared/logs/benchmarks/campaigns/history/modern_brain_reasoning_revalidation_20261025/modern-brain-revalidate-20261025-r2/`.
The first Qwen3.5 27B load reached ready on GPU0 at context 16,384; the runner
verified the served GGUF `Qwen3.5-27B-Q4_K_M.gguf` before starting its
reasoning suite. Do not promote the three scores until the identity fields
and suites complete.

## Integration: Gemma 4 12B (2026-06-05)

Tier: split (2x 1060 6GB) | GPU target: GPU 1+3 or 4+5 | Port: 11440 or 11441
GGUF: `gemma-4-12B-it-Q4_K_M.gguf` | Size: 7.4 GB (Q4_K_M) | Source: HuggingFace (google/gemma-4-12b-it-GGUF)

### Phase 0: Download
- [x] GGUF downloaded to `/mnt/shared/models/gemma-4-12b/`
- [x] File size verified: ~7.4 GB expected vs 7381382048 bytes (6.9 GiB) actual
- Notes: File already present on shared drive.

### Phase 1: Register
- [x] `model_tuning_profiles.json` — GGUF key added (`gemma-4-12B-it-Q4_K_M.gguf`)
- [x] `model_tuning_profiles.json` — short alias added (`gemma-4:12b`)
- [x] `models.catalog.json` — entry added (tier 2, split_gpu, pair_1_3/pair_4_5)
- [x] System prompt: Worker (strict) — same family as other Gemma 4 models
- [x] Runtime config: ctx_size=8192, batch_size=64, n_gpu_layers=999
- Notes: Used same prompt and config pattern as gemma-4-e4b/e2b. Split placement matches qwen2.5-coder:14b and phi-4:14b split groups.

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh`
- [x] `/v1/models` responds with correct model ID (`gemma-4-12B-it-Q4_K_M.gguf`)
- [x] Docker logs checked — no warnings (thinking=1 as expected for Gemma 4)
- [x] VRAM usage: GPU 1: 3372 MiB, GPU 3: 4060 MiB, CPU mapped: 924 MiB
- [x] Load time: ~40s
- [x] Runtime image: `llama-runtime:b8884-candidate` (b8884-750579ff1)
- [x] Extra args needed: `--tensor-split 1,1` (NOT `1,0,1,0,0,0` — use 2-value mask matching visible GPUs), `-fit off` (auto-fitter fails with forced `--n-gpu-layers 999`), no forced n-gpu-layers
- Notes:
  - First attempt with `--n-gpu-layers 999`: auto-fitter aborted ("n_gpu_layers already set by user to 999, abort")
  - Second attempt without forced layers but `--tensor-split 1,0,1,0,0,0`: OOM on CUDA0 — the 6-value split mask doesn't match 2 visible GPUs, full 7024 MiB allocated to device 0
  - Third attempt with `--tensor-split 1,1 -fit off --n-gpu-layers 48`: success, model split across both GPUs
  - Model buffer: CUDA0=3102 MiB, CUDA1=3786 MiB, CPU=924 MiB
  - KV cache: 34 MiB (non-SWA, 8 layers) + 212.5 MiB (SWA, 40 layers)

### Phase 3: Litmus Test
- [x] Reasoning check (555): **PASS** — clean "555" response, no think tags
- [!] JSON check: **FAIL** — wraps JSON in ```json markdown fences (known Gemma 4 behavior, consistent with E4B/E2B)
- [x] Code generation check: **PASS** — clean function output (wraps in ```python but function present)
- Fixes applied: none — JSON fencing is a known Gemma 4 trait handled by system prompt at bench time
- Notes: thinking=1 active in runtime but content field receives the answer correctly. `--patch-think-tag-strip` will be needed for DROP (same as all Gemma 4 models).

### Phase 4: Smoke Runs → merged with Phase 5
- Skipped standalone smoke (limit 5) — went directly to full runs since pipeline is fast and code has no limit option.

### Phase 5: Full Run
- [x] bench-pipeline (full): json_schema 23.1%, cmd_safety 75.0%, ambiguity 46.2%, tool_plan 93.3%, orch_tradeoff 83.3%, long_context 92.9%
- [x] bench-code (full 542): HumanEval base 11.0%, plus 11.0%; MBPP base 36.8%, plus 34.7%
- [x] bench-reasoning: COMPLETED (A/B test: thinking-on vs thinking-off)
- Run names: `gemma4_12b_smoke_v1` (pipeline, code), `gemma4_12b_l100_v2` (reasoning GSM8K), `gemma4_12b_think1024_bbh_l5` (BBH think-on), `gemma4_12b_nobudget_bbh_l5` (BBH think-off)
- Flags needed: `-e BENCHMARK_DISABLE_AUTO_RESERVE=1` for all suites, `--patch-think-tag-strip` for reasoning
- Notes:
  - Pipeline took ~45 min on split 1060s. Non-zero on all 6 tests.
  - Code took ~12 hours on split 1060s (542 problems at ~0.75/min). Low HumanEval consistent with other Gemma 4 models — markdown code fences stripped by evalplus sanitizer.
  - First reasoning attempt (v1) failed: rig root disk 100% full, HuggingFace dataset download failed. Fixed by `docker container prune && docker image prune` (freed 22 GB). Retried as v2.
  - Reasoning v2 (l100): GSM8K completed: strict 0.01, flexible 0.10. Low strict score is format mismatch: model outputs `$18` instead of `#### 18`. Flexible extract also low because `$` prefix confuses number extractor. Known Gemma 4 output format issue, not a capability issue.
  - L100 BBH/DROP never completed — l100 BBH on split 1060s estimated 50+ hours. Run was stopped in favor of A/B testing approach.
  - **A/B Test: Thinking On vs Off (BBH l5)**:
    - Two runtimes loaded: `gemma4-12b-budget1024` (GPUs 1+3, port 11440, `--reasoning-budget 1024`) and `gemma4-12b-nobudget` (GPUs 4+5, port 11441, `--reasoning-budget 0`)
    - Both running BBH l5 (135 requests each) simultaneously
    - Budget=1024 generates ~1800 tokens/request (thinking + answer), budget=0 generates ~750 tokens/request
    - **Think-off result: BBH = 0.8222** (completed in 2h25m, avg 64s/req)
    - **Think-on result: BBH = 0.2444** (completed in 3h57m, avg 106s/req)
    - **Verdict**: `--reasoning-budget 0` is vastly better for BBH benchmarks. Thinking tokens consume generation budget, truncating the CoT answer before the "So the answer is..." extraction point. 13 of 27 subtasks scored 0.0 with thinking on.
    - **Recommendation for Gemma 4 12B benchmarks**: Use `--reasoning-budget 0` for all reasoning suites. The model reasons well in the visible output without needing the hidden thinking channel.
  - **Brain re-run (2026-06-13)**: BBH l50 and DROP l50 on brain (3090) with `--reasoning-budget 0` and `--patch-think-tag-strip`:
    - BBH l50: 0.8067 (confirmed l5 A/B test score of 0.822)
    - DROP l50: EM 0.7400, F1 0.7892 — first DROP score, very strong
    - Runtime: brain (GPU 0, 3090), `llama-runtime:b8884-candidate`, ~75 min total
    - Run name: `gemma4_12b_brain_l50_v1`
    - Note: Previous overnight attempt failed due to using default `sm61-sm86` image (Gemma 4 arch unsupported). Fixed by specifying `--image llama-runtime:b8884-candidate`.

### Phase 6: Finalize
- [x] BENCHMARK_SCORES.md updated — family summary, pipeline, code, reasoning tables + notes (updated with brain l50 BBH/DROP)
- [x] MODEL_LIBRARY.md inventory updated — added to Active Model Inventory as 12B split
- [x] MODEL_RUNTIME_GUIDE.md notes added — updated gemma-4 family section, thinking reference, context sizes
- [x] BENCHMARK_LESSONS_LEARNED.md updated — thinking A/B test results, split-load findings, runtime image mismatch lesson
- Notes: BBH 0.807 at l50 confirms l5 A/B test. DROP F1 0.789 is competitive with 26B-A4B (0.785) and 31B (0.793). GSM8K format issue (0.10) remains — known Gemma 4 output format, not capability.

## Integration: gpt-oss 20B (2026-06-12)

Tier: brain (3090 24GB) | GPU target: GPU 0 | Port: 11434
GGUF: `gpt-oss-20b-mxfp4.gguf` | Size: 12.1 GB (MXFP4 native) | Source: HuggingFace (ggml-org/gpt-oss-20b-GGUF)

Architecture: MoE, 21B total params, 3.6B active. OpenAI's first open-weight model. Apache 2.0.

### Phase 0: Download
- [x] GGUF downloaded to `/mnt/shared/models/gpt-oss-20b/`
- [x] File size verified: ~12.1 GB expected vs 12,109,566,560 bytes (11.3 GiB) actual
- Notes: Downloaded via wget from HuggingFace. MXFP4 is a native quantization format (not post-training quant like Q4_K_M).

### Phase 1: Register
- [x] `model_tuning_profiles.json` — GGUF key added (`gpt-oss-20b-mxfp4.gguf`)
- [x] `model_tuning_profiles.json` — short alias added (`gpt-oss:20b`)
- [x] `models.catalog.json` — entry added (tier 3, single_gpu/brain)
- [x] System prompt: Worker (strict)
- [x] Runtime config: ctx_size=16384, batch_size=128, n_gpu_layers=999
- [x] Extra args: `--jinja` (required for OpenAI chat template)
- Notes: First MXFP4 model in our catalog. MoE with 3.6B active — should be fast despite 20B total.

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh`
- [x] `/v1/models` responds with correct model ID (`gpt-oss-20b-mxfp4.gguf`)
- [x] Docker logs checked — clean load, `thinking = 1` (runtime auto-detects thinking via OpenAI channels)
- [x] VRAM usage: 11,587 MiB on GPU 0 (13GB headroom on 3090)
- [x] Load time: ~5s
- [x] Runtime image: llama-runtime:sm61-sm86
- [x] Extra args needed: `--jinja` (confirmed required for chat template)
- Notes: Chat template uses OpenAI channel system (`<|start|>`, `<|channel|>`, `<|message|>`, `<|end|>`). Channels: analysis, commentary, final. "Reasoning: medium" preset. Compute buffer: 99.6 MiB. KV cache at ctx 16384.

### Phase 3: Litmus Test
- [x] Reasoning check (555): **PASS** — clean "555" in content, reasoning goes to `reasoning_content` field (properly separated)
- [x] JSON check: **PASS** — clean valid JSON `{"name":"Alice","age":30}`, no markdown fences
- [x] Code generation check: **PASS** — clean `def is_palindrome(s): return s == s[::-1]`
- Fixes applied: none needed
- Notes: Cleanest litmus results of any model tested. thinking=1 but reasoning goes to separate `reasoning_content` field via OpenAI channel system, not inline `<think>` tags. Content field is always clean. No `--reasoning-budget 0` needed, no `--patch-think-tag-strip` needed. This is how thinking SHOULD work.

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline: json_schema 23.1%, cmd_safety 75.0%, ambiguity 15.4%, tool_plan 93.3%, orch_tradeoff 75.0%, long_context 92.9%
- [x] bench-code (full 542): HumanEval base 62.2% / plus 58.5%, MBPP base 73.8% / plus 63.5%
- [x] bench-reasoning --limit 10 (v1, OLD prompt): GSM8K strict 20% / flexible 80%, BBH 6.7%, DROP EM 50% / F1 60%
- [x] bench-reasoning --limit 10 (v2, FIXED prompt): GSM8K strict 20% / flexible 60%, **BBH 64.1%**, DROP EM 20% / F1 44.8%
- [x] Raw outputs inspected — BBH extraction failure diagnosed (see notes)
- [x] All suites produce non-zero scores (except BBH v1 — fixed in v2)
- Flags needed: None for pipeline/code. `--reasoning-budget 0` added to runtime for reasoning v2 (prompt fix, not thinking suppression).
- Fixes applied:
  - **BBH 6.7% root cause**: Channel-based thinking puts reasoning in `reasoning_content`, content gets only terse bare letter ("A"). System prompt "keep output minimal" reinforced this. Additionally, when model does output "So the answer is", it wraps answer in markdown bold `**(A)**` which breaks the `get-answer` regex `[Ss]o the answer is \(([A-Za-z])\)`.
  - **Fix**: Changed system prompt to: "reason briefly then conclude with exactly: So the answer is (X). Use plain text only, no markdown formatting." Added `--reasoning-budget 0` to `extra_args` (prevents channel reasoning from consuming output budget).
  - **Verified**: Manual curl test with updated prompt produces extractable "So the answer is (B)." — regex matches.
- Notes:
  - Pipeline: ~65s total on 3090. All 6 stages non-zero.
  - Code: ~32 min on 3090. Best HumanEval base (62.2%) and MBPP base (73.8%) in catalog.
  - Reasoning v1: GSM8K and DROP decent, BBH is extraction-broken (not capability).
  - Run names: `gptoss_smoke_v1` (pipeline), `gptoss_code_v1` (code), `gptoss_smoke_v1` (reasoning v1), `gptoss_smoke_v2` (reasoning v2)

### Phase 5: Full Run (limit 50/100)
- [x] bench-reasoning --limit 100 (GSM8K, BBH, DROP): COMPLETE
  - Run name: `gptoss_l100_v1`
  - GSM8K: strict 0.15, flexible 0.80 (strict low due to format: model outputs number without `#### N` prefix)
  - BBH: 0.645 (confirmed l10 smoke score of 0.641 — prompt fix is stable at scale)
  - DROP: EM 0.18, F1 0.351
  - Runtime: brain (GPU 0, 3090), ~82 min total, `--reasoning-budget 0`, `--jinja`
- [n/a] bench-pipeline: no limit parameter (fixed test set), smoke run is the full run
- [n/a] bench-code: no limit parameter (fixed test set), smoke run is the full run
- Notes: GSM8K flexible improved from 0.60 (l10) to 0.80 (l100) — small sample noise at l10. BBH and DROP stable. This model's main strength is code generation (HumanEval 62.2%, MBPP 73.8%).

### Phase 6: Finalize
- [x] BENCHMARK_SCORES.md updated (l100 reasoning scores, family summary)
- [x] MODEL_LIBRARY.md inventory updated
- [x] MODEL_RUNTIME_GUIDE.md notes added
- [x] BENCHMARK_LESSONS_LEARNED.md updated (channel-based thinking narrative)

## Integration: Phi-4-mini-reasoning 3.8B (2026-06-12)

Tier: single (1060 6GB) | GPU target: GPUs 1-5 | Port: 11435-11439
GGUF: `Phi-4-mini-reasoning-Q4_K_M.gguf` | Size: 2.49 GB (Q4_K_M) | Source: HuggingFace (unsloth/Phi-4-mini-reasoning-GGUF)

Architecture: Dense 3.8B. Microsoft reasoning-focused variant of Phi-4-mini. MIT license.
Has `<think>`/`</think>` reasoning tokens — similar to DeepSeek-R1 family.

### Phase 0: Download
- [x] GGUF downloaded to `/mnt/shared/models/phi-4-mini-reasoning/`
- [x] File size verified: ~2.49 GB expected vs 2.4 GB actual
- Notes: Downloaded via wget from HuggingFace (unsloth GGUF conversion).

### Phase 1: Register
- [x] `model_tuning_profiles.json` — GGUF key added (`Phi-4-mini-reasoning-Q4_K_M.gguf`)
- [x] `model_tuning_profiles.json` — short alias added (`phi-4-mini-reasoning:3.8b`)
- [x] `models.catalog.json` — entry added (tier 1, single_gpu)
- [x] System prompt: Worker (strict)
- [x] Runtime config: ctx_size=4096, batch_size=64, n_gpu_layers=999
- Notes: Same size as phi-4-mini-instruct but different model — trained specifically for reasoning with think tokens.

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh`
- [x] `/v1/models` responds with correct model ID (`Phi-4-mini-reasoning-Q4_K_M.gguf`)
- [x] Docker logs checked — no warnings, `thinking = 0` (runtime doesn't auto-detect thinking mode)
- [x] VRAM usage: 2772 MiB on GPU 1
- [x] Load time: ~3s
- [x] Runtime image: llama-runtime:sm61-sm86
- [x] Extra args needed: `--reasoning-budget 0` tested but has NO EFFECT — think tokens are structural (same as DeepSeek-R1)
- Notes: Chat template detected as Phi-style (`<|system|>`, `<|user|>`, `<|assistant|>`). KV cache 272 MiB (q8_0). Model metadata includes `general.finetune = reasoning`.

### Phase 3: Litmus Test
- [!] Reasoning check (555): **FAIL** — correct answer (555) but wrapped in verbose `<think>` chain-of-thought
- [!] JSON check: **FAIL** — think tags + wraps JSON in ```json markdown fences
- [!] Code generation check: **FAIL** — think tags present, function is correct inside
- Fixes applied: None effective — `--reasoning-budget 0` does not suppress think tokens. They are structural (baked into model vocabulary/training), not an API feature.
- Notes: Identical behavior to DeepSeek-R1 family. The model always generates `<think>...</think>` blocks before the answer. Answers themselves are correct. Will use `--patch-think-tag-strip` at bench time for BBH/DROP. Code suite will have degraded results (evalplus sanitizer strips think + code together). This is a known limitation for think-token models.

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline: json_schema 0%, cmd_safety 83.3%, ambiguity 76.9%, tool_plan 100%, orch_tradeoff 83.3%, long_context FAILED (runtime OOM killed)
- [!] bench-code: **INCOMPATIBLE** — structural think tokens break evalplus code extraction
  - v1: OOM killed at 2g Docker memory limit (anon-rss: 2073576kB)
  - v2: Restarted with 3g/4g limits, got 64/164 HumanEval before runtime timeout
  - Root cause: Think chains produce very long output (thousands of tokens) per problem, causing either memory pressure or timeouts on 1060
  - Parsed solutions show `<think>` as entire content — evalplus sanitizer strips think + code together
  - **Known limitation**: bench-code is not viable for structural-think-token models on 1060 hardware
- [!] bench-reasoning --limit 10: GSM8K strict 0% / flex 10%. **BBH FAILED** (runtime OOM killed after ~52 min). **DROP FAILED** (runtime already dead).
  - Root cause: BBH few-shot prompts are long (~1000+ tokens), combined with think chains exhausts memory at 3g Docker limit on 1060
  - GSM8K completed because prompts are shorter and 10 requests finished before memory pressure built
- [x] Raw outputs inspected — think tokens in all outputs confirmed
- [!] Not all suites produce non-zero scores (json_schema 0%, bench-code incompatible)
- Flags needed: `--patch-think-tag-strip` for bench-reasoning. Memory limit 3g/4g for runtime.
- Notes:
  - Pipeline: 5/6 stages passed, 1 failed (long_context — runtime died under memory pressure from long context + think chains)
  - Code: Known limitation, documented. Not a model settings fix — structural think tokens can't be disabled.
  - Reasoning: Not yet attempted. Expected to work with `--patch-think-tag-strip`.
  - Run names: `phi4mr_smoke_v1` (pipeline), `phi4mr_smoke_v1`/`phi4mr_smoke_v2` (code — both failed)
  - **Known Suite Incompatibilities**:
    - bench-code: Structural think tokens break evalplus extraction. No model settings fix available.
    - bench-pipeline json_schema: Think tokens in JSON responses. Would need `--patch-think-tag-strip` equivalent for pipeline suite.

### Phase 5: Full Run (limit 50/100)
- [ ] bench-pipeline: <pending>
- [ ] bench-code: **SKIPPED** — known incompatibility (structural think tokens)
- [ ] bench-reasoning --limit 50: <pending>
- Run names:
- Notes: bench-code skipped due to documented incompatibility.

### Phase 6: Finalize
- [ ] BENCHMARK_SCORES.md updated
- [ ] MODEL_LIBRARY.md inventory updated
- [ ] MODEL_RUNTIME_GUIDE.md notes added
- [ ] BENCHMARK_LESSONS_LEARNED.md updated (if applicable)
