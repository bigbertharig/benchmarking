# Model research gate (Phase R)

This is the required first step for a **new** local model, before Phase 0 of
[NEW_MODEL_INTEGRATION.md](NEW_MODEL_INTEGRATION.md) downloads weights. Its job is to
reject poor or unavailable candidates cheaply, using public evidence as a rough
screen. Local standard suites then check the downloaded quant and runtime; custom
application and harness tests decide whether it is useful here.

## Current comparison pool

The source of truth is `model_registry.json` and `model_roles.json`, not a copied
leaderboard. At the 2026-11-08 review the registry held 46 entries: 23 active,
7 candidate, 15 archived, and 1 invalid. Select at least one **active model in
the intended rig lane** as the candidate's local comparator. Relevant baselines
include `qwen2.5-coder:7b` on one 1060, `ministral-3:14b` on a worker pair,
`qwen3.6:27b` and `gemma-4:31b` on the 3090, and
`nemotron-3.5-bolt:74b-a9b` for a capacity lane. Verify current roles and
measured placement before each decision; this list is a dated snapshot.

## Evidence to collect

1. **Identity and availability:** official model page and exact upstream model
   ID; release date, license, weight files, architecture, native context, and
   whether this is weights, API access, preview, or rumor. Record the exact
   quant publisher, file, size, and hash source. Do not infer a GGUF from a
   safetensors announcement.
2. **Public capability:** at least one official or benchmark-creator result if
   available, with benchmark version, score, model variant, prompting, tools,
   reasoning budget, context, harness, repetitions, and reporting date. Mark
   missing fields `unknown`. Add independent results when available. Record
   absence of published scores rather than inventing comparability.
3. **Fit and value:** compare estimated weight size plus context/KV and runtime
   overhead with the intended cards and current fit evidence. State the role
   the model could improve, the active local comparator, and the public signal
   that makes a trial worthwhile. The estimate is not a load validation.
4. **Decision:** `trial`, `watch`, or `skip`. `trial` requires released weights,
   a specific obtainable quant, a plausible fit, and a concrete test question.
   `watch` means a missing release, quant, or decisive evidence could change the
   answer. `skip` records a reason. A rumor can be researched but never marked
   `trial` merely on a predicted release date.

Use a JSON record under `research/candidates/` following
[`_template.json`](research/candidates/_template.json). The checker reads the
record by `model_id` and fails closed for a missing or incomplete `trial`:

```bash
python3 scripts/active/check_model_research.py <model-id>
```

Run that command **before** the Phase 0 download command. A passing research
gate authorizes only the planned trial; Phase 1 registration, fit, and the
later local tests remain separate gates. Update the record and rerun the check
if the model, quant, or target lane changes. Review public evidence again if
the record is more than 30 days old. The checker enforces this age for a trial.

## Retrospective calibration

Research some already-tested models as controls. Use
[`PUBLIC_LOCAL_CALIBRATION_2026-11-08.md`](research/PUBLIC_LOCAL_CALIBRATION_2026-11-08.md)
as the first pass. For each public/local pair, label:

- **Directly comparable:** same model variant, dataset/version, metric, tools,
  prompt and inference setup, and similar precision. Rare for GGUF vs hosted.
- **Directional only:** same capability family but a changed quant, sample,
  scaffold, reasoning budget, or benchmark version.
- **Different task:** useful for candidate selection, never subtract scores.

Keep `public_score`, `local_score`, and the reason for any mismatch separate.
Do not add a public score to the local JSONL ledger or derive an ECI score from
the local suites. A public result is a lead for a local test, not a replacement
for one. Treat large gaps as a prompt, quant, runtime, extraction, or harness
investigation before calling a model weak; keep the original receipt.

## Promotion from screening

After Phase R passes, use the existing integration lane and loading experiments
to establish a workable recipe. Record the loading and context decision in
[`MODEL_LOADING_GATE.md`](MODEL_LOADING_GATE.md) before starting full suites.
Only then use workload-specific tests (`bench-dataimport`, `bench-geoimport`,
`bench-agent`, DaedalMap, and eventually checkpoint tasks) and, where relevant,
the separate `llm-harness` comparison playbook. Never merge different
models, served contexts, or harnesses into one claimed model-quality score.
