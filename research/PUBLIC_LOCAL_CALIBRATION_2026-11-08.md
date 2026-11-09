# Public claims against local evidence — first calibration pass

Reviewed 2026-11-08. Local values below are from
`results/model_library_scoreboard.json` generated 2026-11-04, matched to
`model_registry.json`. They describe the **tested GGUF and rig setup**, while
public reports usually describe official weights, different precision,
settings, samples, and sometimes a full agent scaffold. Do not subtract a
number in one benchmark from a number in a different benchmark. Open each
selected local run receipt before making a replacement decision.

| Existing model and tested quant | Public report | Local selected evidence | Interpretation / next check |
| --- | --- | --- | --- |
| `qwen3.6:27b`, Q4_K_M | [Qwen model card](https://huggingface.co/Qwen/Qwen3.6-27B): SWE-bench Pro 53.5%, Terminal-Bench 2.0 59.3%, LiveCodeBench v6 83.9%. These use the card's agent or benchmark settings, not this GGUF setup. | HumanEval+ 90.24% (164 full); MBPP+ 77.51% (378 full); BBH 91.56% (1,350 validated); strict prompt IFEval 88% (50). | Strong local short-code and reasoning baseline. Public agent scores suggest a repo-task comparison, but no direct score match exists yet. |
| `qwen3.8:27b`, UD-Q4_K_M | [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-27B): SWE-bench Pro 61.7% and Terminal-Bench 2.1 73.0%, versus the card's Qwen3.6 53.5% and 63.4% on those same rows. | HumanEval+ 90.24% (164 full) and MBPP+ 77.51% (378 full), tied with the local Qwen3.6 selected rows; BBH **strict** 41.63% but **flexible** 91.04% (1,350 validated), versus Qwen3.6 91.56% on both; strict prompt IFEval 92% (50). | The large strict BBH gap is principally answer extraction: Qwen3.8 thinking-on often gives a bare correct answer where the strict scorer expects a fixed phrase. Flexible BBH is nearly tied. These settings do not isolate a model-version effect. The public Terminal-Bench row is v2.1, while the older Qwen3.6 card reports v2.0; use the Qwen3.8 card's paired v2.1 values for the public comparison. See `research/QWEN36_VS_QWEN38_BENCHMARK_AUDIT_2026-11-08.md`. |
| `gpt-oss:20b`, MXFP4 | [OpenAI model card](https://deploymentsafety.openai.com/gpt-oss) reports MMLU 80.4/84.0/85.3% at low/medium/high reasoning and SWE-bench Verified 37.4/53.2/60.7%. Reasoning effort materially changes the public number. | HumanEval+ 81.10% (164 full); MBPP+ 65.34% (378 full); BBH 83.26% (1,350 validated); flexible GSM8K 76% (50); strict prompt IFEval 70% (50). | Public and local tasks differ, so this is a capability profile, not a numerical reproduction. Record local reasoning effort and output cap before any closer public comparison. Its coding score is below both local Qwen 27B models, while its validated BBH remains useful. |
| `qwen2.5-coder:7b`, Q4_K_M | [Official model card](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) identifies a 7.61B code model with a 131,072-token trained context; the [Qwen launch post](https://qwenlm.github.io/blog/qwen2.5/) positions it as a coding specialist. Trained context is not a demonstrated context on one 1060. | HumanEval+ 84.15% (164 full); MBPP+ 70.37% (378 full); flexible GSM8K 68% (50); strict prompt IFEval 60% (50). | Good single-card coding baseline. Public positioning predicts its stronger code than instruction-following behavior, but this table has no same-protocol public score to reproduce. Compare future 6 GB candidates on both code and real worker tasks. |

## What this calibration shows

Public scores are useful for choosing a **question** to test. Qwen3.8's public
agent results make repo-level work worth testing even though local function
generation ties Qwen3.6. The apparent strict BBH gap is an extraction artifact;
flexible BBH is nearly tied, while the current runs use different reasoning
settings and token budgets.
OpenAI's reasoning-effort spread shows why a single published score without
settings is weak screening evidence. A model card's trained context is not a
rig capacity result. The next calibration pass should seek a public benchmark
that the rig runs with a matched version and metric, then record protocol and
quant differences before interpreting any numerical gap.

## Qwen 4 watch

[Alibaba's September 25 statement](https://home.alibabagroup.com/en-US/document-2041268239081668608)
says Qwen 4 is in training. As of this review, it gives no release date,
weight file, local size, license, or score for an exact Qwen 4 variant. Rumored
names and dates are not inputs to a download decision. The machine-readable
`research/candidates/qwen4-family.json` remains `watch`; revisit the official
[Qwen model catalog](https://huggingface.co/Qwen) when weights appear, then
identify a specific variant and quant and compare it to the relevant active
model before marking a `trial`.
